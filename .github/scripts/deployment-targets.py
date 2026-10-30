#!/usr/bin/env python3
"""Select infrastructure and configuration work independently, without credentials."""

import json
import os
from pathlib import Path
import subprocess


VM_TARGETS = {"sandbox"}
CONFIG_TARGETS = VM_TARGETS | {"common"}


def enabled_roots():
    candidates = list(Path("terraform/workloads").glob("*/*"))
    candidates.append(Path("terraform/platform/images"))
    return sorted(
        ({"environment": path.parent.name, "target": path.name,
          "directory": path.as_posix(), "terraform": False, "ansible": False,
          "destroy": False}
         for path in candidates
         if path.is_dir() and any(path.glob("*.tf"))
         and ((path.parent.name in {"dev", "prod"}
               and path.name in VM_TARGETS | {"talos", "flux"})
              or path.as_posix() == "terraform/platform/images")
         and not (path / ".disabled").exists()),
        key=lambda root: (root["environment"], root["target"]),
    )


def configuration_path(path, root):
    """Limit known service content; shared configuration reaches enabled VM targets."""
    if root["environment"] not in {"dev", "prod"} or root["target"] not in VM_TARGETS:
        return False
    if path.startswith("ssh/"):
        if path in {"ssh/setup-ci.sh", "ssh/enroll-hosts.py"}:
            return True
        if not path.startswith(("ssh/public_keys/", "ssh/known_hosts/")):
            return False
        parts = path.split("/")
        scope = parts[2] if len(parts) > 2 else ""
        return scope not in {"dev", "prod"} or scope == root["environment"]
    if path.startswith((".github/actions/ansible/", ".github/actions/ssh/")):
        return True
    if not path.startswith("ansible/"):
        return False
    if (path.startswith("ansible/tests/") or "/tests/" in path
            or path in {"ansible/.ansible-lint", "ansible/.yamllint",
                        "ansible/requirements-lint.txt"}):
        return False
    if (path.startswith("ansible/roles/podman/")
            or path == "ansible/inventory/group_vars/tag_podman.yml"):
        return root["target"] == "sandbox"
    for target in VM_TARGETS:
        if (path.startswith(f"ansible/roles/{target}/")
                or path == f"ansible/playbooks/{target}.yml"
                or path == f"ansible/inventory/group_vars/tag_{target}.yml"):
            return root["target"] == target
    return True


def infrastructure_path(path, root):
    if path.startswith(("terraform/modules/virtual-machine/cloud-init/", "terraform/modules/virtual-machine/scripts/")):
        return root["target"] in VM_TARGETS
    if path in {".github/scripts/terraform-plan.py", ".github/scripts/terraform-apply.py",
                ".github/scripts/vm_tags.py", ".github/scripts/terraform-plan-artifact.sh"}:
        return True
    if path.startswith("ssh/public_keys/"):
        parts = path.split("/")
        return len(parts) > 2 and parts[2] == root["environment"]
    if not (path.endswith((".tf", ".tfvars", ".tfvars.json"))
            or Path(path).name == ".terraform.lock.hcl"):
        return False
    return path.startswith((root["directory"] + "/", "terraform/modules/"))


def changed_targets(roots, paths):
    selected = []
    for root in roots:
        entry = dict(root)
        for path in paths:
            if path.endswith(".md") or "/tests/" in path:
                continue
            entry["terraform"] |= infrastructure_path(path, root)
            entry["ansible"] |= configuration_path(path, root)
        if entry["terraform"] or entry["ansible"]:
            selected.append(entry)
    return selected


def discover():
    roots = enabled_roots()
    if os.environ["EVENT_NAME"] == "workflow_dispatch":
        if os.environ.get("GITHUB_REF") != "refs/heads/main":
            raise SystemExit("Manual deployments must run from main")
        mode = os.environ.get("DEPLOYMENT_MODE", "auto")
        scope = os.environ.get("DEPLOYMENT_SCOPE", "single")
        environment = os.environ.get("SELECTED_ENV", "")
        target = os.environ.get("SELECTED_TARGET", "")
        if mode not in {"auto", "infrastructure", "configuration", "destroy"}:
            raise SystemExit("Unsupported deployment mode")
        if scope not in {"single", "all"} or environment not in {"dev", "prod", "platform"}:
            raise SystemExit("Invalid deployment scope or environment")
        if mode == "configuration" and scope == "single":
            if environment not in {"dev", "prod"} or target not in CONFIG_TARGETS:
                raise SystemExit("Configuration requires dev/prod and common/sandbox")
            root = next((root for root in roots if root["environment"] == environment
                         and root["target"] == target), None)
            directory = Path(f"terraform/workloads/{environment}/{target}")
            if (directory / ".disabled").exists():
                raise SystemExit("The selected target is disabled")
            return [dict(root or {"environment": environment, "target": target,
                                  "directory": "", "destroy": False},
                         terraform=False, ansible=True)]
        selected = [dict(root) for root in roots
                    if root["environment"] == environment
                    and (scope == "all" or root["target"] == target)
                    and (mode != "configuration" or root["target"] in VM_TARGETS)]
        if not selected:
            raise SystemExit("No enabled deployment targets found for selected scope")
        for entry in selected:
            entry["terraform"] = mode != "configuration"
            entry["ansible"] = (mode in {"auto", "configuration"}
                                and entry["target"] in VM_TARGETS)
            entry["destroy"] = mode == "destroy"
        return selected

    base = os.environ.get("BASE_SHA", "")
    head = os.environ["HEAD_SHA"]
    if not base or set(base) == {"0"}:
        return [dict(root, terraform=True, ansible=root["target"] in VM_TARGETS)
                for root in roots]
    revision = (f"{base}...{head}" if os.environ["EVENT_NAME"] == "pull_request"
                else f"{base}..{head}")
    paths = subprocess.check_output(
        ["git", "diff", "--name-only", "--no-renames", "-z", revision],
    ).decode().split("\0")
    return changed_targets(roots, [path for path in paths if path])


if __name__ == "__main__":
    targets = discover()
    plans = [target for target in targets if target["terraform"]]
    values = {"matrix": json.dumps(targets, separators=(",", ":")),
              "plan-matrix": json.dumps(plans, separators=(",", ":")),
              "has-targets": str(bool(targets)).lower(),
              "has-plans": str(bool(plans)).lower()}
    if len(targets) == 1 and targets[0]["directory"]:
        values["directory"] = targets[0]["directory"]
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        for name, value in values.items():
            output.write(f"{name}={value}\n")
    print(f"Selected deployment work: {values['matrix']}")
