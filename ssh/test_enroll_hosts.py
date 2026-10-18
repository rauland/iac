"""Exercise host enrollment identity checks and failure behavior without infrastructure."""

import base64
import copy
import importlib.util
from pathlib import Path
import stat
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests


SPEC = importlib.util.spec_from_file_location("enroll_hosts", Path(__file__).with_name("enroll-hosts.py"))
enrollment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(enrollment)
KEY = "ssh-ed25519 " + base64.b64encode(
    struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32) + bytes(range(32))).decode()


class EnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.trust = self.root / "committed_known_hosts"
        self.trust.write_text("# Verified hosts\n")
        self.output = self.root / "runtime known_hosts"
        self.values = {"ansible_host": "10.0.0.10", "proxmox_node": "pve",
                       "proxmox_vmid": 113, "proxmox_vmtype": "qemu"}
        self.inventory = {
            "_meta": {"hostvars": {"sandbox": self.values}},
            "proxmox_pool_dev": {"children": ["dev_children"]},
            "dev_children": {"hosts": ["sandbox"]},
            "tag_sandbox": {"hosts": ["sandbox"]},
        }
        self.load_guests = Mock(return_value={("pve", 113, "sandbox"): {}})
        self.api = Mock()
        self.api.get.side_effect = self.response
        self.api_factory = Mock(return_value=self.api)

    def response(self, path, **kwargs):
        return {
            "/pools/dev": {"members": [{"node": "pve", "vmid": 113, "type": "qemu"}]},
            "/nodes/pve/qemu/113/config": {"name": "sandbox", "tags": "common;sandbox"},
            "/nodes/pve/qemu/113/agent/file-read": {"content": KEY + " root@sandbox\n"},
        }[path]

    def enroll(self, environment="dev", target="sandbox"):
        return enrollment.enroll(self.inventory, self.root, environment, target,
                                 self.trust, self.output, self.load_guests, self.api_factory)

    def test_matching_vm_uses_only_public_file_read_and_private_runtime_file(self):
        self.assertEqual(self.enroll(), 1)
        self.assertEqual(self.output.read_text(), f"# Verified hosts\n10.0.0.10 {KEY}\n")
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.api.get.assert_any_call(
            "/nodes/pve/qemu/113/agent/file-read",
            params={"file": "/etc/ssh/ssh_host_ed25519_key.pub", "decode": 1}, retry_agent=True)
        self.assertEqual(self.trust.read_text(), "# Verified hosts\n")

    def test_existing_pins_are_authoritative_and_do_not_require_agent_or_apply_access(self):
        self.trust.write_text(f"10.0.0.10 {KEY}\n")
        self.assertEqual(self.enroll(), 0)
        self.assertEqual(self.output.read_text(), self.trust.read_text())
        self.api_factory.assert_not_called()
        self.load_guests.assert_not_called()

    def test_pinned_external_guest_without_agent_or_terraform_metadata_is_supported(self):
        self.inventory["_meta"]["hostvars"]["sandbox"] = {"ansible_host": "10.0.0.10"}
        self.trust.write_text(f"10.0.0.10 {KEY}\n")
        self.load_guests.side_effect = AssertionError("External guest has no Terraform state")
        self.api_factory.side_effect = AssertionError("Guest-agent access is unavailable")
        self.assertEqual(self.enroll(), 0)
        self.assertEqual(self.output.read_text(), self.trust.read_text())
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)

    def test_hashed_and_wildcard_pins_are_preserved(self):
        self.trust.write_text(f"10.0.0.10 {KEY}\n")
        subprocess.run(["ssh-keygen", "-H", "-f", str(self.trust)],
                       check=True, capture_output=True)
        self.assertEqual(self.enroll(), 0)
        self.api_factory.assert_not_called()
        self.output.unlink()
        self.trust.write_text(f"10.0.0.* {KEY}\n")
        self.assertEqual(self.enroll(), 0)
        self.api_factory.assert_not_called()

    def test_other_environment_and_untagged_hosts_are_excluded(self):
        self.inventory["_meta"]["hostvars"]["prod"] = dict(self.values, ansible_host="10.0.0.20")
        self.inventory["proxmox_pool_prod"] = {"hosts": ["prod"]}
        self.inventory["tag_sandbox"]["hosts"].append("prod")
        self.inventory["dev_children"]["hosts"].append("untagged")
        self.assertEqual(self.enroll(), 1)
        self.assertNotIn("10.0.0.20", self.output.read_text())

    def test_no_matching_hosts_does_not_access_proxmox(self):
        self.assertEqual(self.enroll(environment="prod"), 0)
        self.api_factory.assert_not_called()
        self.load_guests.assert_not_called()

    def test_unknown_state_wrong_vm_name_node_id_and_non_qemu_are_denied(self):
        for changes in ({"proxmox_vmid": 999}, {"proxmox_node": "other"},
                        {"proxmox_vmtype": "lxc"}):
            with self.subTest(changes=changes):
                self.inventory["_meta"]["hostvars"]["sandbox"] = dict(self.values, **changes)
                with self.assertRaises(enrollment.EnrollmentError):
                    self.enroll()
                self.assertFalse(self.output.exists())
        self.inventory["_meta"]["hostvars"]["sandbox"] = self.values
        self.load_guests.return_value = {}
        with self.assertRaises(enrollment.EnrollmentError):
            self.enroll()
        self.assertFalse(self.output.exists())

    def test_guest_removed_from_live_pool_or_retagged_is_denied(self):
        for response in ({"members": []}, {"members": [{"node": "pve", "vmid": 113, "type": "lxc"}]}):
            self.api.get.side_effect = lambda path, **kwargs: response
            with self.assertRaises(enrollment.EnrollmentError):
                self.enroll()
            self.assertFalse(self.output.exists())
        for config in ({"name": "renamed", "tags": "sandbox"}, {"name": "sandbox", "tags": "vault"}):
            self.api.get.side_effect = lambda path, **kwargs: config if path.endswith("/config") else self.response(path)
            with self.assertRaises(enrollment.EnrollmentError):
                self.enroll()
            self.assertFalse(self.output.exists())

    def test_duplicate_address_is_rejected(self):
        self.inventory["_meta"]["hostvars"]["duplicate"] = self.values
        self.inventory["dev_children"]["hosts"].append("duplicate")
        self.inventory["tag_sandbox"]["hosts"].append("duplicate")
        with self.assertRaises(enrollment.EnrollmentError):
            self.enroll()
        self.api_factory.assert_not_called()

    def test_invalid_or_multiple_public_keys_never_publish_trust(self):
        for content in ("not a public key", KEY + "\n" + KEY, "ssh-ed25519 AAAA", KEY.replace("A", "!", 1)):
            self.api.get.side_effect = lambda path, **kwargs: (
                {"content": content} if path.endswith("/file-read") else self.response(path))
            with self.assertRaises(enrollment.EnrollmentError):
                self.enroll()
            self.assertFalse(self.output.exists())

    def test_agent_failure_never_publishes_partial_trust(self):
        self.inventory["_meta"]["hostvars"]["second"] = dict(
            self.values, ansible_host="10.0.0.11", proxmox_vmid=114)
        self.inventory["dev_children"]["hosts"].append("second")
        self.inventory["tag_sandbox"]["hosts"].append("second")
        self.load_guests.return_value[("pve", 114, "second")] = {}
        def response(path, **kwargs):
            if path == "/pools/dev":
                return {"members": [{"node": "pve", "vmid": vmid, "type": "qemu"} for vmid in (113, 114)]}
            if "/114/" in path:
                raise enrollment.EnrollmentError("Agent unavailable")
            return self.response(path)
        self.api.get.side_effect = response
        with self.assertRaises(enrollment.EnrollmentError):
            self.enroll()
        self.assertFalse(self.output.exists())

    def test_ipv6_nonstandard_ports_and_ansible_tagged_strings(self):
        self.values.update(ansible_host={"__ansible_unsafe": "2001:db8::1"}, ansible_port=2222)
        self.assertEqual(self.enroll(), 1)
        self.assertIn(f"[2001:db8::1]:2222 {KEY}", self.output.read_text())


