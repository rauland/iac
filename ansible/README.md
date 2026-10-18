# Ansible deployment targets

Use `bash ansible/run-playbook.sh ENVIRONMENT TARGET` from the repository root.
The GitHub Actions composite action uses the same runner. Environments are `dev`
and `prod`; supported targets are listed below.

| Target | Hosts tagged `common` | Other hosts | Host selection |
| --- | --- | --- | --- |
| `common` | `common.yml` | None | Environment pool and `common` tag |
| `sandbox` | `common.yml`, then `sandbox.yml` | `sandbox.yml` | Environment pool and `sandbox` tag |
| `vault` | `common.yml`, then `vault.yml` | `vault.yml` | Environment pool and `vault` tag |

The `common` tag adds timezone, automation-user, and package configuration from
`common.yml` before the selected service playbook. All VMs with the selected
target tag receive `vault.yml` or `sandbox.yml`, including VMs tagged `common`. VMs
without `common` skip the baseline; VMs without any matching tag receive no
playbook. A baseline failure stops the service playbook. `sandbox.yml` installs
Podman and an Nginx site on sandbox guests also tagged `podman`. Use the runner
to select the environment and target.

`common` identifies the shared baseline consistently across the VM tag,
`tag_common` inventory group, runner target, and `common.yml` playbook. Run only
the baseline with `bash ansible/run-playbook.sh dev common`. Baseline package
variables live in `inventory/group_vars/tag_common.yml`.

## Roles and OS families

| Role | Responsibility |
| --- | --- |
| [`system_timezone`](roles/system_timezone/README.md) | Set the system timezone. |
| [`automation_user`](roles/automation_user/README.md) | Maintain the automation account and environment-specific SSH keys. |
| [`system_packages`](roles/system_packages/README.md) | Install baseline and additional packages using the host's package manager. |
| [`podman`](roles/podman/README.md) | Run the sandbox Nginx site with Podman and a systemd Quadlet. |
| [`vault`](roles/vault/README.md) | Install Vault, obtain Cloudflare DNS TLS certificates, and configure storage and systemd. |

Playbooks select baseline or service responsibilities. Roles handle OS differences
using gathered `ansible_facts['os_family']`, so service playbooks do not duplicate
the baseline for each distribution. The baseline roles use portable modules;
package names still need to be valid for each target distribution.

The current guests are AlmaLinux. Vault supports the `RedHat` family with DNF
and EPEL: `roles/vault/tasks/RedHat.yml` installs its repositories and packages,
and `roles/vault/tasks/common.yml` configures the service. The role rejects
other OS families before making changes. To add another family, add its package
tasks and extend the assertion and task imports in `roles/vault/tasks/main.yml`;
keep shared configuration in `common.yml`. This follows Ansible's documented
[OS-family role pattern](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_reuse_roles.html).

New roles should contain a README and the files they use. Put configurable,
role-prefixed inputs in `defaults/main.yml`; add handlers, templates, static
files, or internal variables as needed. These internal roles keep their
descriptions in their READMEs and omit unused Galaxy publishing metadata.
Maintain offline regression tests in `ansible/tests` instead of retaining
generated localhost test playbooks.

## Linting

CI runs the Ansible Lint `production` profile with warnings treated as failures.
It checks all Ansible content, including YAML formatting, module names,
variable prefixes, and playbook syntax. It contributes to the required `CI`
check. Plans and deployments depend on that check succeeding. The consolidated
[deployment workflow](../.github/workflows/terraform.yml) supports manual
`configuration` mode for Ansible-only runs; production still requires approval.

The shared `.github/actions/ansible-lint` action uses Python 3.12 and exact
tool versions from `requirements-lint.txt`. Collections are pinned in
`requirements.yml` and installed before linting. The lint step uses
`tests/inventory.yml` and offline mode, so it needs no infrastructure credentials.

Run the same checks locally from the repository root with Python 3.12 or newer:

```sh
cd ansible
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-lint.txt
export PATH="$PWD/.venv/bin:$PATH"
export ANSIBLE_COLLECTIONS_PATH="$PWD/.venv/collections"
export ANSIBLE_INVENTORY="$PWD/tests/inventory.yml"
ansible-galaxy collection install -r requirements.yml
ansible-lint --offline --strict .
```

The YAML policy in `.yamllint` is also used by Ansible Lint. Fix findings in the
content; the configuration contains no ignored rules or baseline exemptions.

## Inventory and access

Proxmox tags create groups prefixed with `tag_`, such as `tag_common` and
`tag_vault`, to avoid collisions with VM names. The inventory plugin creates
`proxmox_pool_dev` and `proxmox_pool_prod` from Proxmox resource pool membership.
The runner intersects that pool group with the target tag, for example
`proxmox_pool_dev:&tag_vault`. Assign each VM to its environment pool and tag its
target; add `common` when it should also receive the shared baseline.
Environment tags such as `dev` and `prod` are optional and do not select hosts.
Unpooled VMs are excluded. Group variable files retain their `tag_` names.

Preview a target before applying:

```sh
bash ansible/run-playbook.sh dev vault --list-hosts
bash ansible/run-playbook.sh dev vault --check
```

Apply the updated Terraform workload definitions to update existing VM tags
before running the new playbooks against those VMs. Renaming a tag in this
repository does not change tags on running VMs by itself.

The inventory reads Proxmox credentials from `PROXMOX_URL`, `PROXMOX_USER`,
`PROXMOX_TOKEN_ID`, and `PROXMOX_TOKEN_SECRET`. The Vault role also needs
`CLOUDFLARE_API_TOKEN`; both deployment workflows pass it from GitHub environment
secrets. SSH and sudo access as `ansible` must already be available on guests.

Inventory uses the pinned `community.proxmox` version in `requirements.yml`.
Install it from the repository root to override a different version bundled
with Ansible:

```sh
ansible-galaxy collection install -r ansible/requirements.yml --force
```

Version 2.1.0 queries `/cluster/status`, which requires global `Sys.Audit`;
version 2.0.0
works with the existing pool-scoped inventory tokens. Test inventory with those
tokens before upgrading the collection. An inventory source that cannot be
parsed is a fatal error, so API permission failures cannot silently skip a run.

Dev and prod have separate CI SSH key pairs. Public keys are shared with
Terraform under `ssh/public_keys/ENVIRONMENT/ansible-ci.pub`; private keys live
in their matching GitHub apply environments. For local runs, the runner uses
`ssh/.credentials/ENVIRONMENT/ansible-ci` unless `ANSIBLE_PRIVATE_KEY_FILE` is
set. It selects `ssh/known_hosts/ENVIRONMENT`, enforces host verification and
disables SSH agent fallback. New or rebuilt guests need verified host keys added
before deployment. See [SSH access and rotation](../ssh/README.md) for setup and
the dedicated `ssh-access.yml` migration playbook.

Run offline selection tests and syntax checks without contacting Proxmox or hosts:

```sh
python3 -m unittest discover -s ansible/tests -p 'test_*.py'
bash ansible/run-playbook.sh dev common -i tests/inventory.yml --syntax-check
bash ansible/run-playbook.sh dev vault -i tests/inventory.yml --syntax-check
bash ansible/run-playbook.sh dev sandbox -i tests/inventory.yml --syntax-check
```

Additional Ansible arguments pass through unchanged. Relative inventory paths in
these commands are resolved from the `ansible` directory.
