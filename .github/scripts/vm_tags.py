"""Validate VM tag deferral against the original reviewed Terraform intent."""

import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess


VM_TYPE = "proxmox_virtual_environment_vm"
MANIFEST = ".tf-tags.json"
# These provider-computed observations can become unknown during a tag update.
OBSERVATIONS = {"ipv4_addresses", "ipv6_addresses", "network_interface_names", "mac_addresses"}


def has_unknown(value):
    if isinstance(value, dict):
        return any(has_unknown(item) for item in value.values())
    if isinstance(value, list):
        return any(has_unknown(item) for item in value)
    return value is True


def terraform_json(directory, *arguments):
    result = subprocess.run(["terraform", *arguments], cwd=directory,
                            capture_output=True, text=True)
    if result.returncode:
        # JSON plans contain secrets; never include stdout or stderr in an exception.
        raise ValueError("Cannot read Terraform JSON for tag staging")
    return json.loads(result.stdout)


def changes_by_address(plan):
    if plan.get("complete") is False or plan.get("errored") or plan.get("deferred_changes"):
        raise ValueError("VM tag staging requires a complete Terraform plan")
    result = {}
    for resource in plan.get("resource_changes", []):
        address = resource["address"]
        if address in result:
            raise ValueError("Duplicate resource address in tag staging plan")
        result[address] = resource
    return result


