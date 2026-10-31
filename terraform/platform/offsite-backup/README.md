# Off-site backup storage

This administrator-operated root creates the S3 bucket that holds the clusters'
off-site backups, and one IAM user per cluster to write them. It is excluded
from automatic deployment discovery; CI cannot plan or apply it.

Each cluster's [VolSync](../../../docs/backups.md#kubernetes-volumes) backups
are restic repositories under its own prefix, `<cluster>/<namespace>/<claim>`.
restic encrypts the data before it leaves the cluster, so the bucket holds
nothing readable without the repository password.

## What it creates

| Resource | Notes |
| --- | --- |
| S3 bucket (`bucket_name`) | Private, encrypted at rest, TLS only. Versioned: deleted or overwritten objects stay recoverable for `deleted_retention_days` (30). Incomplete uploads are removed after seven days. Protected from `terraform destroy`. |
| IAM user `backup-<cluster>` per entry in `clusters` | Can list, read, write and delete objects under `<cluster>/`; nothing else in the account. |
| Monthly budget (optional) | Emails when actual or forecast spend exceeds `budget_limit_usd`. Created only when `budget_email` is set. |

restic's prune deletes objects, so a cluster's key must be allowed to. If the
cluster or its key is compromised, versioning keeps what was deleted for 30
days; restore it by removing the delete markers. Backup retention is set on
each ReplicationSource, not here.

## Why this root has access keys

The rest of the repository uses no IAM users or long-lived keys. A restic
mover in the cluster can only authenticate to S3 with a static access key, so
the backup users are the exception. Each policy covers one prefix of one
bucket, and the keys are created outside Terraform so their secrets never enter
state.

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
    -var budget_email=you@example.com
)
```

Review the plan, then apply it with
`terraform -chdir=terraform/platform/offsite-backup apply tfplan` in the same
kind of subshell. Omit `-var budget_email=…` to skip the budget. Bucket names
are global, so a fork must set its own `bucket_name`.

## Create a cluster's credentials

A cluster needs an access key and a restic repository password. Create both
straight into SSM, so neither is displayed or saved in a file. No CI role can
read parameters under `/iac/admin`. Set `cluster` to the cluster's name:

```sh
(
  export AWS_PROFILE=admin cluster=dev
  aws iam create-access-key --user-name "backup-$cluster" \
    --query 'AccessKey.[AccessKeyId,SecretAccessKey]' --output text |
    {
      read -r id secret
      aws ssm put-parameter --name "/iac/admin/backup-$cluster/ACCESS_KEY_ID" \
        --type SecureString --overwrite --value "$id" >/dev/null &&
      aws ssm put-parameter --name "/iac/admin/backup-$cluster/SECRET_ACCESS_KEY" \
        --type SecureString --overwrite --value "$secret" >/dev/null
    } &&
  aws ssm put-parameter --name "/iac/admin/backup-$cluster/RESTIC_PASSWORD" \
    --type SecureString --value "$(openssl rand -base64 32)" >/dev/null
)
```

The password command has no `--overwrite`, because a new password cannot open
existing repositories. Without the password the backups cannot be decrypted,
so keep a second copy offline, such as in a password manager. The cluster gets
the values as SOPS-encrypted Secrets; see
[back up a volume](../../../docs/backups.md#back-up-a-volume).

To rotate the access key, create a second key the same way (a user may have
two), re-encrypt the cluster's Secrets, confirm a backup succeeds, then delete
the old key:

```sh
AWS_PROFILE=admin aws iam list-access-keys --user-name backup-<cluster>
AWS_PROFILE=admin aws iam delete-access-key --user-name backup-<cluster> --access-key-id <old key id>
```

## Checks

Run `terraform validate` and the offline tests with `terraform test` from this
directory. The tests assert that the bucket blocks public access and is
versioned, that each cluster's policy is limited to its own prefix, and that
the budget is optional.
