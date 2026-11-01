#!/usr/bin/env python3
"""Exercise scoped tokens with disposable, stopped, diskless Proxmox guests."""

import argparse
import json
import os
from pathlib import Path
import time
from urllib.parse import quote
import uuid

import requests


def verify(endpoint, credentials, node):
    base = endpoint.rstrip("/") + "/api2/json"
    created = []
    volumes = []

    def call(identity, method, path, expected=200, **kwargs):
        response = requests.request(
            method, base + path,
            headers={"Authorization": "PVEAPIToken=" + credentials[identity]["api_token"]},
            timeout=20, **kwargs,
        )
        if response.status_code != expected:
            raise RuntimeError(f"{identity}: {method} {path}: expected {expected}, got {response.status_code}")
        return response.json().get("data") if expected == 200 else None

    def wait(identity, task):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            status = call(identity, "GET", f"/nodes/{node}/tasks/{quote(task, safe='')}/status")
            if status["status"] == "stopped":
                if status.get("exitstatus") != "OK":
                    raise RuntimeError(f"{identity}: disposable VM task failed: {status.get('exitstatus')}")
                return
            time.sleep(0.2)
        raise RuntimeError(f"{identity}: disposable VM task timed out")

    try:
        guests = {}
        for environment in ["dev", "prod"]:
            owner = f"tf-{environment}-apply"
            vm_id = int(call(owner, "GET", "/cluster/nextid"))
            task = call(owner, "POST", f"/nodes/{node}/qemu", data={
                "vmid": vm_id, "pool": environment,
                "name": f"rbac-check-{environment}-{uuid.uuid4().hex[:6]}",
                "cores": 1, "memory": 128, "onboot": 0,
            })
            created.append((owner, vm_id))
            wait(owner, task)
            guests[environment] = vm_id
            # Tagged create is checked before pool membership on affected PVE releases.
            # Exercise the supported sequence with the exact same scoped identity.
            wait(owner, call(owner, "POST", f"/nodes/{node}/qemu/{vm_id}/config",
                             data={"tags": f"rbac-check;{environment}"}))
            config = call(owner, "GET", f"/nodes/{node}/qemu/{vm_id}/config")
            assert set(config.get("tags", "").split(";")) == {"rbac-check", environment}

        for environment, other in [("dev", "prod"), ("prod", "dev")]:
            own_path = f"/nodes/{node}/qemu/{guests[environment]}/config"
            other_path = f"/nodes/{node}/qemu/{guests[other]}/config"
            owner = f"tf-{environment}-apply"
            wait(owner, call(owner, "POST", own_path, data={"memory": 192}))
            for identity in [owner, f"tf-{environment}-plan"]:
                call(identity, "GET", own_path)
                call(identity, "GET", other_path, expected=403)
                call(identity, "POST", other_path, expected=403, data={"memory": 256})
            for identity in [f"tf-{environment}-plan"]:
                call(identity, "POST", own_path, expected=403, data={"memory": 256})
                privileges = call(identity, "GET", "/access/permissions", params={"path": f"/vms/{guests[environment]}"})
                # Values indicate ACL propagation; presence means access is granted.
                vm_privileges = privileges[f"/vms/{guests[environment]}"]
                assert "VM.GuestAgent.Audit" in vm_privileges
                assert not {"VM.PowerMgmt", "VM.Config.Memory", "VM.GuestAgent.FileRead",
                            "VM.GuestAgent.FileWrite", "VM.GuestAgent.Unrestricted"}.intersection(vm_privileges)
                for vm_id in (guests[environment], guests[other]):
                    call(identity, "GET", f"/nodes/{node}/qemu/{vm_id}/agent/file-read",
                         expected=403, params={"file": "/etc/ssh/ssh_host_ed25519_key.pub"})
                assert "VM.Config.Disk" in vm_privileges
        print("PASS: pool-scoped creation then tagging and owner lifecycle access work; plan tokens have only the approved disk-write exception; memory changes and cross-environment access are denied to read identities.")

        if "k8s-csi-dev" in credentials:
            csi, vm_id = "k8s-csi-dev", guests["dev"]
            call(csi, "GET", f"/nodes/{node}/qemu/{vm_id}/config")
            call(csi, "GET", f"/nodes/{node}/qemu/{guests['prod']}/config", expected=403)
            call(csi, "POST", f"/nodes/{node}/qemu/{vm_id}/config", expected=403, data={"memory": 256})
            disk = {"vmid": vm_id, "filename": f"vm-{vm_id}-disk-9", "size": "4M"}
            for storage in ["zfs", "local-lvm"]:
                call(csi, "POST", f"/nodes/{node}/storage/{storage}/content", expected=403, data=disk)
            volume = call(csi, "POST", f"/nodes/{node}/storage/k8s-dev/content", data=disk)
            volumes.append((csi, volume))
            result = call(csi, "DELETE", f"/nodes/{node}/storage/k8s-dev/content/{quote(volume, safe='')}")
            if isinstance(result, str) and result.startswith("UPID:"):
                wait(csi, result)
            volumes.remove((csi, volume))
            print("PASS: the dev CSI token reads only dev guests, cannot change VM memory, and creates and deletes volumes only on k8s-dev.")
    finally:
        failures = []
        for identity, volume in volumes:
            try:
                call(identity, "DELETE", f"/nodes/{node}/storage/k8s-dev/content/{quote(volume, safe='')}")
            except Exception as error:
                failures.append(str(error))
        for owner, vm_id in reversed(created):
            try:
                wait(owner, call(owner, "DELETE", f"/nodes/{node}/qemu/{vm_id}"))
            except Exception as error:
                failures.append(str(error))
        if failures:
            raise RuntimeError("Disposable guest cleanup failed: " + "; ".join(failures))
        if created:
            print("PASS: all disposable guests removed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", type=Path, default=Path(__file__).parent / ".credentials/automation.json")
    parser.add_argument("--endpoint", default=os.environ.get("TF_VAR_virtual_environment_endpoint"))
    parser.add_argument("--node", default="pve")
    args = parser.parse_args()
    if not args.endpoint:
        parser.error("Set TF_VAR_virtual_environment_endpoint or --endpoint")
    verify(args.endpoint, json.loads(args.credentials.read_text()), args.node)
