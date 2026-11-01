"""The apply helper refuses any saved plan that is not the reviewed one for this target and run."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import importlib.util

SPEC = importlib.util.spec_from_file_location("plan_manifest", Path(__file__).with_name("plan_manifest.py"))
plan_manifest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plan_manifest)


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.context = {"GITHUB_SHA": "abc123", "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1"}
        self.log = self.directory / "commands.jsonl"
        (self.directory / "tfplan").write_text("reviewed plan")
        (self.directory / ".terraform.lock.hcl").write_text("reviewed provider lock")
        plan_manifest.write_manifest(self.directory, self.context, "dev", "talos", False)
        cli = self.directory / "terraform"
        cli.write_text("""#!/usr/bin/env python3
import json, os, sys
with open(os.environ['LOG'], 'a') as stream:
    stream.write(json.dumps(sys.argv[1:]) + '\\n')
""")
        cli.chmod(0o755)

    def apply(self, destroy="false", **context):
        env = dict(os.environ, **self.context, PATH=f"{self.directory}:{os.environ['PATH']}", LOG=str(self.log))
        env.update(context)
        return subprocess.run(["python3", str(Path(__file__).with_name("terraform-apply.py")),
                               "--directory", str(self.directory), "--environment", "dev",
                               "--target", "talos", "--destroy", destroy],
                              env=env, capture_output=True, text=True)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_reviewed_plan_is_applied_once(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [["apply", "-input=false", "tfplan"]])

    def test_wrong_run_target_mode_or_tampered_files_never_apply(self):
        for case in ("run", "destroy", "plan", "lock"):
            with self.subTest(case=case):
                if case == "plan":
                    (self.directory / "tfplan").write_text("swapped plan")
                elif case == "lock":
                    (self.directory / ".terraform.lock.hcl").write_text("swapped lock")
                result = (self.apply(GITHUB_RUN_ATTEMPT="2") if case == "run"
                          else self.apply(destroy="true") if case == "destroy" else self.apply())
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.calls(), [])
                (self.directory / "tfplan").write_text("reviewed plan")
                (self.directory / ".terraform.lock.hcl").write_text("reviewed provider lock")

    def test_missing_manifest_never_applies(self):
        (self.directory / plan_manifest.MANIFEST).unlink()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