class StateScopeTests(unittest.TestCase):
    def test_common_reads_only_enabled_vm_roots_in_its_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            repository = Path(tmp)
            for root in ("dev/sandbox", "dev/vault", "dev/talos", "prod/vault"):
                (repository / "terraform/workloads" / root).mkdir(parents=True)
            def state(command, directory):
                return {"resources": [{
                    "mode": "managed", "type": "proxmox_virtual_environment_vm",
                    "instances": [{"attributes": {
                        "node_name": "pve", "vm_id": 113 if directory.name == "sandbox" else 103,
                        "name": directory.name, "pool_id": "dev", "tags": ["common", directory.name],
                    }}],
                }]}
            with patch.object(enrollment.subprocess, "run", return_value=Mock(returncode=0)):
                with patch.object(enrollment, "command_json", side_effect=state) as read:
                    self.assertEqual(set(enrollment.managed_guests(repository, "dev", "common")),
                                     {("pve", 113, "sandbox"), ("pve", 103, "vault")})
                    self.assertEqual({call.args[1] for call in read.call_args_list},
                                     {repository / "terraform/workloads/dev" / name for name in ("sandbox", "vault")})

    def test_only_current_managed_instances_in_selected_pool_and_target_are_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            repository = Path(tmp)
            directory = repository / "terraform/workloads/dev/sandbox"
            directory.mkdir(parents=True)
            valid = {"attributes": {"node_name": "pve", "vm_id": 113, "name": "sandbox",
                                    "pool_id": "dev", "tags": ["sandbox", "common"]}}
            other = copy.deepcopy(valid)
            other["attributes"].update(pool_id="prod", vm_id=213)
            untagged = copy.deepcopy(valid)
            untagged["attributes"].update(tags=["vault"], vm_id=114)
            deposed = copy.deepcopy(valid)
            deposed.update(deposed="old")
            deposed["attributes"]["vm_id"] = 115
            state = {"resources": [{"mode": "managed", "type": "proxmox_virtual_environment_vm",
                                    "instances": [valid, other, untagged, deposed]}]}
            with patch.object(enrollment.subprocess, "run", return_value=Mock(returncode=0)) as run:
                with patch.object(enrollment, "command_json", return_value=state):
                    self.assertEqual(set(enrollment.managed_guests(repository, "dev", "sandbox")),
                                     {("pve", 113, "sandbox")})
                    self.assertIn("-backend-config=key=terraform/dev/sandbox.tfstate", run.call_args.args[0])
                (directory / ".disabled").touch()
                run.reset_mock()
                self.assertEqual(enrollment.managed_guests(repository, "dev", "sandbox"), {})
                run.assert_not_called()


