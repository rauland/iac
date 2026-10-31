# Off-site backup storage

This administrator-operated root creates the S3 bucket that holds the off-site
copy of Proxmox Backup Server (PBS) backups, and the IAM user PBS uses to reach
it. It is excluded from automatic deployment discovery; CI cannot plan or apply
it.

Backups follow 3-2-1: guests live on local SSDs, PBS keeps nightly backups on
the `nas` ZFS pool, and a PBS sync job copies selected backups to this bucket.
The media library is not copied off-site; it can be downloaded again.

## What it creates

| Resource | Notes |
| --- | --- |
| S3 bucket `rauland-homelab-pbs-offsite` | Private, encrypted at rest, TLS only, no versioning. Incomplete uploads are removed after seven days. Protected from `terraform destroy`. |
| IAM user `pbs-offsite` | Can list the bucket and read, write and delete its objects; nothing else in the account. |
| Monthly budget (optional) | Emails when actual or forecast spend exceeds `budget_limit_usd`. Created only when `budget_email` is set. |

PBS deduplicates and prunes its own chunks, so object versioning would only
keep deleted chunks billable. Retention is set on the PBS side.

## Why this root has an access key

The rest of the repository uses no IAM users or long-lived keys. PBS can only
authenticate to S3 with a static access key, so `pbs-offsite` is the single
exception. Its policy covers one bucket, and the key is created outside
Terraform so the secret never enters state.

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
kind of subshell. Omit `-var budget_email=…` to skip the budget.

## Create or rotate the PBS key

Create the key only when you are ready to enter it in PBS, and put it straight
into the PBS S3 endpoint form (Configuration → S3 Endpoints) without saving it
elsewhere:

```sh
AWS_PROFILE=admin aws iam create-access-key --user-name pbs-offsite \
  --query 'AccessKey.[AccessKeyId,SecretAccessKey]' --output text
```

Use endpoint `s3.ap-southeast-2.amazonaws.com`, region `ap-southeast-2` and
path-style addressing off. To rotate, create a second key (a user may have
two), update the PBS endpoint, confirm a sync job succeeds, then delete the old
key:

```sh
AWS_PROFILE=admin aws iam list-access-keys --user-name pbs-offsite
AWS_PROFILE=admin aws iam delete-access-key --user-name pbs-offsite --access-key-id <old key id>
```

## Checks

Run `terraform validate` and the offline tests with `terraform test` from this
directory. The tests assert that the bucket blocks public access, that the PBS
policy is limited to its own bucket, and that the budget is optional.
