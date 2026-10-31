#!/usr/bin/env python3
"""Back up opted-in Kubernetes volumes and etcd from the Proxmox host to PBS.

Every selected volume is snapshotted at the same instant with ZFS, then each
snapshot is uploaded as a block image together with its PersistentVolume and
claim. Apps with several volumes therefore get a consistent set.
"""

import argparse
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request

CSI_DRIVER = "csi.proxmox.sinextra.dev"
DROPPED_METADATA = ("managedFields", "resourceVersion", "uid", "creationTimestamp")


def kube_list(config, path):
    context = ssl.create_default_context(cafile=config["kube_ca_file"])
    token = Path(config["kube_token_file"]).read_text().strip()
    request = urllib.request.Request(
        config["kube_server"].rstrip("/") + path,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    with urllib.request.urlopen(request, context=context, timeout=30) as response:
        return json.load(response)["items"]


def clean(item):
    item = json.loads(json.dumps(item))
    for key in DROPPED_METADATA:
        item.get("metadata", {}).pop(key, None)
    item.pop("status", None)
    return item


def select_volumes(pvs, pvcs, storage, label):
    """Return opted-in volumes on this storage, sorted by backup ID."""
    key, _, value = label.partition("=")
    claims = {(c["metadata"]["namespace"], c["metadata"]["name"]): c for c in pvcs}
    selected = []
    for pv in pvs:
        csi = pv.get("spec", {}).get("csi") or {}
        ref = pv.get("spec", {}).get("claimRef") or {}
        parts = csi.get("volumeHandle", "").split("/")
        if csi.get("driver") != CSI_DRIVER or len(parts) != 4 or parts[2] != storage:
            continue
        claim = claims.get((ref.get("namespace"), ref.get("name")))
        if not claim or claim["metadata"].get("labels", {}).get(key) != value:
            continue
        if claim["metadata"].get("uid") != ref.get("uid"):
            continue
        selected.append({
            "backup_id": f"{ref['namespace']}.{ref['name']}",
            "volume": parts[3],
            "manifest": {"persistentVolume": clean(pv), "persistentVolumeClaim": clean(claim)},
        })
    return sorted(selected, key=lambda volume: volume["backup_id"])


def run(command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)


def pbs_env(config):
    env = dict(os.environ, PBS_REPOSITORY=config["pbs_repository"],
               PBS_PASSWORD=Path(config["pbs_token_file"]).read_text().strip())
    if config.get("pbs_fingerprint"):
        env["PBS_FINGERPRINT"] = config["pbs_fingerprint"]
    return env


def upload(config, backup_id, archives):
    command = ["proxmox-backup-client", "backup", *archives, "--ns", config["pbs_namespace"],
               "--backup-type", "host", "--backup-id", backup_id]
    run(command, env=pbs_env(config))


def wait_for(path, timeout=60):
    run(["udevadm", "settle"])
    deadline = time.monotonic() + timeout
    while not os.path.exists(path):
        if time.monotonic() > deadline:
            raise RuntimeError(f"{path} did not appear")
        time.sleep(1)


def back_up_volumes(config, volumes, workdir):
    snapshot = "k8s-backup-" + time.strftime("%Y%m%dT%H%M%S")
    names = [f"{config['zfs_dataset']}/{volume['volume']}@{snapshot}" for volume in volumes]
    # One command, so every volume is captured at the same instant.
    run(["zfs", "snapshot", *names])
    failures = []
    try:
        for volume, name in zip(volumes, names):
            try:
                device = f"/dev/zvol/{name}"
                wait_for(device)
                manifest = Path(workdir, f"{volume['backup_id']}.json")
                manifest.write_text(json.dumps(volume["manifest"], indent=2))
                upload(config, volume["backup_id"],
                       [f"volume.img:{device}", f"claim.conf:{manifest}"])
                print(f"backed up {volume['backup_id']} ({volume['volume']})", flush=True)
            except (subprocess.CalledProcessError, RuntimeError) as error:
                failures.append(volume["backup_id"])
                print(f"failed {volume['backup_id']}: {error}", file=sys.stderr, flush=True)
    finally:
        for name in names:
            subprocess.run(["zfs", "destroy", name], check=False)
    return failures


def back_up_etcd(config, workdir):
    snapshot = Path(workdir, "etcd.db")
    run([config.get("talosctl", "talosctl"), "--talosconfig", config["talosconfig_file"],
         "--nodes", config["talos_node"], "--endpoints", config["talos_node"],
         "etcd", "snapshot", str(snapshot)], stdout=subprocess.DEVNULL)
    upload(config, config["etcd_backup_id"], [f"etcd.img:{snapshot}"])
    print(f"backed up {config['etcd_backup_id']}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="/etc/k8s-volume-backup/config.json")
    parser.add_argument("--list", action="store_true", help="print the selected volumes and exit")
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text())

    volumes = select_volumes(kube_list(config, "/api/v1/persistentvolumes"),
                             kube_list(config, "/api/v1/persistentvolumeclaims"),
                             config["storage"], config["label"])
    if args.list:
        for volume in volumes:
            print(volume["backup_id"], volume["volume"])
        return 0

    failures = []
    with tempfile.TemporaryDirectory(prefix="k8s-volume-backup-") as workdir:
        if volumes:
            failures += back_up_volumes(config, volumes, workdir)
        else:
            print("no volumes are labelled for backup", flush=True)
        if config.get("talos_node"):
            try:
                back_up_etcd(config, workdir)
            except subprocess.CalledProcessError as error:
                failures.append(config["etcd_backup_id"])
                print(f"failed {config['etcd_backup_id']}: {error}", file=sys.stderr, flush=True)
    if failures:
        print("failed: " + ", ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
