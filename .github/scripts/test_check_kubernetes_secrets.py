"""Offline tests for the unencrypted Secret check."""

from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("check-kubernetes-secrets.py").resolve()
SECRET = "apiVersion: v1\nkind: Secret\nmetadata:\n  name: demo\nstringData:\n  password: {value}\n"
SOPS = ("sops:\n    age:\n        - recipient: age1example\n"
        "    mac: ENC[AES256_GCM,data:abc,type:str]\n")


class CheckSecretsTests(unittest.TestCase):
    def check(self, files):
        with tempfile.TemporaryDirectory() as directory:
            for name, text in files.items():
                path = Path(directory) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            return subprocess.run(["python3", str(SCRIPT), directory],
                                  capture_output=True, text=True)

    def test_encrypted_secret_and_other_manifests_pass(self):
        result = self.check({
            "clusters/dev/app.sops.yaml": SECRET.format(value="ENC[AES256_GCM,data:x,type:str]") + SOPS,
            "clusters/dev/kustomization.yaml": "resources: []\n",
            "clusters/dev/config.yaml": "kind: ConfigMap\ndata:\n  secretName: demo\n",
        })
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_plain_secret_fails(self):
        result = self.check({"clusters/dev/app.yaml": SECRET.format(value="hunter2")})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("plain Secret", result.stdout)

    def test_unencrypted_sops_file_fails(self):
        result = self.check({"clusters/dev/app.sops.yaml": SECRET.format(value="hunter2")})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not SOPS-encrypted", result.stdout)

    def test_sops_file_without_age_recipient_fails(self):
        text = SECRET.format(value="ENC[AES256_GCM,data:x,type:str]") + "sops:\n    pgp: []\n"
        result = self.check({"clusters/dev/app.sops.yaml": text})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no age recipient", result.stdout)


if __name__ == "__main__":
    unittest.main()
