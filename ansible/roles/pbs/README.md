# pbs

Configure Proxmox Backup Server (PBS) 4 from variables: S3 endpoints,
datastores, namespaces, users, tokens, permissions, and sync, prune and verify
jobs. Each entry is created if missing,
and options that differ are updated; nothing is removed. Changes run through
`proxmox-backup-manager` on the PBS host, so the play connects as `root`.

The bundled `pbs_config` module lists a section as JSON, compares the
configured options, and runs `create` or `update` with only the differences.
It supports check mode.

| Variable | Default | Purpose |
| --- | --- | --- |
| `pbs_s3_endpoints` | `[]` | `id` and `options`, such as `endpoint` and `region`. |
| `pbs_datastores` | `[]` | `name`, `path`, `options`, and `create_only` for settings fixed at creation, such as `backend`. |
| `pbs_sync_jobs` | `[]` | `id` and `options`, such as `store`, `remote-store`, `schedule` and `group-filter`. |
| `pbs_prune_jobs` | `[]` | `id` and `options`, such as `store`, `schedule` and `keep-*`. |
| `pbs_verify_jobs` | `[]` | `id` and `options`, such as `store`, `schedule` and `outdated-after`. |
| `pbs_namespaces` | `[]` | `store` and `ns`, such as `k8s-dev`; nested namespaces use `parent/child`. |
| `pbs_users` | `[]` | `userid` and `options`. Users without a password can only use tokens. |
| `pbs_tokens` | `[]` | `userid` and `name`. The secret shown on creation is discarded; the consumer regenerates it. |
| `pbs_acls` | `[]` | `path`, `role` and `auth_id`. Existing entries are kept. |
| `pbs_s3_access_key_id` | `PBS_S3_ACCESS_KEY_ID` environment variable | S3 access key, needed to create an endpoint or rotate its key. |
| `pbs_s3_secret_access_key` | `PBS_S3_SECRET_ACCESS_KEY` environment variable | S3 secret key, as above. |
| `pbs_s3_rotate_key` | `false` | Send the current key to existing endpoints. |
| `pbs_datastore_reuse` | `false` | Attach existing contents when creating a datastore, for example on a rebuilt PBS. |

Option names and values are those of `proxmox-backup-manager … create`. Lists
repeat the option, and maps become property strings such as
`type=s3,client=aws,bucket=my-bucket`. Set only values that differ from the PBS
defaults; an option PBS does not list is sent again on every run.

The S3 secret key is passed as a command argument on the PBS host while the
endpoint is created, and Ansible hides it from task output. Endpoints keep
their key until `pbs_s3_rotate_key` is set, because PBS does not show the
secret to compare against.

An S3 datastore needs a local cache directory, ideally on its own disk of
64–128 GiB. Create and mount that disk before the first run.

A privilege-separated token gets the intersection of its own permissions and
its user's, so grant both. A token secret is shown only once. The role does not
keep it: the host that uses a token regenerates the secret with
`proxmox-backup-debug api set /access/users/<user>/token/<name> --regenerate true`,
which keeps the token's permissions, as
[`pve_volume_backup`](../pve_volume_backup/README.md) does.
