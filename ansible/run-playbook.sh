#!/usr/bin/env bash
# Select a target and intersect its hosts with the requested Proxmox pool.
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 ENVIRONMENT TARGET [ansible-playbook options]" >&2
  exit 2
fi
ansible_environment=$1
ansible_target=$2
shift 2
case "$ansible_environment" in
  dev|prod) ;;
  *) echo "Unsupported environment: $ansible_environment" >&2; exit 2 ;;
esac
case "$ansible_target" in
  managed) ansible_playbook=managed.yml; ansible_group=tag_managed ;;
  sandbox) ansible_playbook=sandbox.yml; ansible_group=tag_sandbox ;;
  vault) ansible_playbook=vault.yml; ansible_group=tag_vault ;;
  *) echo "Unsupported target: $ansible_target" >&2; exit 2 ;;
esac

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
repository_root=$(cd .. && pwd)
export ANSIBLE_ENVIRONMENT="$ansible_environment"
export ANSIBLE_HOST_KEY_CHECKING=True
export ANSIBLE_PRIVATE_KEY_FILE="${ANSIBLE_PRIVATE_KEY_FILE:-$repository_root/ssh/.credentials/$ansible_environment/ansible-ci}"
export ANSIBLE_SSH_COMMON_ARGS="-o IdentitiesOnly=yes -o IdentityAgent=none -o StrictHostKeyChecking=yes -o UserKnownHostsFile=\"$repository_root/ssh/known_hosts/$ansible_environment\""
ansible_limit="proxmox_pool_$ansible_environment:&$ansible_group"
# Apply the baseline to managed hosts in this target before its service playbook.
if [[ "$ansible_target" != managed ]]; then
  ansible-playbook ./playbooks/managed.yml --limit "$ansible_limit" "$@"
fi
exec ansible-playbook "./playbooks/$ansible_playbook" --limit "$ansible_limit" "$@"
