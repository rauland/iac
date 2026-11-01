# Off-site backup storage

This administrator-operated root creates the S3 bucket that holds the clusters'
off-site backups, and one IAM role per cluster to write them. It is excluded
from automatic deployment discovery; CI cannot plan or apply it.

Each cluster's [VolSync](../../../docs/backups.md#kubernetes-volumes) backups
are restic repositories under its own prefix, `<cluster>/<namespace>/<claim>`.
restic encrypts the data before it leaves the cluster, so the bucket holds
nothing readable without the repository password.

## What it creates

| Resource | Notes |
| --- | --- |
| S3 bucket (`bucket_name`) | Private, encrypted at rest, TLS only. Versioned: deleted or overwritten objects stay recoverable for `deleted_retention_days` (30). Incomplete uploads are removed after seven days. Protected from `terraform destroy`. |
| IAM role `backup-<cluster>` per entry in `clusters` | Can list, read, write and delete objects under `<cluster>/`; nothing else in the account. Assumable only by the cluster's VolSync movers, through its identity provider from [`platform/cluster-oidc`](../cluster-oidc/README.md). |
| Monthly budget (optional) | Emails when actual or forecast spend exceeds `budget_limit_usd`. Created only when `budget_email` is set. |

restic's prune deletes objects, so a cluster's role must be allowed to. If the
cluster is compromised, versioning keeps what was deleted for 30 days; restore
it by removing the delete markers. Backup retention is set on
each ReplicationSource, not here.

## No access keys

A mover pod exchanges its service account token, which expires within an hour,
for temporary credentials of its cluster's role
(`sts:AssumeRoleWithWebIdentity`). The role trusts only service accounts named
`volsync-src-*` and `volsync-dst-*`, which VolSync creates for each
ReplicationSource and ReplicationDestination, with the audience
`sts.amazonaws.com`. Anyone who can create service accounts with those names
in the cluster can reach the cluster's prefix, so treat that permission like
access to the backups.

The cluster injects the role into mover pods with a MutatingAdmissionPolicy;
see [Kubernetes volumes](../../../docs/backups.md#kubernetes-volumes).

## Apply

Authenticate with the `admin` profile as described in
[state-access](../state-access/README.md#authenticate-with-temporary-administrator-credentials),
then from the repository root:

```sh
(
  unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_SECURITY_TOKEN
  export AWS_PROFILE=admin
  aws sts get-caller-identity &&
  terraform -chdir=terraform/platform/offsite-backup init \
    -backend-config=bucket=rauland-iac-homelab \
    -backend-config=region=ap-southeast-2 \
    -backend-config=key=terraform/platform/offsite-backup.tfstate &&
  terraform -chdir=terraform/platform/offsite-backup plan -out=tfplan \
    -var state_bucket=rauland-iac-homelab -var budget_email=you@example.com
)
```

Review the plan, then apply it with
`terraform -chdir=terraform/platform/offsite-backup apply tfplan` in the same
kind of subshell. Omit `-var budget_email=…` to skip the budget. Bucket names
are global, so a fork must set its own `bucket_name`. Apply
[`platform/cluster-oidc`](../cluster-oidc/README.md) first: each role trusts
the identity provider it creates.

## Create a cluster's repository password

restic encrypts each repository with a password; without it the backups cannot
be decrypted. Create it straight into SSM, so it is never displayed or saved in
a file. No CI role can read parameters under `/iac/admin`:

```sh
AWS_PROFILE=admin aws ssm put-parameter --name /iac/admin/backup-<cluster>/RESTIC_PASSWORD \
  --type SecureString --value "$(openssl rand -base64 32)" >/dev/null
```

The command has no `--overwrite`, because a new password cannot open existing
repositories. Keep a second copy offline, such as in a password manager. The
cluster gets it in a SOPS-encrypted Secret per volume; see
[back up a volume](../../../docs/backups.md#back-up-a-volume).

## Checks

Run `terraform validate` and the offline tests with `terraform test` from this
directory. The tests assert that the bucket blocks public access and is
versioned, that each cluster's role is limited to its own prefix and to its
own VolSync movers, and that the budget is optional.
