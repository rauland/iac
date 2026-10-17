#!/usr/bin/env python3
"""Export console-ready IAM policies from the mocked Terraform plan; no AWS calls."""

import json
from pathlib import Path
import subprocess


root = Path(__file__).resolve().parent
result = subprocess.run(
    ["terraform", f"-chdir={root}", "test", "-json", "-verbose"],
    capture_output=True, text=True,
)
if result.returncode:
    raise SystemExit("Mocked Terraform tests failed; run terraform test to inspect the failure.")

policies = {}
for line in result.stdout.splitlines():
    event = json.loads(line)
    if event.get("type") != "test_plan":
        continue
    for change in event["test_plan"]["resource_changes"]:
        if change["type"] == "aws_iam_user_policy":
            policies[change["index"]] = json.loads(change["change"]["after"]["policy"])
if len(policies) != 6:
    raise SystemExit("Expected exactly six scoped state policies.")

directory = root / "policies"
directory.mkdir(exist_ok=True)
for name, policy in sorted(policies.items()):
    (directory / f"{name}.json").write_text(json.dumps(policy, indent=2) + "\n")
    print(f"Exported {name}.json")
