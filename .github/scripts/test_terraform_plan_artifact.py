"""Offline tests for encrypted Terraform plan transfer; no cloud access."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("terraform-plan-artifact.sh").resolve()


class PlanArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.key_home = cls.base / "keys"
        cls.key_home.mkdir(mode=0o700)
        cls.gpg("--batch", "--passphrase", "", "--quick-generate-key",
                "Plan artifact test", "rsa2048", "encr", "1d")
        cls.public = cls.gpg("--armor", "--export").stdout
        cls.private = cls.gpg("--batch", "--pinentry-mode", "loopback",
                              "--passphrase", "", "--armor", "--export-secret-keys").stdout

    @classmethod
    def gpg(cls, *args):
        return subprocess.run(["gpg", "--homedir", str(cls.key_home), *args],
                              check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["gpgconf", "--homedir", str(cls.key_home), "--kill", "all"],
                       check=True, capture_output=True)
        cls.temp.cleanup()

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(dir=self.base)
        self.root = Path(self.workspace.name)
        self.source = self.root / "source"
        self.destination = self.root / "destination"
        self.source.mkdir()
        self.destination.mkdir()
        (self.source / "tfplan").write_bytes(b"secret plan contents\x00\xff")
        (self.source / ".terraform.lock.hcl").write_text("exact provider selections\n")
        (self.source / ".tf-plan.json").write_text('{"version":2}\n')
        self.artifact = self.root / "tfplan.tar.gpg"

    def tearDown(self):
        self.workspace.cleanup()

    def run_script(self, mode, root, **overrides):
        env = dict(os.environ)
        env.pop("TF_PLAN_PUBLIC_KEY", None)
        env.pop("TF_PLAN_PRIVATE_KEY", None)
        env.update(overrides)
        return subprocess.run(["bash", str(SCRIPT), mode, str(root), str(self.artifact)],
                              env=env, capture_output=True, text=True)

    def encrypt(self):
        result = self.run_script("encrypt", self.source, TF_PLAN_PUBLIC_KEY=self.public)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_round_trip_restores_plan_and_lock(self):
        self.encrypt()
        self.assertNotIn(b"secret plan contents", self.artifact.read_bytes())
        result = self.run_script("decrypt", self.destination, TF_PLAN_PRIVATE_KEY=self.private)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("tfplan", ".terraform.lock.hcl", ".tf-plan.json"):
            self.assertEqual((self.source / name).read_bytes(),
                             (self.destination / name).read_bytes())

    def test_missing_key_fails(self):
        for mode in ("encrypt", "decrypt"):
            result = self.run_script(mode, self.source)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Set ", result.stderr)

    def test_corrupt_ciphertext_fails_before_extracting(self):
        self.encrypt()
        data = bytearray(self.artifact.read_bytes())
        data[-1] ^= 1
        self.artifact.write_bytes(data)
        result = self.run_script("decrypt", self.destination, TF_PLAN_PRIVATE_KEY=self.private)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_missing_lock_fails(self):
        (self.source / ".terraform.lock.hcl").unlink()
        result = self.run_script("encrypt", self.source, TF_PLAN_PUBLIC_KEY=self.public)
        self.assertNotEqual(result.returncode, 0)

    def test_missing_tag_manifest_fails(self):
        (self.source / ".tf-plan.json").unlink()
        result = self.run_script("encrypt", self.source, TF_PLAN_PUBLIC_KEY=self.public)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
