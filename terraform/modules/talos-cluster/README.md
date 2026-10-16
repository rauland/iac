# Talos on Proxmox

This module creates Proxmox VMs, boots a custom Talos **metal ISO from CD-ROM**,
installs onto separate SCSI disks through the Talos API, bootstraps one control
plane, checks cluster health, and exposes sensitive client configurations.
It does not use cloud-init, snippets, Proxmox-host SSH, or runner-local credential
resources.

## Deploying the example environment

`terraform/environments/dev/talos` is enabled for local and GitHub Actions
deployments. It participates in automatic discovery and manual `single` or `all`
runs. Forks must adapt the example configuration to their own infrastructure.

1. Set the cluster name, Kubernetes endpoint, bootstrap node, and pinned Talos and
   Kubernetes versions. The dev example pins Talos v1.14.3 and Kubernetes v1.37.1 for a fresh
   deployment. Existing clusters require the sequential upgrade procedure below.
2. Reserve each node's `api_address` on your DHCP server for its `mac_address`.
   The example MACs and addresses are placeholders. The metal ISO initially
   obtains its address through DHCP; a static Talos configuration cannot provide
   network access before that configuration has been applied. For static Talos
   networking, the reserved address and configured IPv4 address must agree.
3. Ensure the runner can reach every node on Talos API port 50000 and the
   Kubernetes API on port 6443 through WireGuard. The nodes need the routes and
   DNS necessary to reach Image Factory and container registries. Set
   `dns_servers` for static nodes (for example, your LAN resolver). A load-balanced
   `cluster_endpoint` must already exist; the module does not create a load
   balancer or a virtual IP.
4. Ensure each selected Proxmox host has `iso_datastore_id` with ISO support and
   `disk_datastore_id` for VM disks. The defaults are `local` and `local-lvm`.
5. Run the Terraform workflow on `main` with environment `dev`, mode `single`,
   and target `talos`. Review the plan before approving apply. Mode `all` for
   `dev` also includes Sandbox and Vault.

To opt out of GitHub Actions deployments, add a `.disabled` file in the root
directory. The marker excludes it from automatic and manual discovery without
changing the module configuration; local Terraform commands are unaffected.
Remove the marker when you want workflow deployments to include it again.

The node map keys must equal `node_name`. Keep keys, API addresses, and
`bootstrap_node` stable. The module derives Proxmox hosts from the node map;
there is no separate `pve_nodes` list that can disagree with it. CPU, memory,
disk capacity, storage override, bridge, VLAN, MAC, VM ID, and YAML patches can be
set per node. Defaults are 2 CPUs, 4096 MiB RAM, and a 32 GiB disk.

VMs use UEFI, q35, VirtIO SCSI, one NIC, and `/dev/sda` as the installation target.
The installation ISO contains `qemu-guest-agent`; waiting for its IP report is
disabled to avoid blocking configuration while the VM is in maintenance mode.
The boot order tries the installed disk before the ISO. The network patch selects
the one physical NIC rather than relying on a Linux interface name.

## Configuration and credentials

Each node gets its own machine configuration, with explicit Talos and Kubernetes
versions. Talos 1.14 and later use dedicated installation, hostname, and resolver
documents to avoid conflicts with generated defaults. Global `config_patches` follow the generated patch, and per-node patches
follow global patches. Configurations are applied with `auto`, which supports
initial installation from maintenance mode (`no_reboot` is rejected there).
Initial installation performs Talos's installation and reboot sequence.
On installed nodes, `auto` may reboot when a configuration change requires it;
Terraform does not coordinate rolling reboots. For a change that requires reboot,
stage/apply it to one node at a time using
Talos tooling during a maintenance window, check health after each node, then
reconcile the reviewed Terraform configuration.

