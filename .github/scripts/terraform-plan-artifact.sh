#!/usr/bin/env bash
# Encrypt/decrypt a saved plan and its exact provider dependency selections.
set -euo pipefail
umask 077

mode=${1:?Expected encrypt or decrypt}
root=${2:?Expected Terraform root directory}
artifact=${3:?Expected encrypted artifact path}
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
export GNUPGHOME="$scratch/gnupg"
mkdir -m 700 "$GNUPGHOME"

case "$mode" in
  encrypt)
    : "${TF_PLAN_PUBLIC_KEY:?Set the TF_PLAN_PUBLIC_KEY repository variable}"
    printf '%s\n' "$TF_PLAN_PUBLIC_KEY" > "$scratch/public.asc"
    tar -C "$root" -cf - tfplan .terraform.lock.hcl .tf-tags.json .cloud-init |
      gpg --batch --yes --trust-model always \
        --recipient-file "$scratch/public.asc" \
        --output "$artifact" --encrypt
    ;;
  decrypt)
    : "${TF_PLAN_PRIVATE_KEY:?Set TF_PLAN_PRIVATE_KEY in the selected apply environment}"
    printf '%s\n' "$TF_PLAN_PRIVATE_KEY" > "$scratch/private.asc"
    gpg --batch --import "$scratch/private.asc"
    # Verify the entire encrypted message before extracting any plaintext.
    gpg --batch --yes --pinentry-mode loopback --passphrase '' \
      --output "$scratch/plan.tar" --decrypt "$artifact"
    tar -C "$root" -xf "$scratch/plan.tar" tfplan .terraform.lock.hcl .tf-tags.json .cloud-init
    ;;
  *)
    echo "Unknown mode: $mode (expected encrypt or decrypt)" >&2
    exit 1
    ;;
esac
