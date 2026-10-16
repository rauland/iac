#!/usr/bin/env python3
"""Discover Terraform roots affected by an event, or one manual selection."""

import json
import os
from pathlib import Path
import subprocess


def select_roots(roots, paths):
    # Shared modules can have transitive consumers: conservatively plan all roots.
    if any(p.startswith(("terraform/modules/", ".github/scripts/"))
           or p == ".github/workflows/terraform.yml" for p in paths):
        return roots
    return [root for root in roots
            if any(p.startswith(f"terraform/environments/{root['environment']}/{root['target']}/")
                   for p in paths)]


def discover():
    roots = sorted(
        ({"environment": p.parent.name, "target": p.name}
         for p in Path("terraform/environments").glob("*/*")
         if p.is_dir() and any(p.glob("*.tf"))),
        key=lambda root: (root["environment"], root["target"]),
    )
    if os.environ["EVENT_NAME"] == "workflow_dispatch":
        selected = {"environment": os.environ["SELECTED_ENV"],
                    "target": os.environ["SELECTED_TARGET"]}
        if selected not in roots:
            raise SystemExit(f"No Terraform root found for {selected}")
        return [selected]

    base = os.environ.get("BASE_SHA", "")
    head = os.environ["HEAD_SHA"]
    # A new branch has no previous commit. All checked-out roots are affected.
    if not base or set(base) == {"0"}:
        return roots
    revision = f"{base}...{head}" if os.environ["EVENT_NAME"] == "pull_request" else f"{base}..{head}"
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", "--no-renames", "-z", revision],
    ).decode().split("\0")
    return select_roots(roots, [p for p in changed if p])


if __name__ == "__main__":
    roots = discover()
    matrix = json.dumps(roots, separators=(",", ":"))
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"matrix={matrix}\n")
        output.write(f"has-changes={str(bool(roots)).lower()}\n")
    print(f"Affected Terraform roots: {matrix}")
