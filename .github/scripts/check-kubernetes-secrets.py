#!/usr/bin/env python3
"""Fail if a Kubernetes Secret under kubernetes/ could reach Git unencrypted.

Secrets must live in *.sops.yaml files, and every such file must carry SOPS
metadata and encrypted values. Text checks only, so CI needs no extra tools.
"""

from pathlib import Path
import re
import sys

SECRET = re.compile(r"^kind:\s*Secret\s*$", re.MULTILINE)
SOPS_FILE = re.compile(r".*\.sops\.ya?ml$")


def problems(root):
    found = []
    for path in sorted(Path(root).rglob("*.y*ml")):
        text = path.read_text()
        if SOPS_FILE.match(path.name):
            if not re.search(r"^sops:\s*$", text, re.MULTILINE) or "ENC[AES256_GCM," not in text:
                found.append(f"{path}: not SOPS-encrypted; run sops --encrypt --in-place {path}")
            elif re.search(r"^\s+age:\s*$", text, re.MULTILINE) is None:
                found.append(f"{path}: has no age recipient, so Flux cannot decrypt it")
        elif SECRET.search(text):
            found.append(f"{path}: plain Secret; rename it to *.sops.yaml and encrypt it")
    return found


def main():
    found = problems(sys.argv[1] if len(sys.argv) > 1 else "kubernetes")
    for problem in found:
        print(f"::error::{problem}")
    if found:
        sys.exit(1)
    print("No unencrypted Secrets found.")


if __name__ == "__main__":
    main()
