#!/usr/bin/env python3
"""Discover workload roots and shared images, excluding privileged access roots."""

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
            if any(p.startswith(f"{root['directory']}/")
                   for p in paths)]


def discover():
    # Only images is deployable under platform. Access remains administrator-operated.
    candidates = list(Path("terraform/workloads").glob("*/*"))
    candidates.append(Path("terraform/platform/images"))
    roots = sorted(
        ({"environment": p.parent.name, "target": p.name, "directory": p.as_posix()}
         for p in candidates
         if p.is_dir() and any(p.glob("*.tf")) and not (p / ".disabled").exists()),
        key=lambda root: (root["environment"], root["target"]),
    )
    if os.environ["EVENT_NAME"] == "workflow_dispatch":
        mode = os.environ.get("DEPLOYMENT_MODE", "single")
        if mode == "all":
            selected = [root for root in roots
                        if root["environment"] == os.environ["SELECTED_ENV"]]
            if not selected:
                raise SystemExit("No enabled Terraform roots found for selected environment")
            return selected
        if mode != "single":
            raise SystemExit(f"Unsupported deployment mode: {mode}")
        selected = [root for root in roots
                    if root["environment"] == os.environ["SELECTED_ENV"]
                    and root["target"] == os.environ["SELECTED_TARGET"]]
        if not selected:
            raise SystemExit("No Terraform root found (or it is disabled) for "
                             f"{os.environ['SELECTED_ENV']}/{os.environ['SELECTED_TARGET']}")
        return selected

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
        if len(roots) == 1:
            output.write(f"directory={roots[0]['directory']}\n")
    print(f"Affected Terraform roots: {matrix}")
