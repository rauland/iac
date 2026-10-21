# Agent development server

Replace the old `ansible` development server with a freshly provisioned Ubuntu
24.04 host, then apply this bootstrap. Server provisioning and configuration are
separate: the bootstrap connects to an existing SSH address and does not create,
rename, or delete Proxmox guests.

For a server hosting disposable Docker or Podman environments, prefer a dedicated
Proxmox VM with its own kernel. A reasonable starting allocation is 4 vCPUs,
8 GB RAM, and a 60 GB disk; adjust for concurrent tasks and project dependencies.
An unprivileged Proxmox LXC is also useful when Codex runs directly inside each
LXC. Running Podman inside LXC adds nested-container requirements.

See [Ubuntu installation ISO instructions](ubuntu24/README.md) for a fresh VM
installation that includes the guest agent before first boot.

## Bootstrap a fresh server

The new host needs Ubuntu 24.04, Python 3, systemd, and SSH access through its
initial administrator account with sudo. Verify its SSH host key before running
Ansible. Keep the initial account available for administration and recovery.

Ubuntu images must be prepared explicitly for Proxmox guest-agent discovery:
enabling the agent in the Proxmox VM settings does not install it in the guest.
This bootstrap installs `qemu-guest-agent` and starts it on KVM/QEMU guests, but
it must first be reachable over SSH. Either prepare an Ubuntu image with the
agent already installed, or use a known static/DHCP-reserved address for the
initial SSH bootstrap and enable agent-based discovery afterward. Do not wait
for guest-agent IP discovery before the guest has an agent. Proxmox must expose
the agent channel before the service can start.

The existing Terraform module's API seed and automatic SSH enrollment are
currently restricted to AlmaLinux 10. Ubuntu provisioning and enrollment need
their own tested first-boot path before this becomes an automatic CI deployment.

On the machine running this repository, install Ansible and the collections in
`ansible/requirements.yml`, then copy `dev/agent-host.example.yml` to a local
configuration file and replace the example key with your laptop's public key.
Public keys are sufficient; never copy private keys into this configuration.

From the repository root:

```sh
ansible-galaxy collection install -r ansible/requirements.yml
cp dev/agent-host.example.yml /tmp/agent-host.yml
# Edit /tmp/agent-host.yml with your developer username and public SSH key.

ANSIBLE_CONFIG="$PWD/ansible/ansible.cfg" \
ansible-playbook -i 'NEW_SERVER_IP,' -u ubuntu --become \
  ansible/playbooks/agent-host.yml -e @/tmp/agent-host.yml
```

Use `--ask-become-pass` if the initial administrator needs a sudo password. The
trailing comma in the inventory argument is intentional. Only that explicit
server is targeted, independently of the Proxmox dynamic inventory.

The bootstrap installs Podman and rootless dependencies, creates the developer
account and SSH access, enables lingering so sessions survive logout, and
installs `codex-container` on PATH. It builds the pinned Codex image as the
developer and checks that Codex starts. Re-running reconciles configuration
without deleting projects or existing containers. Set
`agent_host_build_image: false` for offline host preparation, then run
`codex-container build` as the developer when networking is available.

User creation normally assigns subordinate UID/GID ranges. If an existing
account has none, the role stops with instructions rather than allocating
ranges that might overlap another account.

## Use the new server

```sh
ssh -t developer@NEW_SERVER_IP
git clone YOUR_REPOSITORY_URL ~/projects/my-project
codex-container start task-one ~/projects/my-project
codex-container attach task-one
```

Inside the container, run `codex login --device-auth`, then `codex`. Detach with
**Ctrl-b, then d**; reconnect with `codex-container attach task-one`. When finished,
run `codex-container stop task-one` on the host. Project files persist, while
the container's home and login are removed. See the [container guide](codex/README.md)
for lifecycle details.

For editor access, follow the [VS Code connection guide](vscode.md) to attach
to the same task container through Remote - SSH and Dev Containers.

## Credentials

The bootstrap installs your public SSH keys. Codex login happens inside each
disposable container; its login cache disappears when that container is stopped.
Use `codex-container start NAME PROJECT --env-file FILE` to supply development
tokens and optionally `--credentials-dir DIRECTORY` for files such as an Ansible
SSH key. Credentials are selected explicitly at container creation; `.bashrc`
and image builds are unchanged. See the [credential setup guide](credentials.md)
and [example variable names](dev.env.example).

For a GitHub identity that may push topic branches and open PRs while reserving
default-branch merges for the owner, follow the [GitHub App setup](github.md).

Create the replacement alongside the old server, verify SSH and a complete
agent task, and move repositories deliberately. Change DNS or the server name
after validation. Retire the old server separately after checking its data.
