# Backups and recovery

This guide describes a backup layout for a single Proxmox VE host with Proxmox
Backup Server (PBS) running as a VM, and how to recover from losing each disk.
The backup jobs are configured on the Proxmox host, not by this repository;
adapt the IDs, storage names and schedules to your installation.

## Layout

A PBS VM keeps the guest backups, so it cannot restore itself. Give it two
disks and back them up differently:

| Disk | Holds | Backup |
| --- | --- | --- |
| Boot disk | PBS itself and its configuration: datastore definitions, users, jobs and any encryption key | A regular `vzdump` job to storage on a different physical disk from both PBS disks |
| Datastore disk | The guest backups | None (`backup=0`); an off-site copy comes from a PBS sync job |

Every other guest is backed up to PBS by a nightly job that excludes the PBS VM.
With the boot-disk archive on a third disk, losing any one disk leaves a copy of
everything needed to bring PBS back.

Example layout on one host:

| Storage | Physical disk | Contents |
| --- | --- | --- |
| `local` | Proxmox OS SSD | PBS boot-disk archives |
| `local-data` | Separate SSD | Guest boot disks, including PBS's |
| `zfs` | HDD pool | PBS datastore disk, bulk data |
| `backup_server` | PBS datastore on the HDD pool | Nightly guest backups |

Data that can be recreated, such as a downloaded media library, can be
excluded with `backup=0` on its disk. Off-site storage for the datastore is
defined in [`platform/offsite-backup`](../terraform/platform/offsite-backup/README.md).

## Configuring the jobs

Mark the PBS datastore disk as excluded and the boot disk as included, then
create a job for the PBS VM. Re-specify the whole disk when you change its
options, keeping its size:

```sh
qm set <pbs-vmid> --scsi0 <boot-storage>:<boot-volume>,size=<size>
qm set <pbs-vmid> --scsi1 <datastore-storage>:<datastore-volume>,backup=0,size=<size>
pvesh create /cluster/backup --vmid <pbs-vmid> --storage local \
  --schedule 'sun 03:00' --mode snapshot --compress zstd \
  --prune-backups keep-last=2 --notification-mode notification-system
```

Exclude the PBS VM from the guest job (`--all 1 --exclude <pbs-vmid>`), and keep
the two schedules apart so PBS is not backed up while it receives backups.

Check that the boot-disk storage has room for the archives: a 32 GB PBS boot
disk compresses to about 3.5 GB. Run the job once by hand to confirm that the
datastore disk is excluded:

```sh
vzdump <pbs-vmid> --storage local --mode snapshot --compress zstd
```

## Permissions and retention

Give the Proxmox storage entry a PBS API token with only the `DatastoreBackup`
role on its datastore, and let a PBS prune job apply retention. Proxmox can
then add backups and restore its own, but cannot delete any, so someone who
takes over the hypervisor or its token cannot destroy the backups. `Admin`
would also allow deleting every snapshot and changing the datastore.

Set retention in one place. With a PBS prune job, remove `prune-backups` from
the Proxmox guest job so the storage default (`keep-all=1`) applies, and make
the prune job exist before narrowing the token; otherwise backups accumulate
until the datastore is full. A dry run shows what a policy would remove:

```sh
proxmox-backup-debug api create /admin/datastore/<store>/prune \
  --backup-type vm --backup-id <vmid> --keep-daily 7 --keep-weekly 4 \
  --keep-monthly 6 --dry-run true
```

## Off-site copy

The [`pbs` Ansible role](../ansible/roles/pbs/README.md) configures the PBS
side: an S3 endpoint, an S3-backed datastore with a local cache, a sync job
that copies selected backup groups from the local datastore, and a prune job
that sets the off-site retention. The bucket and its key come from
[`platform/offsite-backup`](../terraform/platform/offsite-backup/README.md).

Copy only what cannot be rebuilt. Guests that this repository recreates need
no off-site copy; their data does. Use `group-filter` on the sync job, such as
`group:vm/<vmid>`, to choose them. The sync does not remove off-site backups
when the local ones are pruned, so a deletion on PBS does not reach the
off-site copy before its own prune job runs.

Before the first sync, give PBS a cache disk for the S3 datastore, 64–128 GiB on
fast storage, excluded from backups:

```sh
qm set <pbs-vmid> --scsi2 <ssd-storage>:64,backup=0
```

Inside PBS, format it and mount it at the cache's parent directory, such as
`/mnt/pbs-cache`, through `/etc/fstab`. The datastore path is a directory
below the mount point, because a filesystem's root is never empty.

