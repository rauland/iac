#!/usr/bin/env python3
"""Load SSM parameters into the job environment, masking secrets first.

Each argument is an SSM path such as /iac/dev/plan. Every parameter under it is
exported as an environment variable named after its last path segment, e.g.
/iac/shared/proxmox/PROXMOX_URL -> PROXMOX_URL.

SecureString values are registered with ::add-mask:: line by line before they
are written to GITHUB_ENV, because the runner only redacts values it has been
told about and multi-line keys are matched one line at a time. Values are never
printed otherwise; errors name parameters, not their contents. String
parameters hold non-secret identifiers and are not masked.
"""
import json
import os
import re
import secrets
import subprocess
import sys

NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RESERVED_PREFIXES = ("GITHUB_", "ACTIONS_", "AWS_", "RUNNER_TEMP", "RUNNER_TOOL", "LD_")
RESERVED_NAMES = {"PATH", "HOME", "BASH_ENV", "ENV", "NODE_OPTIONS", "PYTHONPATH"}
# Shorter secrets cannot be redacted reliably and would blank out common text.
MIN_SECRET_LENGTH = 8


def fail(message):
    print(f"::error::{message}", flush=True)
    sys.exit(1)


def fetch(path):
    result = subprocess.run(
        ["aws", "ssm", "get-parameters-by-path", "--path", path, "--recursive",
         "--with-decryption", "--output", "json"],
        capture_output=True, text=True,
    )
    if result.returncode:
        # The CLI's error names the operation and path, never a decrypted value.
        fail(f"Could not read SSM path {path}: {result.stderr.strip().splitlines()[-1:]}")
    try:
        return json.loads(result.stdout).get("Parameters", [])
    except json.JSONDecodeError:
        fail(f"Unexpected response while reading SSM path {path}")


def main(paths):
    if not paths:
        fail("Pass at least one SSM path")
    environment_file = os.environ.get("GITHUB_ENV")
    if not environment_file:
        fail("GITHUB_ENV is not set")

    loaded = {}
    for path in paths:
        parameters = fetch(path)
        if not parameters:
            fail(f"No parameters found under {path}")
        for parameter in parameters:
            full_name, value, kind = parameter["Name"], parameter["Value"], parameter["Type"]
            name = full_name.rsplit("/", 1)[-1]
            if not NAME.match(name) or name in RESERVED_NAMES or name.startswith(RESERVED_PREFIXES):
                fail(f"{full_name} does not map to an allowed environment variable name")
            if name in loaded:
                fail(f"{full_name} duplicates {loaded[name][0]}")
            if kind == "SecureString":
                if len(value.strip()) < MIN_SECRET_LENGTH:
                    fail(f"{full_name} is shorter than {MIN_SECRET_LENGTH} characters and cannot be masked safely")
                for line in value.splitlines():
                    if line.strip():
                        print(f"::add-mask::{line}", flush=True)
            elif kind != "String":
                fail(f"{full_name} has unsupported type {kind}")
            loaded[name] = (full_name, value, kind)

    # Masks are registered above before any value reaches the environment file.
    with open(environment_file, "a", encoding="utf-8") as handle:
        for name, (_, value, _) in loaded.items():
            delimiter = f"EOF_{secrets.token_hex(16)}"
            handle.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")

    for name, (full_name, _, kind) in sorted(loaded.items()):
        print(f"Loaded {name} from {full_name} ({kind})", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
