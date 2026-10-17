#!/usr/bin/env python3
"""Build approval jobs only for real infrastructure or requested configuration work."""

import json
import os
from pathlib import Path


VM_TARGETS = {"sandbox", "vault"}


def prepare(targets, result_directory, context):
    deployments = []
    rows = []
    seen = set()
    for target in targets:
        environment, name = target["environment"], target["target"]
        key = (environment, name)
        if key in seen:
            raise ValueError("Duplicate deployment target")
        seen.add(key)
        if ((environment == "platform" and name != "images")
                or (environment in {"dev", "prod"}
                    and name not in VM_TARGETS | {"common", "talos"})
                or environment not in {"dev", "prod", "platform"}):
            raise ValueError("Invalid deployment target")
        for flag in ("terraform", "ansible", "destroy"):
            if type(target[flag]) is not bool:
                raise ValueError(f"Invalid {flag} flag")
        if target["destroy"] and (context["GITHUB_EVENT_NAME"] != "workflow_dispatch"
                                  or context["GITHUB_REF"] != "refs/heads/main"
                                  or context.get("DEPLOYMENT_MODE") != "destroy"):
            raise ValueError("Destroy requires an explicit manual request on main")
        changes = False
        if target["terraform"]:
            directory = (f"terraform/platform/{name}" if environment == "platform"
                         else f"terraform/workloads/{environment}/{name}")
            if target["directory"] != directory or name == "common":
                raise ValueError("Invalid infrastructure directory")
            result = json.loads((result_directory / f"{environment}--{name}.json").read_text())
            expected = {"environment": environment, "target": name,
                        "sha": context["GITHUB_SHA"], "run_id": context["GITHUB_RUN_ID"],
                        "run_attempt": context["GITHUB_RUN_ATTEMPT"], "destroy": target["destroy"]}
            if any(result.get(key) != value for key, value in expected.items()):
                raise ValueError("Plan result does not match this target, commit, and run attempt")
            if type(result.get("changes")) is not bool:
                raise ValueError("Missing or invalid Terraform change result")
            changes = result["changes"]
        elif target["destroy"]:
            raise ValueError("Destroy requires a Terraform plan")
        ansible = (not target["destroy"] and
                   (target["ansible"] or (changes and name in VM_TARGETS)))
        if ansible and (environment == "platform" or name not in VM_TARGETS | {"common"}):
            raise ValueError("Invalid Ansible target")
        rows.append(f"| {environment}/{name} | "
                    f"{'destroy' if changes and target['destroy'] else 'apply' if changes else 'skip'} | "
                    f"{'run' if ansible else 'skip'} |")
        if changes or ansible:
            automatic_dev = (environment == "dev" and context["GITHUB_EVENT_NAME"] == "push"
                             and context["GITHUB_REF"] == "refs/heads/main")
            approval = ("proxmox-dev-auto-apply" if automatic_dev else
                        f"proxmox-{environment}-apply")
            deployments.append(dict(target, terraform=changes, ansible=ansible,
                                    approval_environment=approval))
    return deployments, rows


def main():
    deployments, rows = prepare(json.loads(os.environ["TARGETS_JSON"]),
                                Path(os.environ["PLAN_RESULTS_DIRECTORY"]), os.environ)
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"matrix={json.dumps(deployments, separators=(',', ':'))}\n")
        output.write(f"has-deployments={str(bool(deployments)).lower()}\n")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
        summary.write(f"## Deployment preview\n\nCommit: `{os.environ['GITHUB_SHA']}`\n\n")
        summary.write("| Target | Terraform | Ansible |\n| --- | --- | --- |\n")
        summary.write("\n".join(rows) + "\n\n")
        summary.write("Production changes require approval in `proxmox-prod-apply`. "
                      "Ansible entries describe intended runs, not a saved change plan.\n")


if __name__ == "__main__":
    main()
