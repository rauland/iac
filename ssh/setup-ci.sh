#!/usr/bin/env bash
# Materialize an environment's CI SSH key without evaluating its contents as code.
set -euo pipefail

case "${1:-}" in
  setup)
    environment=${2:-}
    case "$environment" in
      dev|prod) ;;
      *) echo 'Select dev or prod for SSH setup.' >&2; exit 2 ;;
    esac
    : "${RUNNER_TEMP:?RUNNER_TEMP is required}"
    : "${GITHUB_ENV:?GITHUB_ENV is required}"
    : "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"
    : "${SSH_PRIVATE_KEY_ANSIBLE:?SSH_PRIVATE_KEY_ANSIBLE is required}"
    repository_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
    umask 077
    directory=$(mktemp -d "$RUNNER_TEMP/ansible-ssh.XXXXXX")
    trap 'rm -rf -- "$directory"' EXIT
    printf '%s\n' "$SSH_PRIVATE_KEY_ANSIBLE" > "$directory/id_ed25519"
    unset SSH_PRIVATE_KEY_ANSIBLE
    ssh-keygen -y -P '' -f "$directory/id_ed25519" > "$directory/public.pub"
    read -r actual_type actual_key _ < "$directory/public.pub"
    read -r expected_type expected_key _ < "$repository_root/ssh/public_keys/$environment/ansible-ci.pub"
    if [[ "$actual_type $actual_key" != "$expected_type $expected_key" ]]; then
      echo "The SSH secret does not match the $environment public key." >&2
      exit 1
    fi
    printf 'ANSIBLE_PRIVATE_KEY_FILE=%s/id_ed25519\n' "$directory" >> "$GITHUB_ENV"
    printf 'directory=%s\n' "$directory" >> "$GITHUB_OUTPUT"
    trap - EXIT
    ;;
  cleanup)
    : "${RUNNER_TEMP:?RUNNER_TEMP is required}"
    directory=${2:-}
    if [[ -z "$directory" ]]; then exit 0; fi
    if [[ "$directory" != "$RUNNER_TEMP/ansible-ssh."* || "${directory#"$RUNNER_TEMP/"}" == */* ]]; then
      echo 'Refusing to remove an unexpected SSH temporary directory.' >&2
      exit 2
    fi
    rm -rf -- "$directory"
    ;;
  *) echo 'Usage: setup-ci.sh setup ENVIRONMENT | cleanup DIRECTORY' >&2; exit 2 ;;
esac
