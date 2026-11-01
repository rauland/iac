#!/usr/bin/env bash
# One-time Proxmox host preparation that the Proxmox API cannot do: create the
# ZFS dataset each environment's Kubernetes storage (k8s-<environment>) uses.
# Run as root from the host console before applying platform/access. Safe to
# run again: existing datasets are checked, not changed.
#
# Usage: prepare-host.sh [pool] [environment...]   (defaults: nas dev prod)
set -euo pipefail

pool=${1:-nas}
shift || true
environments=("$@")
[[ ${#environments[@]} -gt 0 ]] || environments=(dev prod)

if ! zpool list -H -o name "$pool" >/dev/null 2>&1; then
  echo "ZFS pool '$pool' does not exist." >&2
  exit 1
fi

for environment in "${environments[@]}"; do
  if [[ ! $environment =~ ^[a-z0-9-]+$ ]]; then
    echo "Invalid environment name: $environment" >&2
    exit 1
  fi
  dataset="$pool/k8s-$environment"
  if type=$(zfs get -H -o value type "$dataset" 2>/dev/null); then
    if [[ $type != filesystem ]]; then
      echo "$dataset exists but is a $type, not a filesystem dataset." >&2
      exit 1
    fi
    echo "exists: $dataset"
  else
    zfs create "$dataset"
    echo "created: $dataset"
  fi
done
