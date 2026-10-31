# Backups and recovery

Proxmox Backup Server (PBS, VM 100) keeps the guest backups, so it cannot
restore itself. This guide lists what is backed up where and how to recover
from each disk failure. The backup jobs are configured on the Proxmox host, not
by this repository.

## What is backed up

| Data | Where it lives | Backup | Retention |
| --- | --- | --- | --- |
| Guests except PBS | Boot disks on `local-data` and `local-lvm` | Nightly at 21:00 to PBS (`backup_server`, datastore on the `nas` pool) | 7 daily, 4 weekly, 6 monthly |
| PBS boot disk (`scsi0`, 32 GB) | `local-data` | Sundays at 03:00 to `local` on the Proxmox OS disk, zstd, about 3.5 GB each | Last 2 |
| PBS datastore disk (`scsi1`) | `zfs` (`nas` pool) | None: it holds the backups themselves (`backup=0`) | — |
| Media library | VM 116's disk on the `nas` pool | None: it can be downloaded again | — |
| Kubernetes volumes | `k8s-dev` (`nas/k8s-dev`) | Not yet | — |

The PBS boot disk holds the PBS configuration: datastore definitions, users,
jobs and the encryption key, if any. Its backup sits on a different disk from
both the PBS VM and its datastore, so losing any single disk leaves a copy.

An off-site copy of the PBS datastore in S3 is planned; see
[`platform/offsite-backup`](../terraform/platform/offsite-backup/README.md).
Until the sync job exists, losing the `nas` pool loses every guest backup.

## Checking the backups

On the Proxmox host:

```sh
pvesh get /cluster/backup                  # both jobs, schedules and next runs
pvesm list local --content backup          # PBS boot-disk archives
pvesm list backup_server --content backup  # guest backups in PBS
```

Each job reports through the Proxmox notification system (`mail-to-root`).

## Recovery

### `local-data` SSD fails

This loses the boot disks of PBS (100), the admin container (101), the Docker
host (102) and the NFS VM (116). The `nas` pool, with the PBS datastore and the
media disk, survives.

1. Replace the SSD and recreate the `local-data` thin pool with the same name.
2. Restore PBS from its newest local archive:
   ```sh
   pvesm list local --content backup
   qmrestore local:backup/vzdump-qemu-100-<date>.vma.zst 100 --storage local-data
   ```
3. Check that the datastore disk is attached. If `qm config 100` shows no
   `scsi1`, attach the existing volume. Never let Proxmox delete it as an
   unreferenced disk:
   ```sh
   qm rescan --vmid 100      # lists zfs:vm-100-disk-2 as an unused disk
   qm set 100 --scsi1 zfs:vm-100-disk-2,backup=0
   ```
4. Start PBS and confirm the datastore and its backups are listed.
5. Restore 101, 102 and 116 from `backup_server`, then reattach VM 116's media
   disk (`zfs:vm-116-disk-1`) the same way.

Anything written since the last weekly archive is missing from PBS's
configuration, such as jobs or users changed in the meantime. Guest backups
themselves are unaffected, because they live on the datastore.

### Proxmox OS disk fails

This loses the PBS boot-disk archives and the dev guests on `local-lvm`
(104 and 106–108). PBS keeps running.

1. Reinstall Proxmox VE, then re-add the existing storages (`local-data`, `zfs`,
   `k8s-dev`, `dev-images` and `backup_server`) without formatting them.
2. Rebuild the dev guests with Terraform; they hold no unique data.
3. Run the weekly PBS job once by hand so a local archive exists again:
   `vzdump 100 --storage local --mode snapshot --compress zstd`.

### `nas` pool fails

This loses the PBS datastore, the media library and the Kubernetes volumes.
The guests keep running from their SSDs.

1. Rebuild the pool and recreate the PBS datastore disk.
2. Let the nightly job take fresh backups of every guest.

The Kubernetes volumes and media are lost until the off-site sync and volume
backups are in place.
