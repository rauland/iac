# Ansible deployment targets

Use `bash ansible/run-playbook.sh ENVIRONMENT TARGET` from the repository root.
The GitHub Actions composite action uses the same runner. Environments are `dev`
and `prod`; supported targets are listed below.

| Target | Managed hosts | Other hosts | Host selection |
| --- | --- | --- | --- |
| `managed` | `managed.yml` | None | Environment and `managed` tag |
| `sandbox` | `managed.yml` | `sandbox.yml` | Environment and `sandbox` tag |
| `vault` | `managed.yml` | `vault.yml` | Environment and `vault` tag |

The `managed` tag takes priority: those VMs receive only timezone, Ansible-user,
and package configuration from `managed.yml`. VMs without `managed` receive
`vault.yml` or `sandbox.yml` when they have the corresponding target tag. VMs
without any matching tag receive no playbook. `sandbox.yml` currently has no
additional tasks. `site.yml` runs all matching playbooks with the same rules.
If a VM has both `vault` and `sandbox` but no `managed` tag, both service
playbooks match when using `site.yml`.

Proxmox tags create groups prefixed with `tag_`, such as `tag_managed` and
`tag_vault`, to avoid collisions with VM names. The `dev` and `prod` groups come
from their corresponding environment tags. Tag each VM with its environment and
target; add `managed` when it should receive only managed configuration. The sandbox Terraform
configuration includes these tags; an existing VM gets them on its next Terraform
apply. Group variable files use the same prefixed names.

Preview a target before applying:

```sh
bash ansible/run-playbook.sh dev vault --list-hosts
bash ansible/run-playbook.sh dev vault --check
```

The inventory reads Proxmox credentials from `PROXMOX_URL`, `PROXMOX_USER`,
`PROXMOX_TOKEN_ID`, and `PROXMOX_TOKEN_SECRET`. The Vault role also needs
`CLOUDFLARE_API_TOKEN`; both deployment workflows pass it from GitHub environment
secrets. SSH and sudo access as `ansible` must already be available on guests.

Run offline selection tests and syntax checks without contacting Proxmox or hosts:

```sh
python3 ansible/tests/test_run_playbook.py
bash ansible/run-playbook.sh dev vault -i tests/inventory.yml --syntax-check
bash ansible/run-playbook.sh dev sandbox -i tests/inventory.yml --syntax-check
```

Additional Ansible arguments pass through unchanged. Relative inventory paths in
these commands are resolved from the `ansible` directory.
