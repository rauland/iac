# CI state access

This administrator-operated root creates six scoped IAM roles that GitHub Actions
assumes through OIDC, one per dev, prod and shared-image plan/apply identity.
Workflows receive temporary credentials for one hour; no AWS keys are stored in
GitHub. It is excluded from automatic deployment discovery. Keep its state
administrator-only so workload CI cannot change its own trust or permissions.

## GitHub OIDC roles

Each role trusts only tokens that GitHub issues to jobs running in the listed
environments of `rauland/iac`, so branch, pull-request and fork jobs cannot
assume them without passing environment protection. Each role carries a
`terraform-state` inline policy; console-ready copies are in [policies](policies).

| IAM role | GitHub environments (`AWS_ROLE_ARN` variable) |
| --- | --- |
| `iac-tf-dev-plan` | `proxmox-dev-plan` |
| `iac-tf-dev-apply` | `proxmox-dev-apply`, `proxmox-dev-auto-apply` |
| `iac-tf-prod-plan` | `proxmox-prod-plan` |
| `iac-tf-prod-apply` | `proxmox-prod-apply` |
| `iac-tf-platform-images-plan` | `proxmox-platform-plan` |
| `iac-tf-platform-images-apply` | `proxmox-platform-apply` |

The plan, deploy and state-unlock jobs request `id-token: write` and call
`aws-actions/configure-aws-credentials` with the environment's `AWS_ROLE_ARN`.

### CI parameters

CI reads its Proxmox, Ansible and saved-plan secrets from SSM
Parameter Store instead of GitHub environment secrets. Each parameter's last
path segment is the environment variable it becomes. The plan and deploy jobs
run [load-parameters.py](../../../.github/scripts/load-parameters.py) right after
assuming their role; it masks every line of each `SecureString` before
exporting it, and refuses secrets shorter than eight characters, which cannot
be masked reliably. Roles can only read, and only these prefixes:

| Parameter | Type | Readable by |
| --- | --- | --- |
| `/iac/shared/proxmox/PROXMOX_URL`, `.../TF_VAR_virtual_environment_endpoint` | SecureString | All roles |
| `/iac/shared/apply/TF_PLAN_PRIVATE_KEY` | SecureString | Apply roles |
| `/iac/<scope>/plan/TF_VAR_virtual_environment_api_token` | SecureString | That scope's plan role |
| `/iac/<scope>/apply/TF_VAR_virtual_environment_api_token` | SecureString | That scope's apply role |
| `/iac/<scope>/ansible/PROXMOX_TOKEN_SECRET_ANSIBLE`, `.../SSH_PRIVATE_KEY_ANSIBLE` | SecureString | Dev and prod apply roles |
| `/iac/<scope>/ansible/PROXMOX_USER_ANSIBLE`, `.../PROXMOX_TOKEN_ID_ANSIBLE` | String | Dev and prod apply roles |

`<scope>` is `dev`, `prod` or `platform`. No role can read another scope's
values, and plan roles cannot read apply values. Roles may also read
`/iac/shared/wireguard/`, which is unused since CI moved to Tailscale.
`String` parameters hold non-secret identifiers and are
not masked.

To set or rotate a value, use the `admin` profile and keep the value out of
command-line arguments, for example by passing a request file:

```sh
umask 077; printf '%s' '{"Name":"/iac/dev/apply/TF_VAR_virtual_environment_api_token","Type":"SecureString","Overwrite":true,"Value":"..."}' > request.json
aws ssm put-parameter --profile admin --cli-input-json file://request.json && rm request.json
```

Write the JSON with an editor or a script rather than typing the value into the
shell, so it stays out of shell history.

### Roll out

