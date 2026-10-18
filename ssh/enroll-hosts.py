#!/usr/bin/env python3
"""Bootstrap unpinned SSH hosts through the existing scoped Proxmox apply token."""

import argparse
import base64
import ipaddress
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import time
from urllib.parse import quote, urlsplit

import requests


class EnrollmentError(Exception):
    """A trust or identity check failed; do not run Ansible."""


def command_json(command, cwd):
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        # State, inventory and command diagnostics may contain credentials.
        raise EnrollmentError(f"{command[0]} failed while preparing host enrollment")
    return json.loads(result.stdout)


def untag(value):
    if isinstance(value, dict) and set(value) == {"__ansible_unsafe"}:
        return value["__ansible_unsafe"]
    return value


def group_hosts(inventory, group, visited=None):
    visited = set() if visited is None else visited
    if group in visited:
        return set()
    visited.add(group)
    data = inventory.get(group, {})
    hosts = set(data.get("hosts", []))
    for child in data.get("children", []):
        hosts.update(group_hosts(inventory, child, visited))
    return hosts


def selected_hosts(inventory, environment, target):
    names = (group_hosts(inventory, f"proxmox_pool_{environment}")
             & group_hosts(inventory, f"tag_{target}"))
    selected = []
    addresses = set()
    for name in sorted(names):
        values = {key: untag(value) for key, value in inventory["_meta"]["hostvars"][name].items()}
        address = str(ipaddress.ip_address(values["ansible_host"]))
        port = int(values.get("ansible_port", 22))
        if not 1 <= port <= 65535:
            raise EnrollmentError("Invalid inventory SSH port")
        lookup = address if port == 22 else f"[{address}]:{port}"
        if lookup in addresses:
            raise EnrollmentError("Multiple selected guests share an SSH address")
        addresses.add(lookup)
        selected.append((name, lookup, values))
    return selected


def is_pinned(trust, address):
    result = subprocess.run(["ssh-keygen", "-F", address, "-f", str(trust)],
                            text=True, capture_output=True)
    if result.returncode not in (0, 1):
        raise EnrollmentError("Cannot inspect the committed SSH trust file")
    return result.returncode == 0


def managed_guests(repository, environment, target):
    """Read backend state without refreshing or changing guests."""
    guests = {}
    targets = ("sandbox", "vault") if target == "common" else (target,)
    for name in targets:
        directory = repository / "terraform/workloads" / environment / name
        if not directory.is_dir() or (directory / ".disabled").exists():
            continue
        result = subprocess.run(
            ["terraform", "init", "-input=false", "-no-color",
             f"-backend-config=key=terraform/{environment}/{name}.tfstate"],
            cwd=directory, text=True, capture_output=True)
        if result.returncode:
            raise EnrollmentError("Cannot initialize the selected Terraform state backend")
        state = command_json(["terraform", "state", "pull"], directory)
        for resource in state.get("resources", []):
            if resource.get("mode") != "managed" or resource.get("type") != "proxmox_virtual_environment_vm":
                continue
            for instance in resource.get("instances", []):
                # A pending replacement's old, deposed instance is never an enrollment source.
                if instance.get("deposed"):
                    continue
                values = instance["attributes"]
                if values.get("pool_id") != environment or target not in values.get("tags", []):
                    continue
                identity = (values["node_name"], int(values["vm_id"]), values["name"])
                guests[identity] = values
    return guests


