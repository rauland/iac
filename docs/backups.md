# Backups and recovery

The repository rebuilds nodes, apps and their configuration from Git, so they
need no backup; their data does. Decide per kind of data:

| Data | Example | Backup |
| --- | --- | --- |
| Files that cannot be replaced | Photo library, documents | Yes, off-site |
| App configuration | Settings, small SQLite databases | Yes; it is small |
| Databases | PostgreSQL behind an app | The app's or operator's own dump, backed up like a file; not the live data files |
| Regenerable caches | Thumbnails, transcoded video, fetched artwork | No; keep them on a volume of their own |
| Re-downloadable media | Films, music | No |
| Cluster objects | Deployments, claims, Secrets | No; Git and Flux recreate them |

## Kubernetes volumes

[VolSync](https://volsync.readthedocs.io) copies selected PersistentVolumes to
restic repositories in the bucket from
[`platform/backup-storage`](../terraform/platform/backup-storage/README.md),
one repository per volume. restic encrypts the data before upload and only
sends what changed since the last run. Nothing runs on the Proxmox host, and
the cluster holds no hypervisor credentials and no AWS keys.

Mover pods reach S3 through the cluster's OIDC identity: a
MutatingAdmissionPolicy in [`infrastructure/volsync`](../kubernetes/infrastructure/volsync/aws-identity.yaml)
gives each one a short-lived token for `sts.amazonaws.com` and the cluster's
backup role, and restic exchanges the token for temporary credentials. The
cluster's Flux Kustomization sets the role (`backup_role_arn`) and region. One
admin setup per cluster makes AWS trust it:

1. Set `service_account_issuer` in the cluster's Talos root and apply it; see
   [public service account issuer](../terraform/modules/talos-cluster/README.md#public-service-account-issuer).
2. Apply [`platform/cluster-oidc`](../terraform/platform/cluster-oidc/README.md),
   which publishes the issuer and registers it with AWS.
3. Apply [`platform/backup-storage`](../terraform/platform/backup-storage/README.md)
   and create the cluster's repository password.

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

Each volume needs a SOPS-encrypted Secret that names its repository and holds
the cluster's restic password. As an administrator, write it from SSM without
the password touching disk unencrypted:

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
