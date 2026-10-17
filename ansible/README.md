# Ansible deployment targets

Use `bash ansible/run-playbook.sh ENVIRONMENT TARGET` from the repository root.
The GitHub Actions composite action uses the same runner. Environments are `dev`
and `prod`; supported targets are listed below.

| Target | Managed hosts | Other hosts | Host selection |
| --- | --- | --- | --- |
| `managed` | `managed.yml` | None | Environment pool and `managed` tag |
| `sandbox` | `managed.yml`, then `sandbox.yml` | `sandbox.yml` | Environment pool and `sandbox` tag |
| `vault` | `managed.yml`, then `vault.yml` | `vault.yml` | Environment pool and `vault` tag |

The `managed` tag adds timezone, Ansible-user, and package configuration from
`managed.yml` before the selected service playbook. All VMs with the selected
target tag receive `vault.yml` or `sandbox.yml`, including managed VMs. VMs
without `managed` skip the baseline; VMs without any matching tag receive no
playbook. A baseline failure stops the service playbook. `sandbox.yml` currently
has no additional tasks. Use the runner to select the environment and target.

Proxmox tags create groups prefixed with `tag_`, such as `tag_managed` and
`tag_vault`, to avoid collisions with VM names. The inventory plugin creates
`proxmox_pool_dev` and `proxmox_pool_prod` from Proxmox resource pool membership.
The runner intersects that pool group with the target tag, for example
`proxmox_pool_dev:&tag_vault`. Assign each VM to its environment pool and tag its
target; add `managed` when it should also receive the managed baseline.
Environment tags such as `dev` and `prod` are optional and do not select hosts.
Unpooled VMs are excluded. Group variable files retain their `tag_` names.

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
