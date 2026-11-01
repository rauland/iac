# 1. Kubernetes first, no SSH automation

Status: accepted (2026-11-01)

## Context

The platform started with general-purpose VMs: cloud images, cloud-init with SSH
keys, host-key enrollment through the Proxmox guest agent, and Ansible run from
CI over SSH. Alongside them ran hand-built VMs and Proxmox Backup Server for
whole-VM backups.

That model needed long-lived credentials on the network: SSH private keys for
CI and administrators, pinned host keys, and root access to hosts to configure
them. A host could only be rebuilt by replaying its configuration over SSH, and
the backup server itself needed hand-built rebuilds.

Meanwhile the Talos cluster showed a different model: nodes configured entirely
through an API, workloads declared in Git and pulled by Flux, and data handled
at the volume level.

## Decision

- **Workloads run on Kubernetes.** New services are Kubernetes manifests that
  Flux reconciles from `main`, each with its own Flux Kustomization.
- **Nodes are managed through APIs.** The only VMs are Talos nodes, created
  through the Proxmox API and configured through the Talos API. The Proxmox
  host is installed by hand and otherwise managed through its API.
- **No automation logs in to a host.** CI, Terraform and Flux never use SSH.
  The SSH key infrastructure, Ansible and the cloud-init VM module are removed.
- **Data is protected at the volume level.** Volumes are LUKS-encrypted on the
  nodes and opted in to VolSync backups, encrypted by restic before upload to
  S3, which the cluster reaches through OIDC instead of access keys. See
  [backups and recovery](../backups.md).

## Consequences

- Rebuilds need no hands-on steps beyond the administrator Terraform roots: the
  cluster comes from Terraform, apps from Git, and data from backups.
- No SSH private keys, host-key pins or host passwords exist for automation.
- Anything that cannot run on Kubernetes, such as an appliance OS, needs an
  explicit exception: a VM managed only through the Proxmox API, with no SSH
  configuration management, recorded as a new decision.
- People can still reach files through services that expose only what they
  need, such as an SMB or web file manager on a single volume, rather than a
  shell on a host.
