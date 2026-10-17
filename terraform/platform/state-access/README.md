# CI state access

This administrator-operated root can create six dedicated IAM users and access keys
for dev, prod and shared-image plan/apply environments. It is excluded from
automatic deployment discovery. Its encrypted state contains all six secret
keys and must remain inaccessible to workload CI.

## AWS console setup

The existing CLI user intentionally has no IAM administration privileges. To
create these identities using an AWS administrator in the portal instead:

1. In IAM → Users → Create user, use the user name from the table below. Leave
   console access disabled; these users need API credentials only.
2. Create an inline policy using the **JSON** editor and paste the corresponding
   exported file. Name the inline policy `terraform-state` and attach no other
   policies or groups.
3. Under Security credentials, create an access key for an application running
   outside AWS. Save the secret securely when displayed.
4. In the matching GitHub environment, create `AWS_ACCESS_KEY_ID` and
   `AWS_SECRET_ACCESS_KEY` using that user's key pair.

| IAM user | Policy JSON | GitHub environment |
| --- | --- | --- |
| `iac-tf-dev-plan` | [tf-dev-plan.json](policies/tf-dev-plan.json) | `proxmox-dev-plan` |
| `iac-tf-dev-apply` | [tf-dev-apply.json](policies/tf-dev-apply.json) | `proxmox-dev-apply` |
| `iac-tf-prod-plan` | [tf-prod-plan.json](policies/tf-prod-plan.json) | `proxmox-prod-plan` |
| `iac-tf-prod-apply` | [tf-prod-apply.json](policies/tf-prod-apply.json) | `proxmox-prod-apply` |
| `iac-tf-platform-images-plan` | [tf-platform-images-plan.json](policies/tf-platform-images-plan.json) | `proxmox-platform-plan` |
| `iac-tf-platform-images-apply` | [tf-platform-images-apply.json](policies/tf-platform-images-apply.json) | `proxmox-platform-apply` |

The files target bucket `rauland-iac-homelab`. Before running CI,
verify that plan users can read only their state,
apply users can write their state/manage locks, and all six are denied access to
`terraform/platform/access.tfstate` and `terraform/platform/state-access.tfstate`.
Then follow the [GitHub cutover/secret cleanup checklist](../access/GITHUB-CUTOVER.md).

The JSON files are exported from a mocked Terraform plan, not a second policy
implementation. Regenerate after changes using `python3 export_policies.py`
(after `terraform init -backend=false`). This makes no AWS API calls.

## Optional Terraform provisioning

Run these commands from the repository root on the machine where Terraform will
run. `init` configures the backend and installs providers; `apply` creates the six
IAM users, inline policies and access keys.

Do not apply this root against IAM users already created in the console without
importing those users, inline policies and access keys first. Importing an access
key cannot recover its secret; keep the portal-created secret in GitHub or a
secure local backup. Console setup does not require applying this root.

### Authenticate with temporary administrator credentials

Use a separate browser-authenticated session with IAM administration and backend
access. Keep the existing least-privilege CLI user's permissions unchanged.
AWS CLI 2.32.0 or newer supports `aws login`; the IAM identity needs
`SignInLocalDevelopmentAccess` permissions as well as permission to manage these
resources. Use an IAM user or role for the administrator session.

```sh
aws login --profile bootstrap-login --remote --region ap-southeast-2
```

Open the displayed URL, select the administrator identity and enter the resulting
authorization code in the terminal. Do not paste credentials or authorization
codes into chat. If you use IAM Identity Center, configure and authenticate an
SSO profile instead.

Configure a second profile so Terraform's provider and S3 backend can obtain
temporary credentials through the CLI's credential process:

```sh
aws configure set credential_process \
  'aws configure export-credentials --profile bootstrap-login --format process' \
  --profile bootstrap
aws configure set region ap-southeast-2 --profile bootstrap
```

These commands store profile configuration and a local login cache, not
administrator keys in the repository. See AWS's
[browser login and credential-process documentation](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html).

### Initialize, review and apply

Use a subshell to clear exported keys from `.bashrc` that would otherwise override
the profile. This preserves the credentials and settings in your normal shell.
Check that `get-caller-identity` reports account `533245699488` and the intended
administrator identity before continuing.

```sh
(
  unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
  unset AWS_SESSION_TOKEN AWS_SECURITY_TOKEN
  export AWS_PROFILE=bootstrap
  umask 077

  aws sts get-caller-identity &&
  terraform -chdir=terraform/platform/state-access init \
    -backend-config=bucket=rauland-iac-homelab \
    -backend-config=region=ap-southeast-2 \
    -backend-config=key=terraform/platform/state-access.tfstate &&
  terraform -chdir=terraform/platform/state-access plan -out=tfplan &&
  {
    printf 'Review the plan above. Apply it? [y/N] '
    read -r answer
    if [ "$answer" = y ]; then
      terraform -chdir=terraform/platform/state-access apply tfplan
    fi
  }
)
```

### Handle generated credentials

The `state_credentials` output is sensitive, so normal Terraform output hides
its values. The actual secret keys remain in the encrypted S3 state. Keep access
to this administrator state restricted; workload CI must never be able to read
it. Saved plans and local state backups may also contain sensitive data.

Upload each generated key pair to the GitHub environment in the table above as
`AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`. For automation, capture
`terraform output -json state_credentials` in process memory and pass each value
to `gh secret set --repo rauland/iac --env <environment> <secret-name>` through
stdin. Do not print the JSON or put secret values in command-line arguments.
If exporting to a file is necessary, use the gitignored `.credentials/` directory
with directory mode `700` and file mode `600`.

Never put administrator credentials in `.tfvars`, backend arguments, `.bashrc`,
GitHub secrets or committed files. Once provisioning and secret uploads are
complete, end the temporary login session:

```sh
aws logout --profile bootstrap-login
```

## State permission boundaries

Plan users can read matching state objects. Apply users can also write those
objects and manage their `.tflock` files. They cannot delete state objects.
Dev/prod object access is restricted to `terraform/dev/*.tfstate` or
`terraform/prod/*.tfstate`; image access is restricted to
`terraform/platform/images.tfstate`. An explicit deny prevents access to objects
outside the selected state scope, including both administrator access states
and their historical versions. Bucket listing exposes key metadata only.
Only the default Terraform workspace is supported by these policies.

Initial states for new roots must be bootstrapped by an administrator before a
read-only plan credential can initialize them. Export `state_credentials` only
into an owner-only file and upload each key pair to the corresponding GitHub
environment's `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` secrets. Never export
the administrator's broad AWS credentials to those environments.

Validate with `terraform validate` and run mocked policy tests with
`terraform test` from this directory.
