#!/usr/bin/env python3
"""Build approval jobs only for targets whose saved plan has changes."""

import html
import json
import os
from pathlib import Path


TARGETS = {"talos", "flux"}


def preview(targets, result_directory, rows, context):
    """Combine the validated targets' readable plans within GitHub's comment limit."""
    run_url = (f"{context['GITHUB_SERVER_URL']}/{context['GITHUB_REPOSITORY']}/actions/runs/"
               f"{context['GITHUB_RUN_ID']}/attempts/{context['GITHUB_RUN_ATTEMPT']}")
    commit = context.get("PR_HEAD_SHA") or context["GITHUB_SHA"]
    body = (f"## Deployment preview\n\nCommit: `{commit}` · [Workflow run]({run_url})\n\n"
            "| Target | Terraform |\n| --- | --- |\n"
            + "\n".join(rows) + "\n\n")
    plans = [target for target in targets if target["terraform"]]
    if not plans:
        body += "No Terraform plans were needed for this change.\n\n"
    # Leave space for headings, truncation notices, and the comment's hidden markers.
    budget = max(0, (55000 - len(body.encode("utf-8"))) // max(1, len(plans)) - 500)
    for target in plans:
        label = f"{target['environment']}/{target['target']}"
        result = json.loads((result_directory / f"{target['environment']}--{target['target']}.json")
                            .read_text())
        text = result.get("plan_text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Missing readable Terraform plan for {label}")
        # Escape HTML so resource values cannot add markup to the PR comment.
        text = html.escape(text).encode("utf-8")
        truncated = len(text) > budget
        excerpt = text[:budget].decode("utf-8", errors="ignore")
        status = "changes" if result["changes"] else "no changes"
        body += (f"<details open>\n<summary>{label} — {status}</summary>\n\n"
                 f"<pre>{excerpt}</pre>\n\n")
        if truncated:
            body += f"Plan text truncated to fit the comment. [Full plan in job logs]({run_url}).\n\n"
        body += "</details>\n\n"
    body += "Production changes require approval in `proxmox-prod-apply`.\n"
    return body


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
        if environment not in {"dev", "prod"} or name not in TARGETS:
            raise ValueError("Invalid deployment target")
        for flag in ("terraform", "destroy"):
            if type(target[flag]) is not bool:
                raise ValueError(f"Invalid {flag} flag")
        if target["destroy"] and (context["GITHUB_EVENT_NAME"] != "workflow_dispatch"
                                  or context["GITHUB_REF"] != "refs/heads/main"
                                  or context.get("DEPLOYMENT_MODE") != "destroy"):
            raise ValueError("Destroy requires an explicit manual request on main")
        changes = False
        if target["terraform"]:
            directory = f"terraform/workloads/{environment}/{name}"
            if target["directory"] != directory:
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
        rows.append(f"| {environment}/{name} | "
                    f"{'destroy' if changes and target['destroy'] else 'apply' if changes else 'skip'} |")
        if changes:
            automatic_dev = (environment == "dev" and context["GITHUB_EVENT_NAME"] == "push"
                             and context["GITHUB_REF"] == "refs/heads/main")
            approval = ("proxmox-dev-auto-apply" if automatic_dev else
                        f"proxmox-{environment}-apply")
            deployments.append(dict(target, terraform=changes,
                                    approval_environment=approval))
    return deployments, rows


def main():
    targets = json.loads(os.environ["TARGETS_JSON"])
    result_directory = Path(os.environ["PLAN_RESULTS_DIRECTORY"])
    deployments, rows = prepare(targets, result_directory, os.environ)
    body = preview(targets, result_directory, rows, os.environ)
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"matrix={json.dumps(deployments, separators=(',', ':'))}\n")
        output.write(f"has-deployments={str(bool(deployments)).lower()}\n")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
        summary.write(body)
    if os.environ.get("PLAN_COMMENT_PATH"):
        Path(os.environ["PLAN_COMMENT_PATH"]).write_text(body)


if __name__ == "__main__":
    main()
