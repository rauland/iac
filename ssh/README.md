# SSH automation access

Dev and prod use different Ed25519 key pairs for the `ansible` account. Human
administrators should use their own accounts and keys. Proxmox pool permissions
control API access; guest SSH access is controlled separately by authorized keys.

| Environment | Public key | Private-key secret | Trusted host keys |
| --- | --- | --- | --- |
| Dev | [public_keys/dev/ansible-ci.pub](public_keys/dev/ansible-ci.pub) | `proxmox-dev-apply` and `proxmox-dev-auto-apply` → `SSH_PRIVATE_KEY_ANSIBLE` | [known_hosts/dev](known_hosts/dev) |
| Prod | [public_keys/prod/ansible-ci.pub](public_keys/prod/ansible-ci.pub) | `proxmox-prod-apply` → `SSH_PRIVATE_KEY_ANSIBLE` | [known_hosts/prod](known_hosts/prod) |

The same public-key files are used by Terraform for first boot and Ansible for
ongoing access management. VM modules require explicit `ssh_public_keys`; they
have no shared key or path default. A prod workload root must explicitly select
the prod public key, for example:

```hcl
pool_id         = "prod"
ssh_public_keys = [file("${path.root}/../../../../ssh/public_keys/prod/ansible-ci.pub")]
```

Generate private keys outside Terraform so they never enter Terraform state.
Local recovery copies belong in the gitignored `ssh/.credentials/ENVIRONMENT/`
directory (directory mode `700`, key mode `600`). The local runner defaults to
`ssh/.credentials/ENVIRONMENT/ansible-ci`; set `ANSIBLE_PRIVATE_KEY_FILE` to use
another protected copy. Never use a personal administrator key as a CI secret.

CI passes the private key through an environment variable to `setup-ci.sh`.
The script checks that it matches the selected environment's public key, creates
an owner-only temporary directory and exports `ANSIBLE_PRIVATE_KEY_FILE`.
The Ansible action removes that directory on success or failure. Keys are not
interpolated into executable shell code or written to the runner's default
personal identity path.

## Host verification

`ansible/run-playbook.sh` enables strict host checking and selects the matching
environment's `known_hosts` file. It also disables SSH agent fallback and uses
the explicitly selected private key. Unknown or changed host keys stop the
connection. Prod currently has no SSH guests, so its trust file has no host keys.

Before adding a new guest, obtain its host public key or fingerprint through a
trusted console or an existing verified SSH connection:

```sh
# Run inside the guest, not on the Proxmox host.
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
sudo cat /etc/ssh/ssh_host_ed25519_key.pub
```

Add `ADDRESS ssh-ed25519 PUBLIC_KEY` to `ssh/known_hosts/ENVIRONMENT`. If using
`ssh-keyscan` to collect the key, compare its fingerprint with the trusted
console output before adding it. Update the entry when a DHCP address changes;
rebuilding a VM also requires verifying its new host key. Review these files as
access configuration even though their contents are public.

For a newly provisioned VM, Terraform can finish before the first Ansible run
stops on an unknown host key. Verify and commit that host key, then run the
Ansible workflow again. This setup deliberately requires host enrollment; it
does not automatically trust keys reported by the network.

## Rotation

The Ansible-user role installs the environment's public key, removes the retired
shared key and removes the other environment's CI key if present. Unrelated
authorized keys and existing group memberships are preserved. CI keys cannot
forward agents, ports or X11. The role requires that each host belongs to the
requested Proxmox pool.

For rotation, retain the old private key and public key until the replacement
has been verified. Generate the new pair outside Terraform, replace the
environment's public key above, and retain the old public key in the role's
`ansible_user_retired_ssh_keys` list. Then:

1. Install the new public key on every managed guest using the old credential
   and `ansible_user_remove_retired_keys=false`.
2. Verify a fresh SSH connection and noninteractive sudo using the new key on
   every guest. Disable multiplexed connection reuse during this verification.
3. Upload the new private key to the matching GitHub environment secrets (both
   dev apply environments for a dev key) via
   stdin, without printing it or placing it in command-line arguments. Push the
   matching public key and workflow changes together with the cutover.
4. Use the new credential to run the SSH-access playbook with retired-key
   removal enabled. Verify that the new key works and the retired and
   other-environment keys cannot log in to the `ansible` account.

The dedicated playbook changes only SSH account access, avoiding unrelated
service configuration. Run from the repository root, using your scoped Proxmox
inventory credentials and an explicitly selected private key:

```sh
export ANSIBLE_ENVIRONMENT=dev
export ANSIBLE_PRIVATE_KEY_FILE=/absolute/path/to/the/current/private/key
export ANSIBLE_HOST_KEY_CHECKING=True
export ANSIBLE_SSH_COMMON_ARGS="-o IdentitiesOnly=yes -o IdentityAgent=none -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$PWD/ssh/known_hosts/dev"
ANSIBLE_CONFIG="$PWD/ansible/ansible.cfg" ansible-playbook \
  -i "$PWD/ansible/inventory/proxmox.yml" \
  "$PWD/ansible/playbooks/ssh-access.yml" \
  --limit 'proxmox_pool_dev:&tag_managed' \
  -e ansible_user_remove_retired_keys=false
```

After verifying the replacement on every guest and switching to its private key,
run the same command with `ansible_user_remove_retired_keys=true`.

Run deployments from the commit containing the replacement public key and role.
Do not rerun old deployment commits: their role may reinstall the retired key.

Existing VMs ignore Terraform changes to their initialization block. Changing
the bootstrap public key does not rotate SSH access in those guests; use the
Ansible migration above. Retired public keys under `public_keys/retired/` are
revocation records, not trusted credentials.

Run `python3 ssh/test_setup_ci.py` for credential handling tests and
`python3 ansible/tests/test_run_playbook.py` for environment selection tests.
