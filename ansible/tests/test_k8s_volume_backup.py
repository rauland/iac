"""Offline checks for volume selection and the snapshot-and-upload sequence."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "roles/pve_volume_backup/files/k8s-volume-backup.py"
spec = importlib.util.spec_from_file_location("k8s_volume_backup", SCRIPT)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def pv(name, namespace, claim, uid, storage="k8s-dev", driver=backup.CSI_DRIVER):
    return {"metadata": {"name": name, "uid": "pv-uid", "managedFields": [{}]},
            "spec": {"csi": {"driver": driver, "volumeHandle": f"pve/pve/{storage}/vm-9999-{name}"},
                     "claimRef": {"namespace": namespace, "name": claim, "uid": uid}},
            "status": {"phase": "Bound"}}


def pvc(namespace, name, uid, labels=None):
    return {"metadata": {"namespace": namespace, "name": name, "uid": uid, "labels": labels or {}}}


class SelectionTests(unittest.TestCase):
    def test_only_labelled_claims_on_the_storage_are_selected(self):
        pvs = [pv("pvc-a", "photos", "library", "a"), pv("pvc-b", "photos", "thumbs", "b"),
               pv("pvc-c", "other", "data", "c", storage="local-lvm"),
               pv("pvc-d", "other", "nfs", "d", driver="nfs.csi.k8s.io")]
        pvcs = [pvc("photos", "library", "a", {"backup": "true"}), pvc("photos", "thumbs", "b"),
                pvc("other", "data", "c", {"backup": "true"}), pvc("other", "nfs", "d", {"backup": "true"})]
        selected = backup.select_volumes(pvs, pvcs, "k8s-dev", "backup=true")
        self.assertEqual([(v["backup_id"], v["volume"]) for v in selected],
                         [("photos.library", "vm-9999-pvc-a")])

    def test_released_volumes_whose_claim_was_recreated_are_skipped(self):
        pvs = [pv("pvc-a", "photos", "library", "old-uid")]
        pvcs = [pvc("photos", "library", "new-uid", {"backup": "true"})]
        self.assertEqual(backup.select_volumes(pvs, pvcs, "k8s-dev", "backup=true"), [])

    def test_manifest_keeps_the_binding_without_server_fields(self):
        pvs = [pv("pvc-a", "photos", "library", "a")]
        pvcs = [pvc("photos", "library", "a", {"backup": "true"})]
        manifest = backup.select_volumes(pvs, pvcs, "k8s-dev", "backup=true")[0]["manifest"]
        volume = manifest["persistentVolume"]
        self.assertNotIn("managedFields", volume["metadata"])
        self.assertNotIn("status", volume)
        self.assertEqual(volume["spec"]["claimRef"]["name"], "library")
        self.assertEqual(manifest["persistentVolumeClaim"]["metadata"]["labels"], {"backup": "true"})


class SequenceTests(unittest.TestCase):
    config = {"zfs_dataset": "nas/k8s-dev", "pbs_namespace": "k8s-dev",
              "pbs_repository": "user@pbs!t@host:store", "pbs_token_file": "/dev/null"}
    volumes = [{"backup_id": "photos.library", "volume": "vm-9999-pvc-a", "manifest": {}},
               {"backup_id": "photos.db", "volume": "vm-9999-pvc-b", "manifest": {}}]

    def run_backup(self, fail_upload=None):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if command[0] == "proxmox-backup-client" and fail_upload in command:
                raise subprocess.CalledProcessError(1, command)

        def fake_cleanup(command, **kwargs):
            calls.append(command)

        with tempfile.TemporaryDirectory() as workdir, \
                mock.patch.object(backup, "run", fake_run), \
                mock.patch.object(backup, "wait_for"), \
                mock.patch.object(backup.subprocess, "run", fake_cleanup):
            failures = backup.back_up_volumes(self.config, self.volumes, workdir)
        return failures, calls

    def test_every_volume_is_snapshotted_in_one_command_then_released(self):
        failures, calls = self.run_backup()
        self.assertEqual(failures, [])
        snapshot = calls[0]
        self.assertEqual(snapshot[:2], ["zfs", "snapshot"])
        self.assertEqual(len(snapshot), 4)
        uploads = [c for c in calls if c[0] == "proxmox-backup-client"]
        self.assertEqual([c[c.index("--backup-id") + 1] for c in uploads], ["photos.library", "photos.db"])
        self.assertTrue(all(c[c.index("--backup-type") + 1] == "host" for c in uploads))
        self.assertTrue(all(c[c.index("--ns") + 1] == "k8s-dev" for c in uploads))
        destroyed = [c[2] for c in calls if c[:2] == ["zfs", "destroy"]]
        self.assertEqual(destroyed, snapshot[2:])

    def test_a_failed_upload_continues_and_still_releases_snapshots(self):
        failures, calls = self.run_backup(fail_upload="photos.library")
        self.assertEqual(failures, ["photos.library"])
        self.assertEqual(len([c for c in calls if c[:2] == ["zfs", "destroy"]]), 2)
        self.assertIn("photos.db", [c[c.index("--backup-id") + 1] for c in calls
                                    if c[0] == "proxmox-backup-client"])

    def test_snapshots_are_released_even_if_the_run_is_interrupted(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if command[0] == "proxmox-backup-client":
                raise KeyboardInterrupt

        with tempfile.TemporaryDirectory() as workdir, \
                mock.patch.object(backup, "run", fake_run), \
                mock.patch.object(backup, "wait_for"), \
                mock.patch.object(backup.subprocess, "run", lambda c, **k: calls.append(c)):
            with self.assertRaises(KeyboardInterrupt):
                backup.back_up_volumes(self.config, self.volumes, workdir)
        self.assertEqual(len([c for c in calls if c[:2] == ["zfs", "destroy"]]), 2)


class ConfigTests(unittest.TestCase):
    def test_role_template_provides_every_key_the_script_reads(self):
        template = (SCRIPT.parents[1] / "templates/config.json.j2").read_text()
        source = SCRIPT.read_text()
        used = {part.split('"]')[0] for part in source.split('config["')[1:]}
        self.assertIn("pbs_repository", used)
        for key in used:
            self.assertIn(f'"{key}"', template, key)


if __name__ == "__main__":
    unittest.main()
