#!/usr/bin/env bash
# Run an administrator-operated platform playbook. CI never runs these.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 TARGET [ansible-playbook options]" >&2
  exit 2
fi
platform_target=$1
shift
case "$platform_target" in
  pbs) platform_playbook=pbs.yml ;;
  pve) platform_playbook=pve.yml ;;
  *) echo "Unsupported target: $platform_target" >&2; exit 2 ;;
esac

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
repository_root=$(cd .. && pwd)
export ANSIBLE_HOST_KEY_CHECKING=True
export ANSIBLE_PRIVATE_KEY_FILE="${ANSIBLE_PRIVATE_KEY_FILE:-$HOME/.ssh/id_ed25519}"
platform_known_hosts_file=${ANSIBLE_KNOWN_HOSTS_FILE:-$repository_root/ssh/known_hosts/platform}
if [[ ! -f "$platform_known_hosts_file" || ! -r "$platform_known_hosts_file" ]]; then
  echo 'The selected SSH host trust file must exist and be readable.' >&2
  exit 2
fi
case "$platform_known_hosts_file" in
  *\"*|*\'*|*\\*|*%*|*'$'*|*$'\n'*|*$'\r'*) echo 'Unsupported characters in SSH host trust file path.' >&2; exit 2 ;;
esac
# Keep the inner quotes through Ansible's shlex split and SSH's filename-list parser.
export ANSIBLE_SSH_COMMON_ARGS="-o IdentitiesOnly=yes -o IdentityAgent=none -o StrictHostKeyChecking=yes -o UpdateHostKeys=no -o GlobalKnownHostsFile=/dev/null -o 'UserKnownHostsFile=\"$platform_known_hosts_file\"'"
exec ansible-playbook "./playbooks/$platform_playbook" -i ./inventory/platform.yml --limit "$platform_target" "$@"