1. [Apply this root](#initialize-review-and-apply) as an administrator. It adds
   the GitHub OIDC provider, six roles and their policies. If the account
   already has a
   `token.actions.githubusercontent.com` provider, import it first:
   `terraform import aws_iam_openid_connect_provider.github <provider-arn>`.
2. Set each environment's `AWS_ROLE_ARN` variable from the
   `state_role_arns` output (role ARNs are not secret):

   ```sh
   terraform -chdir=terraform/platform/state-access output -json state_role_arns |
     jq -r 'to_entries[] | .value.role_arn as $arn | .value.github_environments[] | "\(.) \($arn)"' |
     while read -r environment arn; do
       gh api --method POST "repos/rauland/iac/environments/$environment/variables" \
         -f name=AWS_ROLE_ARN -f value="$arn"
     done
   ```

3. Run a plan, for example a manual `infrastructure` run for dev sandbox, and
   confirm the "Assume scoped AWS state role" step succeeds.

## AWS console setup

To create the roles in the IAM console instead of applying this root:

1. In IAM → Identity providers, add an OpenID Connect provider with URL
   `https://token.actions.githubusercontent.com` and audience `sts.amazonaws.com`.
2. In IAM → Roles → Create role, choose **Web identity**, that provider and
   audience `sts.amazonaws.com`, and use the role name from the table below.
3. Edit the trust policy so `token.actions.githubusercontent.com:sub` equals
   `repo:rauland/iac:environment:<environment>` for each listed environment.
   Set the maximum session duration to one hour.
4. Add an inline policy named `terraform-state` from the **JSON** editor using
   the matching exported file. Attach no other policies.
5. Set each listed GitHub environment's `AWS_ROLE_ARN` variable to the role ARN.

| IAM role | Policy JSON | GitHub environments |
| --- | --- | --- |
| `iac-tf-dev-plan` | [tf-dev-plan.json](policies/tf-dev-plan.json) | `proxmox-dev-plan` |
| `iac-tf-dev-apply` | [tf-dev-apply.json](policies/tf-dev-apply.json) | `proxmox-dev-apply`, `proxmox-dev-auto-apply` |
| `iac-tf-prod-plan` | [tf-prod-plan.json](policies/tf-prod-plan.json) | `proxmox-prod-plan` |
| `iac-tf-prod-apply` | [tf-prod-apply.json](policies/tf-prod-apply.json) | `proxmox-prod-apply` |
| `iac-tf-platform-images-plan` | [tf-platform-images-plan.json](policies/tf-platform-images-plan.json) | `proxmox-platform-plan` |
| `iac-tf-platform-images-apply` | [tf-platform-images-apply.json](policies/tf-platform-images-apply.json) | `proxmox-platform-apply` |

The files target bucket `rauland-iac-homelab`. Before running CI,
verify that plan roles can read only their state,
apply roles can write their state/manage locks, and all six are denied access to
`terraform/platform/access.tfstate` and `terraform/platform/state-access.tfstate`.

The JSON files are exported from a mocked Terraform plan, not a second policy
implementation. Regenerate after changes using `python3 export_policies.py`
(after `terraform init -backend=false`). This makes no AWS API calls.

## Optional Terraform provisioning

Run these commands from the repository root on the machine where Terraform will
run. `init` configures the backend and installs providers; `apply` creates the
GitHub OIDC provider, six roles and their inline policies.

Do not apply this root against roles already created in the console without
importing the provider, roles and inline policies first. Console setup does not
require applying this root.

### Authenticate with temporary administrator credentials

Use a short-lived IAM Identity Center session with the `AdministratorAccess`
permission set (one-hour sessions, MFA at sign-in). Do not use the root user.
Day-to-day local Terraform uses a separate `TerraformState` permission set that
can only read and write objects in the state bucket.
Add the session and profile to `~/.aws/config` once:

```ini
[sso-session rauland]
sso_start_url = <AWS access portal URL from IAM Identity Center settings>
sso_region = ap-southeast-2
sso_registration_scopes = sso:account:access

[profile admin]
sso_session = rauland
sso_account_id = <account ID>
sso_role_name = AdministratorAccess
region = ap-southeast-2
```

Then sign in before each administrative change:

```sh
aws sso login --sso-session rauland --use-device-code
```

Open the displayed URL, sign in as the Identity Center user and approve the code.
Do not paste credentials or authorization codes into chat. The CLI caches only
the temporary session, not administrator keys.

### Initialize, review and apply

Use a subshell to clear exported keys from `.bashrc` that would otherwise override
the profile. This preserves the credentials and settings in your normal shell.
Check that `get-caller-identity` reports account `533245699488` and the intended
administrator identity before continuing.

```sh
(
  unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
  unset AWS_SESSION_TOKEN AWS_SECURITY_TOKEN
  export AWS_PROFILE=admin
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

### After applying

Set the `AWS_ROLE_ARN` variables as described in [Roll out](#roll-out). The
state holds no secret keys, but keep it administrator-only: anyone who can
write it can change which workflows the roles trust.

Never put administrator credentials in `.tfvars`, backend arguments, `.bashrc`,
GitHub secrets or committed files. Once provisioning is complete, end the
temporary login session:

```sh
aws sso logout
```

## State permission boundaries

Plan roles can read matching state objects. Apply roles can also write those
objects and manage their `.tflock` files. They cannot delete state objects.
Dev/prod object access is restricted to `terraform/dev/*.tfstate` or
`terraform/prod/*.tfstate`; image access is restricted to
`terraform/platform/images.tfstate`. An explicit deny prevents access to objects
outside the selected state scope, including both administrator access states
and their historical versions. Bucket listing exposes key metadata only.
Only the default Terraform workspace is supported by these policies.

Initial states for new roots must be bootstrapped by an administrator before a read-only plan role can initialize
them. Never export the administrator's broad AWS credentials to those
environments.

Validate with `terraform validate` and run mocked policy tests with
`terraform test` from this directory.
