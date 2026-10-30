"""Regression checks for pool-scoped staging and the follow-up plan's mutation boundary."""

import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import vm_tags


ADDRESS = 'module.virtual_machine["podman"].proxmox_virtual_environment_vm.node'
VALUES = {"node_name": "pve", "name": "podman", "pool_id": "dev", "vm_id": 108,
          "tags": ["common", "podman", "sandbox"], "cpu": [{"cores": 2}],
          "agent": [{"enabled": True}], "id": "108"}


def resource(actions, before, after, address=ADDRESS):
    return {"address": address, "mode": "managed", "type": vm_tags.VM_TYPE,
            "change": {"actions": actions, "before": before, "after": after,
                       "after_unknown": {}, "after_sensitive": {}}}


def creation():
    values = dict(VALUES, vm_id=None, id=None)
    result = resource(["create"], None, values)
    result["change"]["after_unknown"] = {"vm_id": True, "id": True}
    result["change"]["after_sensitive"] = {"tags": [False] * len(VALUES["tags"])}
    return {"resource_changes": [result]}


def tag_plan():
    return {"resource_changes": [resource(["update"], dict(VALUES, tags=[]), dict(VALUES))]}


def state(tags):
    return {"values": {"root_module": {"child_modules": [{"resources": [
        {"address": ADDRESS, "values": dict(VALUES, tags=tags)}]}]}}}


class TagPlanBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.reviewed = creation()
        self.guests = vm_tags.deferred_guests(self.reviewed, "dev")
        self.bound = vm_tags.bind_created_guests(state([]), self.guests)

    def test_only_new_or_replaced_tagged_vms_are_deferred(self):
        self.reviewed["resource_changes"].extend([
            resource(["update"], VALUES, VALUES, "existing"),
            resource(["delete"], VALUES, None, "removed"),
            resource(["create"], None, dict(VALUES, tags=[]), "untagged")])
        self.assertEqual(vm_tags.deferred_guests(self.reviewed, "dev"), self.guests)
        for actions in (["delete", "create"], ["create", "delete"]):
            self.reviewed["resource_changes"][0]["change"]["actions"] = actions
            self.assertEqual(vm_tags.deferred_guests(self.reviewed, "dev"), self.guests)

    def test_unknown_or_cross_environment_identity_is_denied_before_staging(self):
        for key, value in (("pool_id", "prod"), ("node_name", None), ("name", None)):
            plan = creation()
            plan["resource_changes"][0]["change"]["after"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                vm_tags.deferred_guests(plan, "dev")
        plan = creation()
        plan["resource_changes"][0]["change"]["after"]["tags"] = None
        plan["resource_changes"][0]["change"]["after_unknown"]["tags"] = True
        with self.assertRaises(ValueError):
            vm_tags.deferred_guests(plan, "dev")

    def test_reviewed_plan_cannot_already_suppress_tags(self):
        plan = creation()
        plan["variables"] = {"deferred_vm_tags": {"value": ["pve/podman"]}}
        with self.assertRaises(ValueError):
            vm_tags.deferred_guests(plan, "dev")

    def test_infrastructure_plan_may_only_suppress_reviewed_create_tags(self):
        staged = copy.deepcopy(self.reviewed)
        staged["resource_changes"][0]["change"]["after"]["tags"] = []
        staged["resource_changes"][0]["change"]["after_sensitive"]["tags"] = []
        vm_tags.validate_infrastructure_plan(self.reviewed, staged, self.guests)
        staged["resource_changes"][0]["change"]["after"]["cpu"] = [{"cores": 8}]
        with self.assertRaises(ValueError):
            vm_tags.validate_infrastructure_plan(self.reviewed, staged, self.guests)

    def test_plan_resource_output_or_action_changes_cannot_hide_in_deferral(self):
        for mutation in ("resource", "output", "action"):
            staged = copy.deepcopy(self.reviewed)
            staged["resource_changes"][0]["change"]["after"]["tags"] = []
            if mutation == "resource":
                staged["resource_changes"].append(resource(["delete"], VALUES, None, "other"))
            elif mutation == "output":
                staged["output_changes"] = {"endpoint": {"actions": ["update"], "after": "other"}}
            else:
                staged["resource_changes"][0]["change"]["actions"] = ["delete", "create"]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                vm_tags.validate_infrastructure_plan(self.reviewed, staged, self.guests)

    def test_created_state_must_match_node_name_pool_and_fixed_vm_id(self):
        for key, value in (("node_name", "other"), ("name", "other"), ("pool_id", "prod"), ("vm_id", None)):
            observed = state([])
            observed["values"]["root_module"]["child_modules"][0]["resources"][0]["values"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                vm_tags.bind_created_guests(observed, self.guests)
        fixed = copy.deepcopy(self.guests)
        fixed[0]["vm_id"] = 999
        with self.assertRaises(ValueError):
            vm_tags.bind_created_guests(state([]), fixed)

    def test_tag_only_update_accepts_known_nested_masks_and_computed_observations(self):
        plan = tag_plan()
        change = plan["resource_changes"][0]["change"]
        change["after_unknown"] = {"cpu": [{}], "agent": [{}], "ipv4_addresses": True}
        change["before"]["ipv4_addresses"] = [["10.0.0.50"]]
        change["after"]["ipv4_addresses"] = None
        change["before"]["cpu"] = [{"cores": 2, "flags": None}]
        change["after"]["cpu"] = [{"cores": 2, "flags": []}]
        vm_tags.validate_tag_plan(plan, self.bound)

    def test_wrong_tags_identity_settings_unknowns_or_actions_are_rejected(self):
        for key, value in (("tags", ["prod"]), ("vm_id", 999), ("pool_id", "prod"),
                           ("node_name", "other"), ("cpu", [{"cores": 8}]),
                           ("cpu", [{"cores": 2, "flags": ["+aes"]}])):
            plan = tag_plan()
            plan["resource_changes"][0]["change"]["after"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                vm_tags.validate_tag_plan(plan, self.bound)
        for actions in (["create"], ["delete"], ["delete", "create"]):
            plan = tag_plan()
            plan["resource_changes"][0]["change"]["actions"] = actions
            with self.subTest(actions=actions), self.assertRaises(ValueError):
                vm_tags.validate_tag_plan(plan, self.bound)
        plan = tag_plan()
        plan["resource_changes"][0]["change"]["after_unknown"] = {"cpu": [{"cores": True}]}
        with self.assertRaises(ValueError):
            vm_tags.validate_tag_plan(plan, self.bound)

    def test_unrelated_mutations_or_missing_staged_vm_abort_tag_apply(self):
        plan = tag_plan()
        plan["resource_changes"].append(resource(["update"], VALUES, VALUES, "other"))
        with self.assertRaises(ValueError):
            vm_tags.validate_tag_plan(plan, self.bound)
        with self.assertRaises(ValueError):
            vm_tags.validate_tag_plan({"resource_changes": []}, self.bound)

    def test_only_reviewed_read_only_data_sources_can_run_again(self):
        plan = tag_plan()
        health = resource(["read"], None, {}, "module.talos.data.talos_cluster_health.this")
        health.update(mode="data", type="talos_cluster_health")
        plan["resource_changes"].append(health)
        with self.assertRaises(ValueError):
            vm_tags.validate_tag_plan(plan, self.bound)
        vm_tags.validate_tag_plan(plan, self.bound, [health["address"]])
        health["mode"] = "managed"
        with self.assertRaises(ValueError):
            vm_tags.validate_tag_plan(plan, self.bound, [health["address"]])

    def test_incomplete_plans_and_additional_action_invocations_are_denied(self):
        for extra in ({"complete": False}, {"errored": True}, {"deferred_changes": [{}]},
                      {"action_invocations": [{"address": "action.unreviewed"}]}):
            plan = tag_plan()
            plan.update(extra)
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                vm_tags.validate_tag_plan(plan, self.bound)
        for mutation in ("import", "move"):
            plan = tag_plan()
            other = resource(["no-op"], VALUES, VALUES, "unrelated")
            if mutation == "import":
                other["change"]["importing"] = {"id": "pve/999"}
            else:
                other["previous_address"] = "old_address"
            plan["resource_changes"].append(other)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                vm_tags.validate_tag_plan(plan, self.bound)

    def test_provider_endpoint_and_configuration_must_match_reviewed_intent(self):
        plan = tag_plan()
        plan["variables"] = {"virtual_environment_endpoint": {"value": "https://pve.invalid:8006"}}
        plan["configuration"] = {"provider_config": {"proxmox": {"name": "proxmox"}}}
        digest = vm_tags.plan_intent_hash(plan)
        vm_tags.validate_tag_plan(plan, self.bound, intent_sha256=digest)
        changed = copy.deepcopy(plan)
        changed["variables"]["virtual_environment_endpoint"]["value"] = "https://other.invalid:8006"
        with self.assertRaises(ValueError):
            vm_tags.validate_tag_plan(changed, self.bound, intent_sha256=digest)
        changed = copy.deepcopy(plan)
        changed["configuration"]["provider_config"]["proxmox"]["name"] = "other"
        with self.assertRaises(ValueError):
            vm_tags.validate_tag_plan(changed, self.bound, intent_sha256=digest)
        plan["variables"].update(deferred_vm_tags={"value": []},
                                 virtual_environment_api_token={"value": "apply-token"})
        vm_tags.validate_tag_plan(plan, self.bound, intent_sha256=digest)


class ApplySequenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.context = {"GITHUB_SHA": "abc123", "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1"}
        self.log = self.directory / "commands.jsonl"
        (self.directory / "tfplan").write_text("reviewed infrastructure")
        (self.directory / ".terraform.lock.hcl").write_text("reviewed provider lock")
        (self.directory / "tags.json").write_text(json.dumps(tag_plan()))
        (self.directory / "before.json").write_text(json.dumps(state([])))
        (self.directory / "after.json").write_text(json.dumps(state(VALUES["tags"])))
        self.guests = vm_tags.deferred_guests(creation(), "dev")
        self.manifest()
        cli = self.directory / "terraform"
        cli.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
with open(os.environ['LOG'], 'a') as stream:
    stream.write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[1] == 'apply':
    if sys.argv[-1] == 'tfplan':
        if os.environ.get('INFRA_EXIT_CODE'):
            sys.exit(int(os.environ['INFRA_EXIT_CODE']))
        Path('created').touch()
    else:
        if os.environ.get('TAG_EXIT_CODE'):
            sys.exit(int(os.environ['TAG_EXIT_CODE']))
        Path('tagged').touch()
elif sys.argv[1] == 'plan':
    Path('tfplan.tags').write_text('tag-only plan')
    sys.exit(2)
elif sys.argv[1] == 'show':
    filename = 'tags.json' if sys.argv[-1] == 'tfplan.tags' else ('after.json' if Path('tagged').exists() else 'before.json')
    print(Path(filename).read_text())
''')
        cli.chmod(0o755)

    def manifest(self, guests=None, destroy=False):
        vm_tags.write_manifest(self.directory, self.guests if guests is None else guests,
                               self.context, "dev", "sandbox", destroy)

    def apply(self, **context):
        env = dict(os.environ, **self.context, PATH=f"{self.directory}:{os.environ['PATH']}", LOG=str(self.log))
        env.update(context)
        return subprocess.run(["python3", str(Path(__file__).with_name("terraform-apply.py")),
                               "--directory", str(self.directory), "--environment", "dev", "--target", "sandbox"],
                              env=env, capture_output=True, text=True)

    def test_saved_infrastructure_precedes_validated_saved_tag_plan(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual(calls[0], ["apply", "-input=false", "tfplan"])
        self.assertTrue((self.directory / "created").exists())
        self.assertTrue((self.directory / "tagged").exists())
        tag_apply = next(i for i, call in enumerate(calls) if call == ["apply", "-input=false", "tfplan.tags"])
        self.assertIn(["show", "-json", "tfplan.tags"], calls[:tag_apply])
        self.assertIn("-refresh=false", next(call for call in calls if call[0] == "plan"))

    def test_unrelated_followup_change_leaves_created_state_and_never_applies_tags(self):
        plan = tag_plan()
        plan["resource_changes"].append(resource(["delete"], VALUES, None, "unexpected"))
        (self.directory / "tags.json").write_text(json.dumps(plan))
        result = self.apply()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.directory / "created").exists())
        self.assertFalse((self.directory / "tagged").exists())

    def test_wrong_run_or_tampered_plan_or_lock_fail_before_any_mutation(self):
        result = self.apply(GITHUB_RUN_ATTEMPT="2")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())
        for name in ("tfplan", ".terraform.lock.hcl"):
            self.manifest()
            (self.directory / name).write_text("tampered")
            result = self.apply()
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.log.exists())

    def test_seed_checksum_is_bound_to_the_plan_and_checked_before_apply(self):
        content = b'exact reviewed cloud-init ISO'
        import hashlib
        digest = hashlib.sha256(content).hexdigest()
        relative = '.cloud-init/' + digest + '.iso'
        path = self.directory / relative
        path.parent.mkdir()
        path.write_bytes(content)
        reviewed = {'planned_values': {'root_module': {'resources': [{
            'type': 'proxmox_virtual_environment_file', 'values': {
                'source_file': [{'path': relative, 'checksum': digest}]}}]}}}
        vm_tags.write_manifest(self.directory, self.guests, self.context, 'dev', 'sandbox', False,
                               reviewed_plan=reviewed)
        self.assertEqual(vm_tags.read_manifest(self.directory, self.context, 'dev', 'sandbox', False)['seed_files'],
                         {relative: digest})
        path.write_bytes(b'tampered ISO')
        result = self.apply()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())
        with self.assertRaises(ValueError):
            vm_tags.write_manifest(self.directory, self.guests, self.context, 'dev', 'sandbox', False,
                                   reviewed_plan=reviewed)

    def test_malformed_or_cross_pool_manifest_fails_before_any_mutation(self):
        original = json.loads((self.directory / vm_tags.MANIFEST).read_text())
        for mutation in ("pool", "tags", "selector", "duplicate", "version", "target"):
            manifest = copy.deepcopy(original)
            if mutation == "pool":
                manifest["guests"][0]["pool_id"] = "prod"
            elif mutation == "tags":
                manifest["guests"][0].pop("tags")
            elif mutation == "selector":
                manifest["guests"][0]["selector"] = "pve/other"
            elif mutation == "duplicate":
                manifest["guests"].append(manifest["guests"][0])
            elif mutation == "version":
                manifest["version"] = True
            else:
                manifest["target"] = "talos"
            (self.directory / vm_tags.MANIFEST).write_text(json.dumps(manifest))
            with self.subTest(mutation=mutation):
                result = self.apply()
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.log.exists())

    def test_infrastructure_failure_stops_before_tag_planning(self):
        result = self.apply(INFRA_EXIT_CODE="7")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([json.loads(line) for line in self.log.read_text().splitlines()],
                         [["apply", "-input=false", "tfplan"]])
        self.assertFalse((self.directory / "created").exists())

    def test_tag_apply_failure_preserves_created_state_and_stops_verification(self):
        result = self.apply(TAG_EXIT_CODE="7")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.directory / "created").exists())
        self.assertFalse((self.directory / "tagged").exists())
        self.assertEqual(json.loads(self.log.read_text().splitlines()[-1]),
                         ["apply", "-input=false", "tfplan.tags"])

    def test_existing_vm_updates_need_only_the_original_saved_plan(self):
        self.manifest(guests=[])
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([json.loads(line) for line in self.log.read_text().splitlines()],
                         [["apply", "-input=false", "tfplan"]])


if __name__ == "__main__":
    unittest.main()
