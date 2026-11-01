"""Bind a saved plan to its commit, run, target and provider lock before apply."""

import hashlib
import json
from pathlib import Path


MANIFEST = ".tf-plan.json"


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expected(directory, context, environment, target, destroy):
    directory = Path(directory)
    return {"version": 2, "environment": environment, "target": target, "destroy": destroy,
            "sha": context["GITHUB_SHA"], "run_id": context["GITHUB_RUN_ID"],
            "run_attempt": context["GITHUB_RUN_ATTEMPT"],
            "plan_sha256": file_hash(directory / "tfplan"),
            "lock_sha256": file_hash(directory / ".terraform.lock.hcl")}


def write_manifest(directory, context, environment, target, destroy):
    (Path(directory) / MANIFEST).write_text(
        json.dumps(expected(directory, context, environment, target, destroy)) + "\n")


def check_manifest(directory, context, environment, target, destroy):
    manifest = json.loads((Path(directory) / MANIFEST).read_text())
    if manifest != expected(directory, context, environment, target, destroy):
        raise ValueError("Plan manifest does not match this saved plan, dependencies, target and run")