The pinned Talos provider 0.12.0 has no read-side reconciliation for
`talos_machine_configuration_apply`: it sends configuration when Terraform inputs
change, but does not detect every out-of-band change. A replaced VM triggers
configuration application again. Bootstrap is a one-time cluster operation;
recreating the bootstrap VM does not automatically bootstrap a new etcd cluster.
Recover loss of the control plane through the Talos disaster-recovery procedure.

After applying, retrieve credentials deliberately:

```sh
umask 077
terraform -chdir=terraform/environments/dev/talos output -raw talosconfig > /secure/path/talosconfig
terraform -chdir=terraform/environments/dev/talos output -raw kubeconfig > /secure/path/kubeconfig
```

The module does not write files or upload these credentials as workflow artifacts.
Both outputs are sensitive, but the underlying cluster secrets remain in
Terraform state. Keep the existing remote-state protections and encrypted-plan
workflow. Client files are ignored by Git; store them securely outside the repo.
Replacing the machine-secrets resource would change the cluster's identity, so
its version input is ignored after creation.

## Upgrades and node removal

Changing `talos_version` updates boot media and generated installation settings;
it **does not upgrade the OS already running on existing nodes**. Never recreate
VM disks to perform an OS upgrade. Follow the supported sequential Talos release
path, back up etcd, and prepare an Image Factory installer with the required
extensions. Use a `talosctl` version appropriate for the running cluster.

Run the helper once for each node, one node at a time. It checks full cluster
health, upgrades exactly one node with `--wait`, and checks health again. It stops
if either the precheck, upgrade, or postcheck fails. Coordinate operators so two
invocations cannot overlap; Terraform's deployment concurrency does not lock
independent CLI upgrades. A single control plane has API downtime while rebooting.

```sh
export TALOSCONFIG=/secure/path/talosconfig
bash terraform/modules/talos-cluster/scripts/upgrade-node.sh \
  NODE_IP FACTORY_INSTALLER_IMAGE CONTROL_PLANE_IPS WORKER_IPS
```

The last two arguments are comma-separated address lists; pass `''` for no
workers. Include all cluster nodes. Upgrade each control plane and check health
before proceeding, then upgrade workers individually. Update the pinned
`talos_version` through a reviewed Terraform change after the rolling operation
so future machines use the same version. ISO attachments may update, but the
disk-first boot order preserves installed systems.

For Kubernetes upgrades, run `talosctl upgrade-k8s --to TARGET_VERSION` through a
control-plane node, verify health, and only then update `kubernetes_version` in
Terraform to align configurations for new nodes. Changing machine-config image
tags alone is not a substitute for the coordinated upgrade procedure.

Scale down deliberately: drain workers or gracefully remove an etcd member
before removing its node entry. Terraform removal deletes its VM and disks;
the module does not automatically drain or reset nodes. Full cluster destruction
remains an explicit approved workflow operation.

References: [Talos Proxmox installation](https://docs.siderolabs.com/talos/v1.11/platform-specific-installations/virtualized-platforms/proxmox),
[Talos upgrades](https://docs.siderolabs.com/talos/v1.11/configure-your-talos-cluster/lifecycle-management/upgrading-talos),
[Talos provider configuration apply](https://raw.githubusercontent.com/siderolabs/terraform-provider-talos/v0.12.0/docs/resources/machine_configuration_apply.md).

## Offline tests

The CI workflow validates the module on pushes and pull requests, independently
of deployment exclusion markers. Manual runs validate it when Talos is selected.
Contract tests mock both providers and reject invalid bootstrap selections,
unpinned releases, mismatched addresses, and static networking without DNS.
A separate test exercises the real local Talos configuration generator while
overriding every network-facing operation. The upgrade helper tests use a fake
`talosctl` executable.

```sh
terraform -chdir=terraform/modules/talos-cluster init -backend=false
terraform -chdir=terraform/modules/talos-cluster test
python3 terraform/modules/talos-cluster/scripts/test_upgrade_node.py
```

Mocked tests cannot demonstrate a successful Proxmox boot or a live Talos cluster;
perform the first deployment as a reviewed integration run.
