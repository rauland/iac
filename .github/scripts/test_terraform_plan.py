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
    print('  ~ resource "example" "talos" { password = (sensitive value) }')
    print('Plan: 0 to add, 1 to change, 0 to destroy.')
    sys.exit(int(os.environ.get('SHOW_EXIT_CODE', '0')))
if sys.argv[1] == 'plan':
    open('tfplan', 'w').write('saved plan')
    open('.terraform.lock.hcl', 'w').write('provider lock')
sys.exit(int(os.environ['PLAN_EXIT_CODE']))
""")
        fake.chmod(0o755)

    def plan(self, exit_code, destroy="false", show_exit_code=0):
        env = dict(os.environ, PATH=f"{self.directory}:{os.environ['PATH']}",
                   ARGUMENTS=str(self.arguments), PLAN_EXIT_CODE=str(exit_code),
                   SHOW_EXIT_CODE=str(show_exit_code),
                   GITHUB_SHA="abc123", GITHUB_RUN_ID="42", GITHUB_RUN_ATTEMPT="2",
                   GITHUB_OUTPUT=str(self.output))
        return subprocess.run(
            ["python3", str(SCRIPT), "--directory", str(self.directory),
             "--environment", "dev", "--target", "talos", "--destroy", destroy,
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

    def test_manifest_binds_plan_lock_target_and_run(self):
        result = self.plan(2)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((self.directory / ".tf-plan.json").read_text())
        self.assertEqual((manifest["environment"], manifest["target"], manifest["destroy"]),
                         ("dev", "talos", False))
        self.assertEqual((manifest["sha"], manifest["run_id"], manifest["run_attempt"]),
                         ("abc123", "42", "2"))
        self.assertEqual(len(manifest["plan_sha256"]), 64)
        calls = [json.loads(line) for line in self.arguments.read_text().splitlines()]
        self.assertEqual(len([call for call in calls if call[0] == "plan"]), 1)


if __name__ == "__main__":
    unittest.main()
