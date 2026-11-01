# Talos on Proxmox

This module creates Proxmox VMs, boots a custom Talos **Secure Boot metal ISO from CD-ROM**,
installs onto separate SCSI disks through the Talos API, bootstraps one control
plane, encrypts `STATE` and `EPHEMERAL` with TPM-backed LUKS2, checks cluster health,
and exposes sensitive client configurations.
It does not use cloud-init, snippets, Proxmox-host SSH, or runner-local credential
resources.

CI uses the shared [VM tag staging](../../../docs/deployments.md#vm-tag-staging)
path when creating or replacing nodes: create each guest in its pool, then
apply only its reviewed tags after pool-scoped permissions take effect. The
internal `deferred_vm_tags` input defaults to an empty set.

## Deploying the example environment

`terraform/workloads/dev/talos` is enabled for local and GitHub Actions
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
   Kubernetes API on port 6443 through Tailscale. The nodes need the routes and
   DNS necessary to reach Image Factory and container registries. Set
   `dns_servers` for static nodes (for example, your LAN resolver). A load-balanced
   `cluster_endpoint` must already exist; the module does not create a load
   balancer or a virtual IP.
4. Apply the [platform access root](../../platform/access/README.md) to create
   the dev pool and `dev-images` ISO storage. The example assigns all VMs to
   `pool_id = "dev"` and uses `iso_datastore_id = "dev-images"`.
   Ensure each selected Proxmox host has `iso_datastore_id` with ISO support and
   `disk_datastore_id` for VM disks. The defaults are `local` and `local-lvm`.
5. Run the Terraform workflow on `main` with environment `dev`, scope `single`,
   and target `talos`. Review the plan before approving apply. Scope `all` for
   `dev` also includes the Flux root.

To opt out of GitHub Actions deployments, add a `.disabled` file in the root
directory. The marker excludes it from automatic and manual discovery without
changing the module configuration; local Terraform commands are unaffected.
Remove the marker when you want workflow deployments to include it again.

The node map keys must equal `node_name`. Keep keys, API addresses, and
`bootstrap_node` stable. The module derives Proxmox hosts from the node map;
there is no separate `pve_nodes` list that can disagree with it. CPU, memory,
disk capacity, storage override, bridge, VLAN, MAC, VM ID, and YAML patches can be
set per node. Defaults are 2 CPUs, 4096 MiB RAM, and a 32 GiB disk.

VMs use UEFI, q35, a 4 MiB EFI disk, a persistent TPM 2.0 device, VirtIO SCSI,
one NIC, and `/dev/sda` as the installation target. EFI and TPM state use the
node's disk datastore (or the module default). The EFI disk intentionally has
`pre_enrolled_keys = false`: fresh firmware starts in setup mode so the Secure
Boot ISO can automatically enroll Sidero Labs signing keys under virtualization.
Proxmox's pre-enrolled Microsoft/distribution keys do not replace Talos key enrollment.
The installation ISO contains `qemu-guest-agent`; waiting for its IP report is
disabled to avoid blocking configuration while the VM is in maintenance mode.
The boot order tries the installed disk before the ISO. The network patch selects
the one physical NIC rather than relying on a Linux interface name.

Every node is labelled `topology.kubernetes.io/region` with `proxmox_region`
(default `pve`) and `topology.kubernetes.io/zone` with its `pve_node`. The
Proxmox CSI plugin needs both to create and attach volumes, and its config must
use the same region. Changing them applies without a reboot.

The plugin attaches volumes to the VMs as extra disks, so the VM resource
ignores changes to its disks; otherwise an apply would detach them from
running pods. To grow a node's boot disk, resize it in Proxmox
(`qm disk resize <vmid> scsi0 <size>`) and update `disk_size` to match.
Refreshing a VM reads every attached disk, so the Terraform identities need
`Datastore.Audit` on the Kubernetes storage and `VM.Config.Disk` on the
plugin's placeholder volume owner, `/vms/9999`. [`platform/access`](../../platform/access/README.md)
grants both; neither allows deleting a volume.

## Secure Boot and system-volume encryption

Both boot media and installation/upgrade images use Image Factory's Secure Boot
variants with the same schematic and extensions. `installer_iso_url` and
`installer_image` expose those variants too; use the latter for rolling upgrades.

Every node receives `VolumeConfig` documents for `STATE` and `EPHEMERAL`. Each
uses LUKS2 with a single TPM key in slot 0, explicitly bound to PCR 7 (Secure Boot
state), in addition to the signed UKI policy. Key enrollment fails if Secure Boot
is disabled; there is no static passphrase or node-ID fallback. `EPHEMERAL` also
uses `lockToState: true`, so wiping/replacing `STATE` prevents that volume from
being unlocked. Encryption keys are generated and sealed on the node, not passed
through Terraform variables.

The default etcd, container-runtime, kubelet, and log directories live under
`EPHEMERAL` and inherit its encryption. If additional configuration patches place
them on dedicated partitions, configure encryption for those volumes separately.
CSI-managed disks and remote persistent volumes need their own encryption settings;
the Proxmox CSI StorageClasses in this repository encrypt their volumes with LUKS
(see [volume encryption](../../../kubernetes/README.md#volume-encryption)).
Custom global/per-node patches run last and can override the module defaults;
review any changes to boot or encryption settings carefully.

After initial boot, verify each node through its installed system:

```sh
talosctl --talosconfig /secure/path/talosconfig -n NODE_IP get securitystate
talosctl --talosconfig /secure/path/talosconfig -n NODE_IP get volumestatus STATE -o yaml
talosctl --talosconfig /secure/path/talosconfig -n NODE_IP get volumestatus EPHEMERAL -o yaml
```

Require `SECUREBOOT=true` and confirm that both volumes report `luks2` with TPM
encryption. If boot or enrollment fails, inspect the Proxmox console and firmware
settings; do not bypass the Secure Boot enrollment check.

Preserve the VM's EFI variables and TPM state alongside its encrypted disks in
backups and migrations. With only a TPM key, loss of the TPM state or an
incompatible boot-policy change can make the disks unrecoverable. Maintain and
test independent etcd/workload backups for recovery onto fresh nodes. A Proxmox
vTPM is controlled by the hypervisor; this does not protect against an administrator
who controls the Proxmox host, or against a compromised running node.

References: [Talos Secure Boot](https://docs.siderolabs.com/talos/v1.14/platform-specific-installations/bare-metal-platforms/secureboot),
[Talos disk encryption](https://docs.siderolabs.com/talos/v1.14/configure-your-talos-cluster/storage-and-disk-management/disk-encryption),
[VolumeConfig](https://docs.siderolabs.com/talos/v1.14/reference/configuration/block/volumeconfig).

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
terraform -chdir=terraform/workloads/dev/talos output -raw talosconfig > /secure/path/talosconfig
terraform -chdir=terraform/workloads/dev/talos output -raw kubeconfig > /secure/path/kubeconfig
```

The module does not write files or upload these credentials as workflow artifacts.
Both outputs are sensitive, but the underlying cluster secrets remain in
Terraform state. Keep the existing remote-state protections and encrypted-plan
workflow. Client files are ignored by Git; store them securely outside the repo.
Replacing the machine-secrets resource would change the cluster's identity, so
its version input is ignored after creation.

### Public service account issuer

Kubernetes signs service account tokens as an OIDC issuer. By default that is
the API endpoint, which services outside the network cannot reach to fetch the
signing keys. Set `service_account_issuer` to a public HTTPS URL that serves the
cluster's discovery documents, such as the one
[`platform/cluster-oidc`](../../platform/cluster-oidc/README.md) publishes, and
AWS can trust tokens issued to pods without any stored access key.

Control planes then sign with the public issuer and still accept tokens from
the API endpoint, so pods that hold older tokens keep working while the kubelet
refreshes them. The token audience stays the API endpoint. Changing these flags
restarts the API server without rebooting the node; with a single control
plane, the API is unavailable for a few seconds.

## Upgrades and node removal

Changing `talos_version` updates boot media and generated installation settings;
it **does not upgrade the OS already running on existing nodes**. Never recreate
VM disks to perform an OS upgrade. Follow the supported sequential Talos release
path, back up etcd, and use an Image Factory installer with the required
extensions. Use a `talosctl` version appropriate for the running cluster. An
upgrade keeps the `STATE` and `EPHEMERAL` volumes, including etcd data.

### Upgrade workflow

Run the **Talos upgrade** workflow (`.github/workflows/talos-upgrade.yml`) from
`main`. Choose the environment, the component (`talos` or `kubernetes`) and a
pinned target version. After approval in the `proxmox-ENVIRONMENT-apply`
environment, it:

1. Reads the `upgrade_inventory` output and the talosconfig from Terraform state.
   Deploy the Talos root from `main` once before the first upgrade so the output exists.
2. Installs the `talosctl` release matching the target (Talos) or the pinned
   `talos_version` (Kubernetes), verified against the release checksums.
3. Takes an etcd snapshot, encrypts it to the saved-plan public key and keeps it
   as a run artifact for seven days. Decrypt it with the saved-plan private key.
4. For `talos`, reads every node's running version and refuses the run before
   changing anything if any node would be downgraded or skip a minor release.
   Nodes already on the target are skipped, so rerunning after a failure resumes
   where it stopped. The rest are upgraded with `upgrade-node.sh`, control planes
   first, using the same Secure Boot schematic with the new tag.
5. For `kubernetes`, runs `talosctl upgrade-k8s --to VERSION` between two
   cluster health checks.

The workflow shares the `iac-terraform-ENVIRONMENT-talos` concurrency group with
deployments, so an upgrade never overlaps a Terraform apply or another upgrade.
A single control plane has API downtime while rebooting. When the run succeeds,
open a pull request pinning the new `talos_version` or `kubernetes_version` so
future machines use the same version. ISO attachments may update, but the
disk-first boot order preserves installed systems.

### Manual upgrade

Without the workflow, run the helper once for each node, one node at a time. It
checks full cluster health, upgrades exactly one node with `--wait`, and checks
health again. It stops if the precheck, upgrade, or postcheck fails. Coordinate
operators so two invocations cannot overlap: unlike the workflow, a local run
does not join the deployment concurrency group.

```sh
export TALOSCONFIG=/secure/path/talosconfig
bash terraform/modules/talos-cluster/scripts/upgrade-node.sh \
  NODE_IP FACTORY_INSTALLER_IMAGE CONTROL_PLANE_IPS WORKER_IPS
```

The last two arguments are comma-separated address lists; pass `''` for no
workers. Include all cluster nodes. Upgrade each control plane and check health
before proceeding, then upgrade workers individually.
Always use the matching Secure Boot installer image and preserve signing-key
continuity; a regular installer image can leave a node unable to boot or unlock
its system volumes.

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
overriding every network-facing operation. The upgrade helper and rolling
upgrade tests use a fake `talosctl` executable. Tests also cover Secure Boot image selection, UEFI/TPM
hardware, and the real generator's encrypted-volume configuration for both node roles.

```sh
terraform -chdir=terraform/modules/talos-cluster init -backend=false
terraform -chdir=terraform/modules/talos-cluster test
python3 terraform/modules/talos-cluster/scripts/test_upgrade_node.py
python3 terraform/modules/talos-cluster/scripts/test_rolling_upgrade.py
```

Mocked tests cannot demonstrate a successful Proxmox boot or a live Talos cluster;
perform the first deployment as a reviewed integration run.
