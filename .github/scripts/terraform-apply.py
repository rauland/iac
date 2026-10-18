#!/usr/bin/env python3
"""Apply the saved infrastructure plan, then an exact, validated VM tag-only plan."""

import argparse
import os
import subprocess

from vm_tags import bind_created_guests, read_manifest, state_resources, terraform_json, validate_tag_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--destroy", choices=("true", "false"), default="false")
    args = parser.parse_args()
    manifest = read_manifest(args.directory, os.environ, args.environment, args.target, args.destroy == "true")
    guests = manifest["guests"]
    subprocess.run(["terraform", "apply", "-input=false", "tfplan"], cwd=args.directory, check=True)
    if not guests:
        return
    bound = bind_created_guests(terraform_json(args.directory, "show", "-json"), guests)
    result = subprocess.run(
        ["terraform", "plan", "-input=false", "-refresh=false", "-detailed-exitcode",
         "-var=deferred_vm_tags=[]", "-out=tfplan.tags"], cwd=args.directory)
    if result.returncode not in (0, 2):
        raise ValueError("VM tag follow-up planning failed; recover with a fresh full plan")
    validate_tag_plan(terraform_json(args.directory, "show", "-json", "tfplan.tags"), bound,
                      manifest["data_reads"], manifest["intent_sha256"])
    subprocess.run(["terraform", "apply", "-input=false", "tfplan.tags"], cwd=args.directory, check=True)
    resources = terraform_json(args.directory, "show", "-json")
    final = bind_created_guests(resources, bound)
    # Verify persisted tags before downstream SSH enrollment or service configuration.
    observed = state_resources(resources)
    if any(sorted(observed[guest["address"]].get("tags") or []) != guest["tags"] for guest in final):
        raise ValueError("VM tags were not recorded in state; recover with a fresh full plan")


if __name__ == "__main__":
    main()
