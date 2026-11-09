#!/usr/bin/env bash
# Store or fetch a saved plan and its exact provider dependency selections.
#
# Plans go to plans/<environment>/<target>/<run>-<attempt>.tar in the state
# bucket. Only that environment's plan role can write there and only its apply
# role can read, so neither the other environment nor anyone on GitHub can.
# The archive's SHA-256 travels in the run's plan result, so the apply refuses
# any object other than the one this run uploaded.
set -euo pipefail
umask 077

mode=${1:?Expected upload or download}
root=${2:?Expected Terraform root directory}
environment=${3:?Expected environment}
target=${4:?Expected target}
: "${TF_STATE_BUCKET:?Set TF_STATE_BUCKET to the state bucket name}"
: "${GITHUB_RUN_ID:?}" "${GITHUB_RUN_ATTEMPT:?}"
key="plans/$environment/$target/$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT.tar"
files=(tfplan .terraform.lock.hcl .tf-plan.json)
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT

case "$mode" in
  upload)
    result=${5:?Expected plan result file}
    tar -C "$root" -cf "$scratch/plan.tar" "${files[@]}"
    digest=$(sha256sum "$scratch/plan.tar" | cut -d' ' -f1)
    # Never replace an existing object: each run attempt writes its own key.
    aws s3api put-object --bucket "$TF_STATE_BUCKET" --key "$key" \
      --body "$scratch/plan.tar" --if-none-match '*' > /dev/null
    jq --arg digest "$digest" '.archive_sha256 = $digest' "$result" > "$scratch/result.json"
    mv "$scratch/result.json" "$result"
    ;;
  download)
    expected=${5:-}
    if [[ ! "$expected" =~ ^[0-9a-f]{64}$ ]]; then
      echo "Expected the saved plan's SHA-256 from this run's plan result" >&2
      exit 1
    fi
    aws s3api get-object --bucket "$TF_STATE_BUCKET" --key "$key" "$scratch/plan.tar" > /dev/null
    # Check the whole archive before extracting anything from it.
    if ! printf '%s  %s\n' "$expected" "$scratch/plan.tar" | sha256sum --check --strict --status; then
      echo "Saved plan $key is not the archive this run uploaded" >&2
      exit 1
    fi
    tar -C "$root" -xf "$scratch/plan.tar" "${files[@]}"
    ;;
  *)
    echo "Unknown mode: $mode (expected upload or download)" >&2
    exit 1
    ;;
esac
