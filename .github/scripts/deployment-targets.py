#!/usr/bin/env python3
"""Select Terraform roots to plan from changed paths or a manual request, without credentials."""

import json
import os
from pathlib import Path
import subprocess


TARGETS = {"talos", "flux"}


def enabled_roots():
    return sorted(
        ({"environment": path.parent.name, "target": path.name,
          "directory": path.as_posix(), "terraform": False, "destroy": False}
         for path in Path("terraform/workloads").glob("*/*")
         if path.is_dir() and any(path.glob("*.tf"))
         and path.parent.name in {"dev", "prod"} and path.name in TARGETS
         and not (path / ".disabled").exists()),
        key=lambda root: (root["environment"], root["target"]),
    )


def infrastructure_path(path, root):
    # Removing the marker re-enables a root, which needs a plan of its own.
    if path == root["directory"] + "/.disabled":
        return True
    if path in {".github/scripts/terraform-plan.py", ".github/scripts/terraform-apply.py",
                ".github/scripts/plan_manifest.py", ".github/scripts/terraform-plan-artifact.sh"}:
        return True
    if not (path.endswith((".tf", ".tfvars", ".tfvars.json"))
            or Path(path).name == ".terraform.lock.hcl"):
        return False
    return path.startswith((root["directory"] + "/", "terraform/modules/"))


def changed_targets(roots, paths):
    selected = []
    for root in roots:
        entry = dict(root)
        for path in paths:
            if path.endswith(".md") or "/tests/" in path:
                continue
            entry["terraform"] |= infrastructure_path(path, root)
        if entry["terraform"]:
            selected.append(entry)
    return selected


def discover():
    roots = enabled_roots()
    if os.environ["EVENT_NAME"] == "workflow_dispatch":
        if os.environ.get("GITHUB_REF") != "refs/heads/main":
            raise SystemExit("Manual deployments must run from main")
        mode = os.environ.get("DEPLOYMENT_MODE", "auto")
        scope = os.environ.get("DEPLOYMENT_SCOPE", "single")
        environment = os.environ.get("SELECTED_ENV", "")
        target = os.environ.get("SELECTED_TARGET", "")
        if mode not in {"auto", "destroy"}:
            raise SystemExit("Unsupported deployment mode")
        if scope not in {"single", "all"} or environment not in {"dev", "prod"}:
            raise SystemExit("Invalid deployment scope or environment")
        selected = [dict(root, terraform=True, destroy=mode == "destroy") for root in roots
                    if root["environment"] == environment
                    and (scope == "all" or root["target"] == target)]
        if not selected:
            raise SystemExit("No enabled deployment targets found for selected scope")
        return selected

    base = os.environ.get("BASE_SHA", "")
    head = os.environ["HEAD_SHA"]
    if not base or set(base) == {"0"}:
        return [dict(root, terraform=True) for root in roots]
    revision = (f"{base}...{head}" if os.environ["EVENT_NAME"] == "pull_request"
                else f"{base}..{head}")
    paths = subprocess.check_output(
        ["git", "diff", "--name-only", "--no-renames", "-z", revision],
    ).decode().split("\0")
    return changed_targets(roots, [path for path in paths if path])


if __name__ == "__main__":
    targets = discover()
    plans = [target for target in targets if target["terraform"]]
    values = {"matrix": json.dumps(targets, separators=(",", ":")),
              "plan-matrix": json.dumps(plans, separators=(",", ":")),
              "has-targets": str(bool(targets)).lower(),
              "has-plans": str(bool(plans)).lower()}
    if len(targets) == 1 and targets[0]["directory"]:
        values["directory"] = targets[0]["directory"]
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        for name, value in values.items():
            output.write(f"{name}={value}\n")
    print(f"Selected deployment work: {values['matrix']}")
