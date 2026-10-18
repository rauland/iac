#!/usr/bin/env python3
"""Record the actual plan result; never interpret Terraform exit code 2 as failure."""

import argparse
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--destroy", choices=("true", "false"), default="false")
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    command = ["terraform", "plan", "-lock=false", "-input=false",
               "-detailed-exitcode", "-out=tfplan"]
    if args.destroy == "true":
        command.append("-destroy")
    result = subprocess.run(command, cwd=args.directory)
    if result.returncode not in (0, 2):
        raise SystemExit(result.returncode or 1)
    changes = result.returncode == 2
    # The human-readable renderer hides sensitive values; show -json does not.
    plan_text = subprocess.run(
        ["terraform", "show", "-no-color", "tfplan"], cwd=args.directory,
        check=True, capture_output=True, text=True).stdout
    metadata = {"environment": args.environment, "target": args.target,
                "changes": changes, "destroy": args.destroy == "true",
                "plan_text": plan_text,
                "sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
                "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"]}
    path = Path(args.result)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata) + "\n")
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"changes={str(changes).lower()}\n")


if __name__ == "__main__":
    main()
