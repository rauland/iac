# automation_user

Create the Ansible automation account, install its environment-specific SSH key,
and optionally remove retired and other-environment automation keys. Unrelated
authorized keys are preserved.

Requires `ansible.posix`, an existing SSH connection with privilege escalation,
and membership in the selected `proxmox_pool_dev` or `proxmox_pool_prod` inventory
group. The role maintains access; cloud-init must bootstrap SSH and sudo access
before the first run. It does not configure sudo privileges.

| Variable | Default | Purpose |
| --- | --- | --- |
| `automation_user_name` | `ansible` | Automation account name. |
| `automation_user_shell` | `/bin/bash` | Login shell. |
| `automation_user_home` | `/home/{{ automation_user_name }}` | Home directory. |
| `automation_user_groups` | `[]` | Supplementary groups; omitted when empty. |
| `automation_user_environment` | `ANSIBLE_ENVIRONMENT` environment variable | Required environment: `dev` or `prod`. |
| `automation_user_ssh_key` | Repository public key for the selected environment | Key installed with agent, port, and X11 forwarding disabled. |
| `automation_user_remove_retired_keys` | `true` | Remove keys listed below after installing the current key. |
| `automation_user_retired_ssh_keys` | Retired shared key and the other environment's key | Keys to remove from the account. |

The default key lookups expect playbooks under `ansible/playbooks`. Override the
key variables when using this role elsewhere. There are no role dependencies.

For staged key rotation, use [the SSH access guide](../../../ssh/README.md)
and `playbooks/ssh-access.yml`.
