#!/usr/bin/env python3
"""Upgrade Talos or Kubernetes across a cluster, one node at a time.

Reads the upgrade_inventory Terraform output. Talos upgrades check every
node's running version first: nodes already on the target are skipped, so a
rerun resumes after a failure, and the run refuses downgrades or skipped minor
releases before touching any node. Each node then goes through upgrade-node.sh,
control planes first. Kubernetes upgrades run talosctl upgrade-k8s between two
cluster health checks.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

VERSION = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
UPGRADE_NODE = Path(__file__).with_name("upgrade-node.sh")


def fail(message):
    print(f"::error::{message}", flush=True)
    sys.exit(1)


def parse_version(text):
    match = VERSION.match(text)
    if not match:
        fail(f"Expected a pinned release such as v1.14.3, got {text!r}")
    return tuple(int(part) for part in match.groups())


def talosctl(*args, capture=False):
    command = ["talosctl", "--talosconfig", os.environ["TALOSCONFIG"], *args]
    result = subprocess.run(command, capture_output=capture, text=True)
    if result.returncode:
        if capture:
            sys.stderr.write(result.stderr)
        fail(f"Failed: talosctl {' '.join(args)}")
    return result.stdout


def running_version(node):
    output = talosctl("--endpoints", node, "--nodes", node, "version", capture=True)
    server = output.split("Server:", 1)[1] if "Server:" in output else ""
    tags = re.findall(r"^\s*Tag:\s*(\S+)", server, re.MULTILINE)
    if len(tags) != 1:
        fail(f"Could not read the running Talos version of {node}")
    return tags[0]


def check_path(current, target):
    """Allow staying put, patch releases, or exactly one minor release forward."""
    cur, tgt = parse_version(current), parse_version(target)
    if tgt < cur:
        return f"would downgrade from {current}"
    if tgt[0] != cur[0] or tgt[1] > cur[1] + 1:
        return f"skips minor releases from {current}; upgrade through each minor release in turn"
    return None


def health_args(inventory):
    control_planes = inventory["control_planes"]
    args = ["--endpoints", control_planes[0], "--nodes", control_planes[0], "health",
            "--control-plane-nodes", ",".join(control_planes), "--wait-timeout", "15m"]
    if inventory["workers"]:
        args += ["--worker-nodes", ",".join(inventory["workers"])]
    return args


def upgrade_talos(inventory, target):
    image = inventory["installer_image"]
    if "secureboot" not in image or ":" not in image:
        fail("The installer image is not a Secure Boot Image Factory installer")
    # The schematic is version-independent, so only the tag changes.
    installer = f"{image.rsplit(':', 1)[0]}:{target}"

    nodes = inventory["control_planes"] + inventory["workers"]
    pending = []
    for node in nodes:
        current = running_version(node)
        problem = check_path(current, target)
        if problem:
            fail(f"Upgrading {node} to {target} {problem}. No node was changed.")
        if current == target:
            print(f"{node} already runs {target}; skipping.", flush=True)
        else:
            pending.append(node)

    for node in pending:
        print(f"::group::Upgrade {node} to {target}", flush=True)
        result = subprocess.run(
            ["bash", str(UPGRADE_NODE), node, installer,
             ",".join(inventory["control_planes"]), ",".join(inventory["workers"])])
        print("::endgroup::", flush=True)
        if result.returncode:
            fail(f"Upgrade stopped at {node}. Nodes after it were not changed; rerun to resume.")
    print(f"All {len(nodes)} nodes run Talos {target}.", flush=True)


def upgrade_kubernetes(inventory, target):
    parse_version(target)
    endpoint = inventory["control_planes"][0]
    talosctl(*health_args(inventory))
    talosctl("--endpoints", endpoint, "--nodes", endpoint, "upgrade-k8s", "--to", target)
    talosctl(*health_args(inventory))
    print(f"Kubernetes upgraded to {target}.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component", choices=["talos", "kubernetes"], required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--inventory", required=True, type=Path)
    args = parser.parse_args()
    if not os.environ.get("TALOSCONFIG"):
        fail("Set TALOSCONFIG to the cluster administrator configuration")
    parse_version(args.version)
    inventory = json.loads(args.inventory.read_text())
    if not inventory.get("control_planes"):
        fail("The inventory lists no control-plane nodes")
    if args.component == "talos":
        upgrade_talos(inventory, args.version)
    else:
        upgrade_kubernetes(inventory, args.version)


if __name__ == "__main__":
    main()
