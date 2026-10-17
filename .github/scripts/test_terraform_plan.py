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
with open(os.environ['ARGUMENTS'], 'w') as output:
    json.dump(sys.argv[1:], output)
sys.exit(int(os.environ['PLAN_EXIT_CODE']))
""")
        fake.chmod(0o755)

    def plan(self, exit_code, destroy="false"):
        env = dict(os.environ, PATH=f"{self.directory}:{os.environ['PATH']}",
                   ARGUMENTS=str(self.arguments), PLAN_EXIT_CODE=str(exit_code),
                   GITHUB_SHA="abc123", GITHUB_RUN_ID="42", GITHUB_RUN_ATTEMPT="2",
                   GITHUB_OUTPUT=str(self.output))
        return subprocess.run(
            ["python3", str(SCRIPT), "--directory", str(self.directory),
             "--environment", "dev", "--target", "vault", "--destroy", destroy,
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
        self.assertIn("-detailed-exitcode", json.loads(self.arguments.read_text()))

    def test_errors_cannot_be_mistaken_for_noop(self):
        result = self.plan(1)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.result.exists())
        self.assertFalse(self.output.exists())

    def test_destroy_plan_is_explicit(self):
        result = self.plan(2, destroy="true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(self.result.read_text())["destroy"])
        self.assertIn("-destroy", json.loads(self.arguments.read_text()))


if __name__ == "__main__":
    unittest.main()