class ApiBoundaryTests(unittest.TestCase):
    def api(self, environment="dev", endpoint="https://pve.example.invalid:8006", token=None):
        return enrollment.Proxmox(endpoint, token or f"tf-{environment}-apply@pve!ci=placeholder", environment)

    def test_wrong_identity_environment_and_unverified_origin_are_denied(self):
        for token in ("root@pam!ci=secret", "ansible-dev@pve!ci=secret", "tf-prod-apply@pve!ci=secret",
                      "tf-dev-plan@pve!ci=secret", "tf-dev-apply@pve!ci="):
            with self.subTest(token=token), self.assertRaises(enrollment.EnrollmentError):
                self.api(token=token)
        for endpoint in ("http://pve:8006", "https://user:password@pve:8006", "https://pve/path",
                         "https://pve/?token=value", "https://pve/#fragment"):
            with self.subTest(endpoint=endpoint), self.assertRaises(enrollment.EnrollmentError):
                self.api(endpoint=endpoint)

    def test_requests_verify_tls_refuse_redirects_and_never_retry_forbidden_access(self):
        api = self.api()
        for status in (301, 302, 401, 403):
            with self.subTest(status=status):
                api.session.get = Mock(return_value=Mock(status_code=status))
                with self.assertRaises(enrollment.EnrollmentError):
                    api.get("/agent/file-read", retry_agent=True)
                self.assertEqual(api.session.get.call_count, 1)
                self.assertTrue(api.session.get.call_args.kwargs["verify"])
                self.assertFalse(api.session.get.call_args.kwargs["allow_redirects"])

    def test_agent_readiness_retries_are_bounded_and_tls_errors_do_not_fall_back(self):
        api = self.api()
        ready = Mock(status_code=200)
        ready.json.return_value = {"data": {"content": KEY}}
        api.session.get = Mock(side_effect=[Mock(status_code=500), ready])
        with patch.object(enrollment.time, "sleep") as sleep:
            self.assertEqual(api.get("/agent/file-read", retry_agent=True), {"content": KEY})
            sleep.assert_called_once_with(5)
        api.session.get = Mock(return_value=Mock(status_code=503))
        with patch.object(enrollment.time, "sleep"), self.assertRaises(enrollment.EnrollmentError):
            api.get("/agent/file-read", retry_agent=True)
        self.assertEqual(api.session.get.call_count, 36)
        api.session.get = Mock(side_effect=requests.exceptions.SSLError("untrusted certificate"))
        with self.assertRaises(requests.exceptions.SSLError):
            api.get("/agent/file-read", retry_agent=True)
        self.assertEqual(api.session.get.call_count, 1)


if __name__ == "__main__":
    unittest.main()
