# pve_volume_backup

Back up opted-in Kubernetes volumes and etcd from a Proxmox VE host to Proxmox
Backup Server (PBS). The volumes are disks created by the
[Proxmox CSI plugin](../../../kubernetes/README.md#persistent-storage) on a ZFS
dataset, so the host can snapshot them without touching the cluster.

A systemd timer runs `k8s-volume-backup` nightly. It:

1. Lists PersistentVolumes and claims through a read-only service account and
   selects volumes on `pve_volume_backup_storage` whose claim carries
   `pve_volume_backup_label` (`backup=true`).
2. Snapshots every selected volume with one `zfs snapshot` command, so volumes
   of the same app are captured at the same instant.
3. Uploads each snapshot to the PBS namespace as a `host` backup named
   `<namespace>.<claim>`, with archives `volume.img` and `claim.conf` (the
   PersistentVolume and claim, for restores), then destroys the snapshots.
4. Takes an etcd snapshot with a Talos credential limited to the
   `os:etcd:backup` role and uploads it as `talos-etcd`.

Snapshots are crash-consistent, like a power cut: databases such as Postgres
and SQLite recover from them. Each run reads every selected volume in full;
PBS stores only changed chunks. Retention is a PBS prune job, because the
token can only add backups.

| Variable | Default | Purpose |
| --- | --- | --- |
| `pve_volume_backup_zfs_dataset` | `""` | ZFS dataset behind the CSI storage, such as `nas/k8s-dev`. |
| `pve_volume_backup_storage` | `""` | Proxmox storage ID of that dataset, such as `k8s-dev`. |
| `pve_volume_backup_label` | `backup=true` | Claim label that opts a volume in. |
| `pve_volume_backup_schedule` | `*-*-* 20:30:00` | systemd calendar event. |
| `pve_volume_backup_pbs_host` | `""` | Inventory host of PBS, used to regenerate the token secret. |
| `pve_volume_backup_pbs_server` | `""` | PBS host name for the repository. |
| `pve_volume_backup_pbs_datastore` | `""` | Datastore name. |
| `pve_volume_backup_pbs_namespace` | `""` | Namespace, one per cluster. |
| `pve_volume_backup_pbs_token` | `""` | Token ID, such as `k8s-backup@pbs!pve`, created by the [`pbs` role](../pbs/README.md). |
| `pve_volume_backup_pbs_fingerprint` | `""` | PBS certificate fingerprint; leave empty for a publicly trusted certificate. |
| `pve_volume_backup_kube_server` | `""` | Kubernetes API URL. |
| `pve_volume_backup_kube_reader_namespace`, `pve_volume_backup_kube_reader` | `volume-backup`, `reader` | Service account from `kubernetes/infrastructure/volume-backup`. |
| `pve_volume_backup_talos_node` | `""` | Control-plane node for etcd snapshots; empty skips etcd. |
| `pve_volume_backup_talosctl_version`, `pve_volume_backup_talosctl_sha256` | Pinned release | `talosctl` downloaded and verified on the host. |
| `pve_volume_backup_credential_ttl_hours` | `8760` | Lifetime of issued Kubernetes and Talos credentials. |
| `pve_volume_backup_renew_after_days` | `300` | Runs after this many days issue new credentials. |
| `pve_volume_backup_rotate` | `false` | Issue new credentials now. |

## Credentials

The role issues three credentials and writes them to `/etc/k8s-volume-backup`
(mode `0700`), never to the repository or task output:

| File | Issued by | Can do |
| --- | --- | --- |
| `pbs-token` | PBS, by regenerating the token secret on `pve_volume_backup_pbs_host` | Add backups to its namespace |
| `kube-token` | `kubectl create token` with the administrator's kubeconfig | List PersistentVolumes and claims |
| `talosconfig` | `talosctl config new --roles os:etcd:backup` with the administrator's talosconfig | Take etcd snapshots |

Missing credentials are issued on the next run, and credentials older than
`pve_volume_backup_renew_after_days` are renewed, so run the playbook at least
once within each credential lifetime. `KUBECONFIG` and `TALOSCONFIG` must point
at the target cluster's administrator credentials when a credential is issued.

Requires `community.general`, root SSH access to the Proxmox host and the PBS
host, and `proxmox-backup-client`, which Proxmox VE includes. Check the timer
with `systemctl list-timers k8s-volume-backup.timer` and a run with
`journalctl -u k8s-volume-backup`; `k8s-volume-backup --list` prints the
selected volumes without backing anything up.
