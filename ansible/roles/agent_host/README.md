# Agent development host

Bootstrap a fresh Ubuntu 24.04 server for SSH access and disposable Codex
containers. This role installs rootless Podman, creates a developer account,
installs its public keys, enables systemd lingering, and installs the container
helper. It builds the image as that account and smoke-tests `codex --version`.
It installs `qemu-guest-agent` and starts it on KVM/QEMU guests; see the guide
for the separate first-boot networking and guest-agent prerequisite.

Use the standalone `playbooks/agent-host.yml` against an explicit SSH address.
It is deliberately separate from the Proxmox VM configuration runner: the
replacement machine does not have to exist in the current inventory.

See [the fresh-server bootstrap guide](../../../dev/README.md) for commands.
Inputs live in `defaults/main.yml`; public keys must be supplied explicitly.
The developer account receives no host sudo privileges. Keep the server's
initial administrator account for host maintenance.