The first sync uploads every selected snapshot, so run it when the local
storage is healthy, not while a pool is degraded or rebuilding.

## Kubernetes volumes and etcd

Kubernetes nodes, images and manifests are rebuilt from Git, so only
PersistentVolumes and the cluster's etcd database need backups. The
[`pve_volume_backup` role](../ansible/roles/pve_volume_backup/README.md) backs
them up from the Proxmox host into one PBS namespace per cluster. Opt a volume
in with a label on its claim; leave caches and other data the app can
regenerate unlabelled:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: library
  labels:
    backup: "true"
```

Each volume becomes a `host` backup group named `<namespace>.<claim>`, holding
`volume.img` and `claim.conf` with the original PersistentVolume and claim.
etcd is the group `talos-etcd`. The commands below run on the Proxmox host as
root, with the job's repository and token:

```sh
export PBS_REPOSITORY=<token-id>@<pbs-host>:<datastore>
export PBS_PASSWORD=$(cat /etc/k8s-volume-backup/pbs-token)
proxmox-backup-client snapshot list --ns <namespace>
```

### Restore a volume

1. Stop the app, for example by scaling its Deployment to zero, so the CSI
   plugin detaches the disk. Suspend its Flux Kustomization first, or Flux
   scales it back up.
2. Find the target disk. To roll back an existing claim, read its
   PersistentVolume's `volumeHandle` (`<region>/<node>/<storage>/<volume>`). For
   a new claim, create it, start the app once so the disk is provisioned, then
   stop it again.
3. Write the image into the disk. The disk must be at least as large as the
   backup and attached to no VM:
   ```sh
   proxmox-backup-client restore --ns <namespace> host/<namespace>.<claim>/<time> \
     volume.img - | dd of=/dev/zvol/<dataset>/<volume> bs=4M conv=sparse status=progress
   ```
4. Resume the Kustomization and start the app.

`claim.conf` records the original binding, which helps when the cluster has
been rebuilt and claim UIDs and volume names have changed:
`proxmox-backup-client restore --ns <namespace> host/<group>/<time> claim.conf -`.

### Restore etcd onto a rebuilt control plane

Restoring etcd brings back every Kubernetes object, including the
PersistentVolumes, so the CSI plugin reattaches the existing disks itself.

```sh
proxmox-backup-client restore --ns <namespace> host/talos-etcd/<time> etcd.img etcd.db
talosctl --nodes <control-plane> bootstrap --recover-from=./etcd.db
```

Bootstrap from the snapshot instead of an empty etcd: a node bootstraps only
once, so recover before anything else bootstraps it.

## Checking the backups

```sh
pvesh get /cluster/backup                      # jobs, schedules and next runs
pvesm list local --content backup              # PBS boot-disk archives
pvesm list <pbs-storage> --content backup      # guest backups in PBS
```

## Recovery

### The PBS boot disk is lost

The datastore disk survives on its own storage.

1. Restore PBS from its newest local archive:
   ```sh
   pvesm list local --content backup
   qmrestore local:backup/<archive> <pbs-vmid> --storage <boot-storage>
   ```
2. Check that the datastore disk is attached. If `qm config <pbs-vmid>` does
   not list it, attach the existing volume:
   ```sh
   qm rescan --vmid <pbs-vmid>   # adds the volume as an unused disk
   qm set <pbs-vmid> --scsi1 <datastore-storage>:<datastore-volume>,backup=0
   ```
3. Start PBS and confirm that the datastore lists its backups.
4. Restore the other guests that shared the failed disk from PBS, and reattach
   any excluded data disks the same way.

Configuration changed in PBS since the last archive, such as new jobs or users,
is missing. The guest backups are unaffected because they live on the
datastore.

Proxmox treats volumes named `vm-<vmid>-*` as belonging to that VM. Do not use
"Destroy unreferenced disks" or `qm destroy --purge` on the PBS VM while its
datastore disk is detached: either deletes the backups.

### The Proxmox OS disk is lost

This loses the boot-disk archives and any guests on the OS disk. PBS keeps
running.

1. Reinstall Proxmox VE, then re-add the existing storages and PBS without
   formatting them.
2. Restore or rebuild the guests that lived on the OS disk. Guests managed by
   Terraform can be redeployed.
3. Run the PBS job once by hand so a local archive exists again.

### The datastore storage is lost

This loses the backups. Guests keep running from their own disks.

1. Rebuild the storage, recreate the datastore disk and the PBS datastore, or
   restore it from the off-site copy.
2. Run the guest job by hand so fresh backups exist.

Without an off-site copy, data that lived only on that storage is lost.
