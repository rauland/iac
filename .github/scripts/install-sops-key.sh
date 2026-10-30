#!/usr/bin/env bash
# Install the SOPS age private key Flux decrypts with as flux-system/sops-age.
# Runs in the apply job only: plan roles cannot read /iac/<env>/flux, and the
# key never enters Terraform state or the saved plan.
set -euo pipefail
umask 077

environment=${1:?Expected an environment}
: "${SOPS_AGE_KEY:?Load /iac/$environment/flux before installing the SOPS key}"
: "${TF_VAR_state_bucket:?Set the TF_STATE_BUCKET repository variable}"
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT

if [[ "$SOPS_AGE_KEY" != *AGE-SECRET-KEY-* ]]; then
  echo "::error::SOPS_AGE_KEY is not an age private key." >&2
  exit 1
fi

# Read the kubeconfig straight from the talos root's state; this role can
# read every state object in its environment, and no init is needed.
aws s3 cp --only-show-errors "s3://$TF_VAR_state_bucket/terraform/$environment/talos.tfstate" "$scratch/state.json"
jq -er '.outputs.kubeconfig.value' "$scratch/state.json" > "$scratch/kubeconfig"
rm "$scratch/state.json"
export KUBECONFIG="$scratch/kubeconfig"

printf '%s\n' "$SOPS_AGE_KEY" > "$scratch/age.agekey"
kubectl --namespace flux-system create secret generic sops-age \
  --from-file=age.agekey="$scratch/age.agekey" --dry-run=client --output=yaml |
  kubectl apply --filename=- > /dev/null
echo "Installed flux-system/sops-age."
