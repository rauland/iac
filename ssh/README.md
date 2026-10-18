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

CI keeps committed host pins and enrolls unpinned managed guests through the
authenticated Proxmox API and QEMU guest agent. It reads only
`/etc/ssh/ssh_host_ed25519_key.pub`, verifies TLS, and refuses API redirects.
The guest must match the selected environment and target in Ansible inventory,
the selected Terraform backend state (node, VM ID, name, pool and tag), and live
Proxmox pool membership and configuration. Deposed instances and disabled roots
cannot supply new trust. For `common`, the enabled sandbox and Vault states in
the selected environment supply the managed guest identities.

Enrollment uses the existing `tf-ENVIRONMENT-apply@pve!ci` token; its VM admin
role already grants guest-agent file access within its own pool. The
`ansible-ENVIRONMENT` inventory token stays audit-only. No file-read, file-write
or unrestricted guest-agent permissions are added to it. Proxmox's file-read
permission can read arbitrary guest files, so it must not be added to an
inventory token just to obtain a public key. Enrollment never uses guest-exec.

Only guests without a committed pin use this bootstrap path. Existing pins
(including hashed entries) remain authoritative: changed keys still stop SSH
and require an explicit pin update. Runtime trust is written with mode `0600`
inside the temporary SSH credential directory and removed with it, including
after failures. It is not committed or uploaded as an artifact. Each CI run
can obtain an unpinned guest's key again through the same trusted channel.

The guest agent must already be installed and running in the cloud image;
installing it later through Ansible cannot bootstrap the first SSH connection.
Enrollment waits up to 36 file-read attempts for guest-agent readiness and
fails closed on permission, TLS, state or identity errors. It never falls back
to trusting network scans. Configuration-only CI runs also install Terraform
so enrollment can initialize the selected backend and read state without
refreshing or applying infrastructure. The existing apply identity's state
credentials are used; no additional state permissions are granted.

The deploy job already makes its apply token available at job scope. These
steps share that trusted deployment boundary; separate steps do not isolate
the apply credential from Ansible. This change does not create a separate
credential boundary.

For local runs, or to pin a guest explicitly, obtain its host public key or
fingerprint through a trusted console or an existing verified SSH connection:

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

Local runs use the committed environment trust file by default. Set
`ANSIBLE_KNOWN_HOSTS_FILE` to an existing, separately verified runtime trust file
when needed; strict host checking remains enabled. Relative paths resolve from
the `ansible` directory. Paths containing quotes, backslashes, newlines, `$` or
`%` are rejected to prevent parser ambiguity and SSH path expansion.

## Rotation

The Ansible-user role installs the environment's public key, removes the retired
shared key and removes the other environment's CI key if present. Unrelated
authorized keys and existing group memberships are preserved. CI keys cannot
forward agents, ports or X11. The role requires that each host belongs to the
requested Proxmox pool.

For rotation, retain the old private key and public key until the replacement
has been verified. Generate the new pair outside Terraform, replace the
environment's public key above, and retain the old public key in the role's
`automation_user_retired_ssh_keys` list. Then:

1. Install the new public key on every guest tagged `common` using the old credential
   and `automation_user_remove_retired_keys=false`.
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
  --limit 'proxmox_pool_dev:&tag_common' \
  -e automation_user_remove_retired_keys=false
```

After verifying the replacement on every guest and switching to its private key,
run the same command with `automation_user_remove_retired_keys=true`.

Run deployments from the commit containing the replacement public key and role.
Do not rerun old deployment commits: their role may reinstall the retired key.

Existing VMs ignore Terraform changes to their initialization block. Changing
the bootstrap public key does not rotate SSH access in those guests; use the
Ansible migration above. Retired public keys under `public_keys/retired/` are
revocation records, not trusted credentials.

Run `python3 -m unittest discover -s ssh -p 'test_*.py'` for credential handling
and offline host enrollment tests (requires `requests`), and
`python3 ansible/tests/test_run_playbook.py` for environment selection tests.