class Proxmox:
    def __init__(self, endpoint, token, environment):
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ("", "/")):
            raise EnrollmentError("Enrollment requires the verified HTTPS Proxmox API origin")
        if not token.startswith(f"tf-{environment}-apply@pve!ci=") or not token.split("=", 1)[1]:
            raise EnrollmentError("Enrollment requires this environment's Terraform apply token")
        self.base = endpoint.rstrip("/") + "/api2/json"
        self.session = requests.Session()
        self.session.headers["Authorization"] = "PVEAPIToken=" + token

    def get(self, path, params=None, retry_agent=False):
        for attempt in range(36 if retry_agent else 1):
            response = self.session.get(self.base + path, params=params, timeout=15,
                                        verify=True, allow_redirects=False)
            if response.status_code == 200:
                return response.json()["data"]
            if retry_agent and response.status_code in (500, 503) and attempt < 35:
                time.sleep(5)
                continue
            # Never fall back to network discovery, another token or disabled TLS verification.
            raise EnrollmentError(f"Proxmox host enrollment request failed (HTTP {response.status_code})")


def host_public_key(content):
    parts = content.strip().split()
    if len(parts) < 2 or parts[0] != "ssh-ed25519" or "\n" in content.strip() or "\r" in content:
        raise EnrollmentError("Guest agent did not return one Ed25519 public host key")
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except ValueError as error:
        raise EnrollmentError("Invalid public host key encoding") from error
    prefix = struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32)
    if len(blob) != len(prefix) + 32 or not blob.startswith(prefix):
        raise EnrollmentError("Invalid Ed25519 public host key")
    return " ".join(parts[:2])


def enroll(inventory, repository, environment, target, trust, output, load_guests, api_factory):
    if environment not in {"dev", "prod"} or target not in {"common", "sandbox", "vault"}:
        raise EnrollmentError("Invalid enrollment environment or target")
    pending = [host for host in selected_hosts(inventory, environment, target)
               if not is_pinned(trust, host[1])]
    additions = []
    if pending:
        managed = load_guests(repository, environment, target)
        api = api_factory()
        members = api.get(f"/pools/{environment}")["members"]
        membership = {(member["node"], int(member["vmid"])) for member in members
                      if member.get("type") == "qemu"}
        for name, address, values in pending:
            node, vmid = values["proxmox_node"], int(values["proxmox_vmid"])
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", node) or vmid < 100:
                raise EnrollmentError("Invalid inventory VM identity")
            if (values.get("proxmox_vmtype") != "qemu" or (node, vmid, name) not in managed
                    or (node, vmid) not in membership):
                raise EnrollmentError("Unpinned guest does not match the selected Terraform state and pool")
            path = f"/nodes/{quote(node, safe='')}/qemu/{vmid}"
            config = api.get(path + "/config")
            if config.get("name") != name or target not in config.get("tags", "").split(";"):
                raise EnrollmentError("Live guest identity differs from the selected deployment")
            data = api.get(path + "/agent/file-read",
                           params={"file": "/etc/ssh/ssh_host_ed25519_key.pub", "decode": 1},
                           retry_agent=True)
            key = host_public_key(data["content"])
            additions.append(f"{address} {key}\n")
    # Publish only after every guest passes; the caller keeps this in its private SSH directory.
    with open(output, "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
        stream.write(trust.read_text().rstrip() + "\n" + "".join(additions))
    return len(additions)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment", choices=("dev", "prod"))
    parser.add_argument("target", choices=("common", "sandbox", "vault"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parent.parent
    inventory = command_json(["ansible-inventory", "--list"], repository / "ansible")
    count = enroll(
        inventory, repository, args.environment, args.target,
        repository / "ssh/known_hosts" / args.environment, args.output,
        managed_guests,
        lambda: Proxmox(os.environ["TF_VAR_virtual_environment_endpoint"],
                        os.environ["TF_VAR_virtual_environment_api_token"], args.environment))
    print(f"Enrolled {count} unpinned SSH host(s) through the scoped Proxmox guest agent.")


if __name__ == "__main__":
    try:
        main()
    except (EnrollmentError, KeyError, ValueError, OSError, requests.RequestException) as error:
        # requests exceptions can include URLs; never print API bodies, inventory or token values.
        message = str(error) if isinstance(error, EnrollmentError) else type(error).__name__
        print(f"SSH host enrollment stopped: {message}", file=sys.stderr)
        sys.exit(1)
