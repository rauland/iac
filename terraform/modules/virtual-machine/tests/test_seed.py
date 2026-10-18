"""Check actual seed bytes, guest policy boundaries and cross-run reproducibility."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import pycdlib


MODULE = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed = load("seed", MODULE / "scripts/build-seed.py")
policy = load("policy", MODULE / "cloud-init/agent-policy.py")


class SeedTests(unittest.TestCase):
    def setUp(self):
        self.files = {"user-data": "#cloud-config\nssh_pwauth: false\n",
                      "meta-data": "instance-id: dev/pve/test\n",
                      "network-config": "version: 2\n"}

    def test_iso_contains_exact_documents_under_cidata_label(self):
        iso = pycdlib.PyCdlib()
        iso.open_fp(io.BytesIO(seed.build(self.files)))
        self.assertEqual(iso.pvd.volume_identifier.strip(), b"CIDATA")
        for name, contents in self.files.items():
            result = io.BytesIO()
            iso.get_file_from_iso_fp(result, rr_path="/" + name)
            self.assertEqual(result.getvalue(), contents.encode())
        iso.close()

    def test_cross_directory_timezone_and_clock_changes_do_not_change_iso(self):
        outputs = []
        for timezone in ("UTC", "Australia/Melbourne"):
            with tempfile.TemporaryDirectory() as directory:
                result = subprocess.run(["python3", str(MODULE / "scripts/build-seed.py")],
                    cwd=directory, env=dict(os.environ, TZ=timezone), input=json.dumps(self.files),
                    capture_output=True, text=True, check=True)
                metadata = json.loads(result.stdout)
                contents = (Path(directory) / metadata["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(contents).hexdigest(), metadata["sha256"])
                outputs.append(contents)
        self.assertEqual(*outputs)
        changed = dict(self.files, **{"user-data": "#cloud-config\nssh_pwauth: true\n"})
        self.assertNotEqual(seed.build(changed), outputs[0])

    def test_malformed_document_set_is_rejected(self):
        with self.assertRaises(ValueError):
            seed.build(dict(self.files, **{"../../outside": "bad"}))


class AgentPolicyTests(unittest.TestCase):
    def configure(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qemu-ga"
            path.write_text(text)
            policy.configure(path)
            result = path.read_text()
            policy.configure(path)
            self.assertEqual(result, path.read_text())
            return result

    def test_allow_list_adds_only_read_rpcs_and_retains_other_settings(self):
        result = self.configure('FILTER_RPC_ARGS="--allow-rpcs=guest-ping,guest-info"\nFSFREEZE_HOOK_PATHNAME=/test\n')
        self.assertIn('guest-file-close,guest-file-open,guest-file-read,guest-info,guest-ping', result)
        self.assertIn('FSFREEZE_HOOK_PATHNAME=/test', result)
        self.assertNotIn('guest-file-write', result)
        self.assertNotIn('guest-exec', result)

    def test_block_list_retains_exec_and_file_write_restrictions(self):
        result = self.configure('FILTER_RPC_ARGS="--block-rpcs=guest-file-open,guest-file-read,guest-file-close,guest-file-write,guest-exec,guest-exec-status"\n')
        self.assertEqual(result, 'FILTER_RPC_ARGS="--block-rpcs=guest-exec,guest-exec-status,guest-file-write"\n')

    def test_unknown_or_already_unrestricted_policy_is_not_weakened(self):
        for text in ('FILTER_RPC_ARGS=""\n', 'OTHER=value\n',
                     'FILTER_RPC_ARGS="--allow-rpcs=guest-ping,guest-exec"\n',
                     'FILTER_RPC_ARGS="--block-rpcs=guest-file-open"\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.configure(text)


if __name__ == "__main__":
    unittest.main()
