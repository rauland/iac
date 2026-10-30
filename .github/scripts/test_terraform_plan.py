"""Exercise Terraform plan exit codes using a fake CLI, without providers or state."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("terraform-plan.py").resolve()


class TerraformPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.result = self.directory / "result.json"
        self.output = self.directory / "output"
        self.arguments = self.directory / "arguments.json"
        fake = self.directory / "terraform"
        fake.write_text("""#!/usr/bin/env python3
import json, os, sys
with open(os.environ['ARGUMENTS'], 'a') as output:
    output.write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[1] == 'show':
    if '-json' in sys.argv:
        from pathlib import Path
        plan = json.loads(os.environ.get('PLAN_FIXTURE', '{"resource_changes":[]}'))
        if Path('staged').exists():
            change = plan['resource_changes'][0]['change']
            change['after']['tags'] = []
            if os.environ.get('BAD_STAGED_PLAN'):
                change['after']['cpu'] = [{'cores': 8}]
        print(json.dumps(plan))
        sys.exit(int(os.environ.get('SHOW_EXIT_CODE', '0')))
    print('  ~ resource "example" "sandbox" { password = (sensitive value) }')
    print('Plan: 0 to add, 1 to change, 0 to destroy.')
    sys.exit(int(os.environ.get('SHOW_EXIT_CODE', '0')))
if sys.argv[1] == 'plan':
    open('tfplan', 'w').write('saved plan')
    open('.terraform.lock.hcl', 'w').write('provider lock')
    if any(arg.startswith('-var=deferred_vm_tags=') for arg in sys.argv):
        open('staged', 'w').close()
sys.exit(int(os.environ['PLAN_EXIT_CODE']))
""")
        fake.chmod(0o755)

    def plan(self, exit_code, destroy="false", show_exit_code=0, fixture=None, bad_staged=False):
        env = dict(os.environ, PATH=f"{self.directory}:{os.environ['PATH']}",
                   ARGUMENTS=str(self.arguments), PLAN_EXIT_CODE=str(exit_code),
                   SHOW_EXIT_CODE=str(show_exit_code),
                   GITHUB_SHA="abc123", GITHUB_RUN_ID="42", GITHUB_RUN_ATTEMPT="2",
                   GITHUB_OUTPUT=str(self.output))
        if fixture is not None:
            env['PLAN_FIXTURE'] = json.dumps(fixture)
        if bad_staged:
            env['BAD_STAGED_PLAN'] = '1'
        return subprocess.run(
            ["python3", str(SCRIPT), "--directory", str(self.directory),
             "--environment", "dev", "--target", "sandbox", "--destroy", destroy,
             "--result", str(self.result)], env=env, text=True, capture_output=True)

    def test_empty_plan_is_success_and_reports_no_changes(self):
        result = self.plan(0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(self.result.read_text())["changes"])
        self.assertIn("changes=false", self.output.read_text())

    def test_exit_two_is_success_and_reports_changes(self):
        result = self.plan(2)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(self.result.read_text())
        self.assertTrue(data["changes"])
        self.assertEqual((data["sha"], data["run_id"], data["run_attempt"]), ("abc123", "42", "2"))
        commands = [json.loads(line) for line in self.arguments.read_text().splitlines()]
        self.assertIn("-detailed-exitcode", commands[0])
        self.assertEqual(commands[1], ["show", "-no-color", "tfplan"])
        self.assertIn("password = (sensitive value)", data["plan_text"])
        self.assertIn("Plan: 0 to add, 1 to change, 0 to destroy.", data["plan_text"])

    def test_errors_cannot_be_mistaken_for_noop(self):
        result = self.plan(1)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.result.exists())
        self.assertFalse(self.output.exists())

    def test_destroy_plan_is_explicit(self):
        result = self.plan(2, destroy="true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(self.result.read_text())["destroy"])
        self.assertIn("-destroy", json.loads(self.arguments.read_text().splitlines()[0]))

    def test_unreadable_saved_plan_does_not_publish_a_result(self):
        result = self.plan(2, show_exit_code=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.result.exists())
        self.assertFalse(self.output.exists())

    def creation_fixture(self):
        return {"resource_changes": [{
            "address": "module.vm.proxmox_virtual_environment_vm.node",
            "type": "proxmox_virtual_environment_vm", "mode": "managed",
            "change": {"actions": ["create"], "before": None,
                       "after": {"node_name": "pve", "name": "podman", "pool_id": "dev",
                                 "tags": ["sandbox", "podman"], "cpu": [{"cores": 2}]},
                       "after_unknown": {}, "after_sensitive": {}},
        }]}

    def test_new_vm_plan_publishes_final_intent_and_binds_staged_artifact(self):
        result = self.plan(2, fixture=self.creation_fixture())
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in self.arguments.read_text().splitlines()]
        plans = [call for call in calls if call[0] == "plan"]
        self.assertEqual(len(plans), 2)
        self.assertIn('-var=deferred_vm_tags=["pve/podman"]', plans[1])
        manifest = json.loads((self.directory / ".tf-tags.json").read_text())
        self.assertEqual(manifest["guests"][0]["tags"], ["podman", "sandbox"])
        self.assertEqual(manifest["guests"][0]["pool_id"], "dev")
        self.assertIn("VM tag staging:", json.loads(self.result.read_text())["plan_text"])

    def test_unreviewed_staging_difference_prevents_result_and_manifest_publication(self):
        result = self.plan(2, fixture=self.creation_fixture(), bad_staged=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.result.exists())
        self.assertFalse(self.output.exists())
        self.assertFalse((self.directory / ".tf-tags.json").exists())


if __name__ == "__main__":
    unittest.main()
