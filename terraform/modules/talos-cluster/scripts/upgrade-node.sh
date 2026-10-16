#!/usr/bin/env bash
# Explicitly upgrade ONE node, with full cluster health checks before and after.
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "Usage: TALOSCONFIG=/secure/talosconfig bash $0 NODE INSTALLER_IMAGE CONTROL_PLANE_IPS WORKER_IPS" >&2
  echo 'Pass comma-separated IP lists; use an empty fourth argument for no workers.' >&2
  exit 1
fi
: "${TALOSCONFIG:?Set TALOSCONFIG to the cluster administrator configuration}"
node=$1
installer_image=$2
control_planes=$3
workers=$4
endpoint=${control_planes%%,*}

if [[ -z "$node" || "$node" == *,* || -z "$endpoint" || -z "$installer_image" ]]; then
  echo 'Provide exactly one node, an installer image, and at least one control-plane address.' >&2
  exit 1
fi
if [[ ",$control_planes,$workers," != *",$node,"* ]]; then
  echo 'The target node must be in the supplied cluster node lists.' >&2
  exit 1
fi

health_args=(--talosconfig "$TALOSCONFIG" --endpoints "$endpoint" --nodes "$endpoint"
  health --control-plane-nodes "$control_planes" --wait-timeout 15m)
if [[ -n "$workers" ]]; then
  health_args+=(--worker-nodes "$workers")
fi

talosctl "${health_args[@]}"
talosctl --talosconfig "$TALOSCONFIG" --endpoints "$node" --nodes "$node" \
  upgrade --image "$installer_image" --wait
talosctl "${health_args[@]}"
