"""Offline checks for the PBS configuration module's create and update plans."""
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / "roles/pbs/library/pbs_config.py"
spec = importlib.util.spec_from_file_location("pbs_config", MODULE)
pbs_config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pbs_config)


def params(**overrides):
    base = {"section": ["sync-job"], "id": "offsite", "id_key": "id", "positional": [],
            "options": {}, "create_only": {}, "write_only": {}, "update_write_only": False}
    return {**base, **overrides}


class PlanTests(unittest.TestCase):
    def test_missing_entry_is_created_with_every_option(self):
        action, command, _ = pbs_config.plan([], params(
            section=["datastore"], id="offsite", id_key="name", positional=["/cache"],
            options={"gc-schedule": "daily"},
            create_only={"backend": {"type": "s3", "client": "aws", "bucket": "b"}}))
        self.assertEqual(action, "create")
        self.assertEqual(command, ["proxmox-backup-manager", "datastore", "create", "offsite",
                                   "/cache", "--backend", "bucket=b,client=aws,type=s3",
                                   "--gc-schedule", "daily"])

    def test_matching_entry_is_left_alone(self):
        current = [{"id": "offsite", "store": "offsite", "keep-daily": 7, "verify": True,
                    "group-filter": ["group:ct/101", "group:vm/102"]}]
        action, command, _ = pbs_config.plan(current, params(options={
            "store": "offsite", "keep-daily": 7, "verify": True,
            "group-filter": ["group:ct/101", "group:vm/102"]}))
        self.assertEqual((action, command), ("none", None))

    def test_only_differing_options_are_updated(self):
        current = [{"id": "offsite", "store": "offsite", "schedule": "01:00"}]
        action, command, changed = pbs_config.plan(current, params(
            options={"store": "offsite", "schedule": "02:00", "group-filter": ["group:vm/102"]}))
        self.assertEqual(action, "update")
        self.assertEqual(changed, ["group-filter", "schedule"])
        self.assertEqual(command, ["proxmox-backup-manager", "sync-job", "update", "offsite",
                                   "--group-filter", "group:vm/102", "--schedule", "02:00"])

    def test_listed_property_strings_match_maps(self):
        self.assertTrue(pbs_config.matches({"type": "s3", "bucket": "b"}, "type=s3,bucket=b"))
        self.assertFalse(pbs_config.matches({"type": "s3", "bucket": "b"}, "type=s3,bucket=c"))
        self.assertTrue(pbs_config.matches(True, 1))
        self.assertFalse(pbs_config.matches("monthly", None))

    def test_secrets_are_required_on_create_and_sent_only_on_rotation(self):
        endpoint = params(section=["s3", "endpoint"], id="aws", options={"region": "r"},
                          write_only={"access-key": "id", "secret-key": ""})
        with self.assertRaisesRegex(ValueError, "secret-key"):
            pbs_config.plan([], endpoint)
        current = [{"id": "aws", "region": "r"}]
        endpoint["write_only"]["secret-key"] = "secret"
        self.assertEqual(pbs_config.plan(current, endpoint)[0], "none")
        action, command, _ = pbs_config.plan(current, dict(endpoint, update_write_only=True))
        self.assertEqual(action, "update")
        self.assertEqual(command[-4:], ["--access-key", "id", "--secret-key", "secret"])


if __name__ == "__main__":
    unittest.main()