def plan_intent_hash(plan):
    # The apply token is intentionally different from the plan token. Terraform
    # normally omits ephemeral values; exclude its known credential input too.
    variables = {key: value for key, value in plan.get("variables", {}).items()
                 if key not in {"deferred_vm_tags", "virtual_environment_api_token"}}
    intent = {"configuration": plan.get("configuration", {}), "variables": variables}
    return hashlib.sha256(json.dumps(intent, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def deferred_guests(plan, environment):
    if plan.get("variables", {}).get("deferred_vm_tags", {}).get("value"):
        raise ValueError("The reviewed plan must describe the final tags without deferral")
    guests = []
    identities = set()
    for address, resource in changes_by_address(plan).items():
        change = resource["change"]
        if resource.get("type") != VM_TYPE or "create" not in change["actions"]:
            continue
        values = change["after"]
        tags = values.get("tags")
        if not tags:
            if change.get("after_unknown", {}).get("tags"):
                raise ValueError("New VM tags must be known before staging")
            continue
        if (environment not in {"dev", "prod"} or values.get("pool_id") != environment
                or not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags)
                or not all(isinstance(values.get(key), str) and values[key]
                           for key in ("node_name", "name"))):
            raise ValueError("New VM tag staging requires a known identity and its own environment pool")
        selector = values["node_name"] + "/" + values["name"]
        if selector in identities:
            raise ValueError("Ambiguous new VM tag staging identity")
        identities.add(selector)
        guests.append({"address": address, "selector": selector, "tags": sorted(tags),
                       "node_name": values["node_name"], "name": values["name"],
                       "pool_id": values["pool_id"], "vm_id": values.get("vm_id")})
    return guests


def validate_infrastructure_plan(reviewed, staged, guests):
    original = changes_by_address(reviewed)
    actual = copy.deepcopy(changes_by_address(staged))
    if original.keys() != actual.keys():
        raise ValueError("Deferring VM tags changed the planned resource set")
    for guest in guests:
        change = actual[guest["address"]]["change"]
        if change["after"].get("tags") != [] or has_unknown(change.get("after_unknown", {}).get("tags")):
            raise ValueError("Infrastructure plan must create each staged VM without tags")
        change["after"]["tags"] = original[guest["address"]]["change"]["after"]["tags"]
        for mask in ("after_sensitive", "after_unknown"):
            expected = original[guest["address"]]["change"].get(mask, {})
            if "tags" in expected:
                change.setdefault(mask, {})["tags"] = expected["tags"]
            else:
                change.get(mask, {}).pop("tags", None)
    if (actual != original or plan_intent_hash(staged) != plan_intent_hash(reviewed)
            or staged.get("output_changes", {}) != reviewed.get("output_changes", {})
            or staged.get("action_invocations", []) != reviewed.get("action_invocations", [])):
        raise ValueError("Deferring VM tags changed more than the reviewed create-time tags")


def module_resources(module):
    yield from module.get("resources", [])
    for child in module.get("child_modules", []):
        yield from module_resources(child)


def reviewed_data_reads(plan):
    resources = list(module_resources(plan.get("planned_values", {}).get("root_module", {})))
    resources.extend(plan.get("resource_changes", []))
    return sorted({resource["address"] for resource in resources if resource.get("mode") == "data"})


def state_resources(state):
    return {resource["address"]: resource["values"]
            for resource in module_resources(state.get("values", {}).get("root_module", {}))}


def bind_created_guests(state, guests):
    resources = state_resources(state)
    bound = []
    for guest in guests:
        actual = resources.get(guest["address"], {})
        if (any(actual.get(key) != guest[key] for key in ("node_name", "name", "pool_id"))
                or type(actual.get("vm_id")) is not int or actual["vm_id"] < 100
                or (guest["vm_id"] is not None and actual["vm_id"] != guest["vm_id"])):
            raise ValueError("Created VM does not match the reviewed tag manifest")
        bound.append(dict(guest, vm_id=actual["vm_id"]))
    return bound


def validate_tag_plan(plan, guests, data_reads=(), intent_sha256=None):
    if intent_sha256 is not None and plan_intent_hash(plan) != intent_sha256:
        raise ValueError("Tag follow-up plan changed the reviewed configuration or input values")
    if plan.get("action_invocations"):
        raise ValueError("Tag follow-up plan cannot invoke additional actions")
    expected = {guest["address"]: guest for guest in guests}
    found = set()
    for address, resource in changes_by_address(plan).items():
        change = resource["change"]
        if resource.get("previous_address") or change.get("importing"):
            raise ValueError("Tag follow-up plan cannot move or import Terraform state")
        if resource.get("mode") == "data" and change["actions"] == ["read"] and address in data_reads:
            # For example, Talos health checks can be deferred through a VM dependency.
            continue
        if change["actions"] == ["no-op"] and address not in expected:
            continue
        guest = expected.get(address)
        if (guest is None or resource.get("type") != VM_TYPE
                or change["actions"] not in (["update"], ["no-op"])):
            raise ValueError("Tag follow-up plan contains an unreviewed resource change")
        before, after = change["before"], change["after"]
        if (any(before.get(key) != guest[key] or after.get(key) != guest[key]
                for key in ("node_name", "name", "pool_id", "vm_id"))
                or sorted(after.get("tags") or []) != guest["tags"]):
            raise ValueError("Tag follow-up plan differs from the reviewed VM identity or tags")
        unknown = change.get("after_unknown", {})
        if any(has_unknown(value) for key, value in unknown.items() if key not in OBSERVATIONS):
            raise ValueError("Tag follow-up plan has unreviewed unknown values")
        settings_before, settings_after = copy.deepcopy(before), copy.deepcopy(after)
        # bpg 0.109.0 reads absent CPU flags as null, then plans [] on the next update.
        # Both mean no custom flags; nonempty flag changes remain forbidden.
        for values in (settings_before, settings_after):
            for cpu in values.get("cpu") or []:
                if cpu.get("flags") is None:
                    cpu["flags"] = []
        keys = settings_before.keys() | settings_after.keys()
        if any(settings_before.get(key) != settings_after.get(key)
               for key in keys - {"tags"} if not (key in OBSERVATIONS and has_unknown(unknown.get(key)))):
            raise ValueError("Tag follow-up plan changes VM settings beyond tags")
        found.add(address)
    if found != expected.keys():
        raise ValueError("Tag follow-up plan omits a reviewed staged VM")


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seed_files(directory, plan):
    """Bind local NoCloud images referenced by the plan to their exact bytes."""
    files = {}
    resources = list(module_resources(plan.get("planned_values", {}).get("root_module", {})))
    resources.extend(dict(resource, values=resource["change"].get("after"))
                     for resource in plan.get("resource_changes", []))
    for resource in resources:
        values = resource.get("values") or {}
        if resource.get("type") != "proxmox_virtual_environment_file":
            continue
        for source in values.get("source_file") or []:
            path = source.get("path") or ""
            if not path.startswith(".cloud-init/"):
                continue
            if not re.fullmatch(r"\.cloud-init/[0-9a-f]{64}\.iso", path):
                raise ValueError("Invalid cloud-init seed path in saved plan")
            digest = file_hash(Path(directory) / path)
            if digest != source.get("checksum") or Path(path).stem != digest:
                raise ValueError("Cloud-init seed differs from the reviewed checksum")
            files[path] = digest
    return files


def write_manifest(directory, guests, context, environment, target, destroy, data_reads=(), reviewed_plan=None):
    directory = Path(directory)
    manifest = {"version": 1, "environment": environment, "target": target, "destroy": destroy,
                "sha": context["GITHUB_SHA"], "run_id": context["GITHUB_RUN_ID"],
                "run_attempt": context["GITHUB_RUN_ATTEMPT"], "guests": guests,
                "data_reads": list(data_reads),
                "intent_sha256": plan_intent_hash(reviewed_plan or {}),
                "seed_files": seed_files(directory, reviewed_plan or {}),
                "plan_sha256": file_hash(directory / "tfplan"),
                "lock_sha256": file_hash(directory / ".terraform.lock.hcl")}
    (directory / MANIFEST).write_text(json.dumps(manifest) + "\n")


def read_manifest(directory, context, environment, target, destroy):
    directory = Path(directory)
    manifest = json.loads((directory / MANIFEST).read_text())
    expected = {"version": 1, "environment": environment, "target": target, "destroy": destroy,
                "sha": context["GITHUB_SHA"], "run_id": context["GITHUB_RUN_ID"],
                "run_attempt": context["GITHUB_RUN_ATTEMPT"],
                "plan_sha256": file_hash(directory / "tfplan"),
                "lock_sha256": file_hash(directory / ".terraform.lock.hcl")}
    if (type(manifest.get("version")) is not int or type(manifest.get("destroy")) is not bool
            or any(manifest.get(key) != value for key, value in expected.items())):
        raise ValueError("Tag manifest does not match this saved plan, dependencies, target and run")
    guests = manifest["guests"]
    if not isinstance(guests, list) or (destroy and guests):
        raise ValueError("Invalid staged VM manifest")
    for guest in guests:
        if (not isinstance(guest, dict) or not all(isinstance(guest.get(key), str) and guest[key]
                for key in ("address", "selector", "node_name", "name", "pool_id"))
                or guest["selector"] != guest["node_name"] + "/" + guest["name"]
                or not isinstance(guest.get("tags"), list)
                or not all(isinstance(tag, str) for tag in guest["tags"])
                or (guest.get("vm_id") is not None and type(guest["vm_id"]) is not int)):
            raise ValueError("Invalid staged VM identity or tags in manifest")
    if len({guest["address"] for guest in guests}) != len(guests):
        raise ValueError("Duplicate staged VM in manifest")
    if any(guest["pool_id"] != environment for guest in guests):
        raise ValueError("Staged VM manifest crosses environment pools")
    if not isinstance(manifest.get("data_reads"), list) or not all(isinstance(address, str) for address in manifest["data_reads"]):
        raise ValueError("Invalid reviewed data-source manifest")
    if not isinstance(manifest.get("intent_sha256"), str) or len(manifest["intent_sha256"]) != 64:
        raise ValueError("Invalid reviewed configuration identity")
    files = manifest.get("seed_files")
    if not isinstance(files, dict):
        raise ValueError("Missing cloud-init seed manifest")
    for path, digest in files.items():
        if (not re.fullmatch(r"\.cloud-init/[0-9a-f]{64}\.iso", path)
                or (directory / path).is_symlink() or (directory / path).resolve().parent != (directory / ".cloud-init").resolve()
                or (directory / ".cloud-init").is_symlink()
                or digest != Path(path).stem or file_hash(directory / path) != digest):
            raise ValueError("Cloud-init seed does not match the reviewed artifact")
    return manifest
