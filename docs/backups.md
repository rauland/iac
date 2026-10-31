# Backups and recovery

This guide covers two kinds of backup on a single Proxmox VE host:

- Whole-guest backups with Proxmox Backup Server (PBS) running as a VM, for
  guests that this repository cannot rebuild. The jobs are configured on the
  Proxmox host, not by this repository; adapt the IDs, storage names and
  schedules to your installation.
- Kubernetes volume backups with [VolSync](#kubernetes-volumes), managed by
  Flux, to an encrypted off-site repository.

Guests, nodes and apps that the repository rebuilds need no backup; their data
does. Decide per kind of data:

| Data | Example | Backup |
| --- | --- | --- |
| Files that cannot be replaced | Photo library, documents | Yes, off-site |
| App configuration | Settings, small SQLite databases | Yes; it is small |
| Databases | PostgreSQL behind an app | The app's or operator's own dump, backed up like a file; not the live data files |
| Regenerable caches | Thumbnails, transcoded video, fetched artwork | No; keep them on a volume of their own |
| Re-downloadable media | Films, music | No |
| Cluster objects | Deployments, claims, Secrets | No; Git and Flux recreate them |

## Layout

A PBS VM keeps the guest backups, so it cannot restore itself. Give it two
disks and back them up differently:

| Disk | Holds | Backup |
| --- | --- | --- |
| Boot disk | PBS itself and its configuration: datastore definitions, users, jobs and any encryption key | A regular `vzdump` job to storage on a different physical disk from both PBS disks |
| Datastore disk | The guest backups | None (`backup=0`) |

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
excluded with `backup=0` on its disk. PBS keeps everything on the one host, so
move data that cannot be replaced to Kubernetes volumes with an off-site
backup, or copy it off-site separately.

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

Add a verify job so damaged chunks are found before a restore needs them:

```sh
proxmox-backup-manager verify-job create <store>-weekly --store <store> \
  --schedule 'sat 04:00' --ignore-verified true --outdated-after 30
```

## Kubernetes volumes

[VolSync](https://volsync.readthedocs.io) copies selected PersistentVolumes to
restic repositories in the bucket from
[`platform/offsite-backup`](../terraform/platform/offsite-backup/README.md),
one repository per volume. restic encrypts the data before upload and only
sends what changed since the last run. Nothing runs on the Proxmox host, and
the cluster holds no hypervisor credentials.

The Proxmox CSI plugin's volume snapshots need a `root@pam` login, so backups
use `copyMethod: Direct`: VolSync starts a mover pod on the app's node, mounts
the live volume and reads it while the app runs. Each file is read as it is at
that moment, and an app's volumes are copied one after another, not at the
same instant. That suits files and settings. For a database, back up the dump
it writes, not its live data files.

### Lay out an app's volumes

A backup covers a whole volume, so give each kind of data its own claim and
back up only the ones worth keeping:

| Claim | Holds | Back up |
| --- | --- | --- |
| `<app>-data` | Files that cannot be replaced, database dumps | Yes |
| `<app>-config` | Settings | Yes |
| `<app>-cache` | Thumbnails, transcodes, downloads | No |

Mount a cache inside a data directory, for example at `/data/thumbs`, when the
app expects it there.

### Back up a volume

Create the cluster's credentials first; see
[`platform/offsite-backup`](../terraform/platform/offsite-backup/README.md#create-a-clusters-credentials).
Each volume then needs a SOPS-encrypted Secret that names its repository. As an
administrator, write it from SSM without the values touching disk unencrypted:

```sh
cluster=dev namespace=<namespace> claim=<claim> bucket=<bucket> region=<region>
file=kubernetes/clusters/$cluster/<app>/$claim-backup.sops.yaml
get() {
  AWS_PROFILE=admin aws ssm get-parameter --with-decryption \
    --name "/iac/admin/backup-$cluster/$1" --query Parameter.Value --output text
}
cat <<YAML | sops --encrypt --filename-override "$file" \
  --input-type yaml --output-type yaml /dev/stdin > "$file"
apiVersion: v1
kind: Secret
metadata:
  name: $claim-backup
stringData:
  RESTIC_REPOSITORY: s3:https://s3.$region.amazonaws.com/$bucket/$cluster/$namespace/$claim
  RESTIC_PASSWORD: $(get RESTIC_PASSWORD)
  AWS_ACCESS_KEY_ID: $(get ACCESS_KEY_ID)
  AWS_SECRET_ACCESS_KEY: $(get SECRET_ACCESS_KEY)
YAML
```

Add the Secret and a ReplicationSource to the app's `resources`:

```yaml
apiVersion: volsync.backube/v1alpha1
kind: ReplicationSource
metadata:
  name: <claim>
spec:
  sourcePVC: <claim>
  trigger:
    schedule: "30 2 * * *"
  restic:
    repository: <claim>-backup
    copyMethod: Direct
    retain:
      daily: 7
      weekly: 4
      monthly: 6
    pruneIntervalDays: 7
    cacheStorageClassName: proxmox-scratch
    cacheCapacity: 1Gi
    moverSecurityContext:
      runAsUser: <app uid>
      runAsGroup: <app gid>
      fsGroup: <app gid>
      runAsNonRoot: true
      seccompProfile:
        type: RuntimeDefault
```

- `moverSecurityContext` runs the mover as the app's user, so it can read the
  app's files and passes the `restricted` Pod Security standard. Set it before
  the first run: the restic cache is owned by the first run's user.
- `proxmox-scratch` deletes the cache's disk with its claim; the default
  `proxmox` class would keep it.
- Spread the schedules of large volumes so their uploads do not overlap.

### Check the backups

```sh
kubectl get replicationsource -A
kubectl -n <namespace> get replicationsource <claim> \
  -o jsonpath='{.status.lastSyncTime} {.status.latestMoverStatus.result}{"\n"}{.status.latestMoverStatus.logs}{"\n"}'
```

To run one now, set a manual trigger, then remove it to return to the
schedule: `kubectl -n <namespace> patch replicationsource <claim> --type=merge
-p '{"spec":{"trigger":{"manual":"now-1"}}}'`.

### Restore a volume

1. Stop the app so nothing writes to the volume: suspend the Flux
   Kustomization that applies it, then scale it to zero.
2. Restore into the claim, choosing the backup with `restoreAsOf` (the latest
   at or before a time) or `previous` (how many backups back):
   ```yaml
   apiVersion: volsync.backube/v1alpha1
   kind: ReplicationDestination
   metadata:
     name: <claim>-restore
     namespace: <namespace>
   spec:
     trigger:
       manual: restore-1
     restic:
       repository: <claim>-backup
       destinationPVC: <claim>
       copyMethod: Direct
       enableFileDeletion: true
       restoreAsOf: "2026-01-31T00:00:00Z"
       cacheStorageClassName: proxmox-scratch
       moverSecurityContext: <as in the ReplicationSource>
   ```
   `enableFileDeletion` removes files that are not in the backup, so the
   volume matches it exactly. Wait until `.status.lastManualSync` is
   `restore-1`, check `.status.latestMoverStatus`, then delete the
   ReplicationDestination.
3. Scale the app back up and resume its Kustomization.

On a rebuilt cluster, Flux creates the claims empty and the apps start with no
data. Restore each backed-up claim the same way, before the app writes
settings of its own. If only the cluster was rebuilt and its storage survived,
the old disks still exist, because the StorageClass retains them; see
[persistent storage](../kubernetes/README.md#persistent-storage).

### Cost

Storage costs the repository size times the provider's monthly price per GB,
plus a few cents of requests. The first backup uploads everything; later ones
upload only changes. restic's deduplication and compression shrink settings
and databases a lot, but barely shrink photos and video, which are already
compressed. Restoring downloads the data, which most providers charge for.
The bucket keeps deleted objects for 30 days, so pruned backups cost that
long.

## Checking the PBS backups

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

1. Rebuild the storage, then recreate the datastore disk and the PBS
   datastore.
2. Run the guest job by hand so fresh backups exist.

Guest data that lived only on that storage is lost. Kubernetes volumes on it
are restored from their off-site repositories; see
[restore a volume](#restore-a-volume).
