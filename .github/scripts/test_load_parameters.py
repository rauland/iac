"""Offline checks that SSM values are masked before they reach the job environment."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

LOADER = Path(__file__).resolve().parent / "load-parameters.py"
KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\nQyNTUxOQAAACBzZWNyZXRrZXk=\n-----END OPENSSH PRIVATE KEY-----"
TOKEN = "terraform-token-0123456789abcdef"


class LoadParametersTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.responses = self.root / "responses.json"
        self.environment = self.root / "github_env"
        self.environment.touch()
        fake = self.root / "aws"
        fake.write_text("""#!/usr/bin/env python3
import json, os, sys
path = sys.argv[sys.argv.index('--path') + 1]
responses = json.load(open(os.environ['FAKE_RESPONSES']))
if path not in responses:
    sys.stderr.write(f'An error occurred (AccessDeniedException) when calling the GetParametersByPath operation: not authorized for {path}\\n')
    sys.exit(254)
print(json.dumps({'Parameters': responses[path]}))
""")
        fake.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{self.root}:{os.environ['PATH']}",
                        FAKE_RESPONSES=str(self.responses), GITHUB_ENV=str(self.environment))

    def run_loader(self, responses, *paths):
        self.responses.write_text(json.dumps(responses))
        return subprocess.run(["python3", str(LOADER), *paths], env=self.env,
                              capture_output=True, text=True)

    def parameter(self, name, value, kind="SecureString"):
        return {"Name": name, "Value": value, "Type": kind}

    def exported(self):
        values, lines = {}, iter(self.environment.read_text().splitlines())
        for line in lines:
            name, delimiter = line.split("<<", 1)
            body = []
            for item in lines:
                if item == delimiter:
                    break
                body.append(item)
            values[name] = "\n".join(body)
        return values

    def assert_values_only_in_masks(self, output, *values):
        for value in values:
            for line in value.splitlines():
                for output_line in output.splitlines():
                    if line in output_line:
                        self.assertEqual(output_line, f"::add-mask::{line}")

    def test_masks_every_line_of_multiline_secret_before_exporting(self):
        result = self.run_loader({"/iac/dev/ansible": [
            self.parameter("/iac/dev/ansible/SSH_PRIVATE_KEY_ANSIBLE", KEY)]}, "/iac/dev/ansible")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        masks = [line[len("::add-mask::"):] for line in result.stdout.splitlines() if line.startswith("::add-mask::")]
        self.assertEqual(masks, KEY.splitlines())
        self.assertEqual(self.exported()["SSH_PRIVATE_KEY_ANSIBLE"], KEY)
        self.assert_values_only_in_masks(result.stdout, KEY)

    def test_exports_leaf_names_and_does_not_mask_plain_strings(self):
        result = self.run_loader({
            "/iac/dev/plan": [self.parameter("/iac/dev/plan/TF_VAR_virtual_environment_api_token", TOKEN)],
            "/iac/dev/ansible": [self.parameter("/iac/dev/ansible/PROXMOX_TOKEN_ID_ANSIBLE", "ci", "String")],
        }, "/iac/dev/plan", "/iac/dev/ansible")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.exported(), {"TF_VAR_virtual_environment_api_token": TOKEN,
                                           "PROXMOX_TOKEN_ID_ANSIBLE": "ci"})
        self.assertIn(f"::add-mask::{TOKEN}", result.stdout)
        self.assertNotIn("::add-mask::ci", result.stdout)
        self.assert_values_only_in_masks(result.stdout, TOKEN)

    def test_rejects_short_secret_without_printing_it(self):
        result = self.run_loader({"/iac/shared/wireguard": [
            self.parameter("/iac/shared/wireguard/PEER_IP", "10.0.1")]}, "/iac/shared/wireguard")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("10.0.1", result.stdout + result.stderr)
        self.assertEqual(self.environment.read_text(), "")

    def test_failure_exports_nothing_even_after_earlier_paths_succeed(self):
        result = self.run_loader({"/iac/dev/plan": [
            self.parameter("/iac/dev/plan/TF_VAR_virtual_environment_api_token", TOKEN)]},
            "/iac/dev/plan", "/iac/prod/plan")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("/iac/prod/plan", result.stdout)
        self.assertEqual(self.environment.read_text(), "")
        self.assert_values_only_in_masks(result.stdout + result.stderr, TOKEN)

    def test_rejects_empty_paths_reserved_names_duplicates_and_unknown_types(self):
        cases = [
            ({"/iac/dev/plan": []}, "No parameters found"),
            ({"/iac/dev/plan": [self.parameter("/iac/dev/plan/PATH", TOKEN)]}, "allowed environment variable"),
            ({"/iac/dev/plan": [self.parameter("/iac/dev/plan/GITHUB_TOKEN", TOKEN)]}, "allowed environment variable"),
            ({"/iac/dev/plan": [self.parameter("/iac/dev/plan/bad-name", TOKEN)]}, "allowed environment variable"),
            ({"/iac/dev/plan": [self.parameter("/iac/dev/plan/A_TOKEN", TOKEN),
                                self.parameter("/iac/dev/plan/sub/A_TOKEN", TOKEN)]}, "duplicates"),
            ({"/iac/dev/plan": [self.parameter("/iac/dev/plan/LIST", "a,b,c", "StringList")]}, "unsupported type"),
        ]
        for responses, message in cases:
            with self.subTest(message=message):
                result = self.run_loader(responses, "/iac/dev/plan")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stdout)
                self.assertEqual(self.environment.read_text(), "")

    def test_delimiter_cannot_collide_with_value(self):
        value = "line-one-secret\nEOF\nline-three-secret"
        result = self.run_loader({"/iac/shared/apply": [
            self.parameter("/iac/shared/apply/CLOUDFLARE_API_TOKEN", value)]}, "/iac/shared/apply")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.exported()["CLOUDFLARE_API_TOKEN"], value)


if __name__ == "__main__":
    unittest.main()
