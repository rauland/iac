# Platform setup

Follow these steps when bootstrapping a fork or a new platform. Existing
installations can go straight to [deployments and operations](deployments.md).
Use separate administrator credentials for bootstrap and scoped credentials for
workload CI, as described in the access guides below.

## 1. Prepare infrastructure and networking

You need a Proxmox VE host with storage and networking for the configured guests,
an AWS account for Terraform state, and a GitHub repository with Actions enabled.
Adapt the workload variables, node names, storage, VM addresses and SSH public
keys to your infrastructure before deploying.

Service VMs use AlmaLinux 10; Kubernetes nodes use Talos. VM networking requires
DHCP and dynamic DNS or explicitly configured static addresses. Talos requires
the reservations and networking in the [Talos module guide](../terraform/modules/talos-cluster/README.md).

Configure a WireGuard peer that GitHub-hosted runners can reach. The
[WireGuard action](../.github/actions/wireguard/action.yml) expects these repository
secrets: `WIREGUARD_PRIVATE_KEY`, `RUNNER_IP`, `PEER_IP`,
`WIREGUARD_PEER_PUBLIC_KEY`, and `WIREGUARD_ENDPOINT`. It currently routes
`10.0.0.0/24` and uses the peer for DNS; adapt this to your network.

For local Terraform work, CI currently uses version `1.15.8`. Install the
[VM seed builder dependency](../terraform/modules/virtual-machine/README.md#api-only-cloud-init-iso)
before planning sandbox locally. The [Ansible guide](../ansible/README.md)
covers its local dependencies and checks.

## 2. Configure Terraform state

Create the versioned, encrypted state bucket once, locally, using a temporary
administrator session (see
[authenticate with temporary administrator credentials](../terraform/platform/state-access/README.md#authenticate-with-temporary-administrator-credentials)).
No AWS keys are stored in GitHub for this step:

```sh
(
  unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
  export AWS_PROFILE=bootstrap bucket=rauland-iac-homelab region=ap-southeast-2
  aws s3api create-bucket --bucket "$bucket" --region "$region" \
    --create-bucket-configuration LocationConstraint="$region" &&
  aws s3api put-bucket-versioning --bucket "$bucket" \
    --versioning-configuration Status=Enabled &&
  aws s3api put-bucket-encryption --bucket "$bucket" \
    --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
)
```

The Terraform roots use an encrypted S3 backend with lock files enabled.

Create the repository variable `TF_CLI_ARGS_init` in GitHub **Settings → Secrets
and variables → Actions → Variables**:

```text
-backend-config=bucket=YOUR_STATE_BUCKET -backend-config=region=YOUR_AWS_REGION
```

Terraform and State Unlock use this variable during initialization and supply
the state key separately as `terraform/<environment>/<target>.tfstate`. Use the
same bucket and region you selected during bootstrap.

For local use, authenticate to AWS and export the variable:

```sh
export TF_CLI_ARGS_init='-backend-config=bucket=YOUR_STATE_BUCKET -backend-config=region=YOUR_AWS_REGION'
terraform -chdir=terraform/workloads/dev/sandbox init \
  -backend-config="key=terraform/dev/sandbox.tfstate"
```

The exported arguments apply to every `terraform init` in that shell. The
[State Unlock workflow](../.github/workflows/state-unlock.yml) accepts an environment,
target, and lock ID for the corresponding state.

## 3. Configure scoped Proxmox and AWS access

Use the administrator-operated [Proxmox access root](../terraform/platform/access/README.md)
to configure pools, users, API tokens, storage and ACLs. Follow its credential
export instructions for the matching GitHub environments. Keep this root's
state inaccessible to workload CI.

Use the [state-access guide](../terraform/platform/state-access/README.md) to
configure scoped AWS identities through IAM or Terraform. Adapt the example
policies to your state bucket. Bootstrap initial state objects with an
administrator before read-only plan credentials initialize a new root.

Each plan/apply environment needs its matching `AWS_ROLE_ARN` and
`AWS_DEFAULT_REGION` variables (see
[GitHub OIDC roles](../terraform/platform/state-access/README.md#github-oidc-roles)),
`TF_VAR_VIRTUAL_ENVIRONMENT_ENDPOINT`, `TF_VAR_VIRTUAL_ENVIRONMENT_API_TOKEN`,
and `PROXMOX_URL` secrets. Dev/prod apply environments also need the scoped
Ansible inventory credentials documented in the Proxmox access guide.

## 4. Configure SSH and service credentials

Follow [SSH automation access](../ssh/README.md) to generate separate dev/prod
SSH keys, commit the public keys, and set `SSH_PRIVATE_KEY_ANSIBLE` in the matching
apply environments. Use verified host pins or the documented guest-agent
enrollment path. The guest agent must already be running for automatic
enrollment; Ansible cannot install it to establish its first connection.

Configure any service-specific credentials required by your target, including
the Cloudflare token for Vault. See the [Ansible guide](../ansible/README.md)
and [Vault role](../ansible/roles/vault/README.md).

## 5. Configure plan encryption

Generate a dedicated encryption key locally with GnuPG:

```sh
plan_key_dir=$(mktemp -d)
gpg --homedir "$plan_key_dir" --batch --passphrase '' \
  --quick-generate-key 'Terraform plan encryption' rsa3072 encr 1y
gpg --homedir "$plan_key_dir" --armor --export 'Terraform plan encryption' \
  > "$plan_key_dir/public.asc"
gpg --homedir "$plan_key_dir" --batch --pinentry-mode loopback --passphrase '' \
  --armor --export-secret-keys 'Terraform plan encryption' \
  > "$plan_key_dir/private.asc"
```

| GitHub setting | Value |
| --- | --- |
| Repository variable `TF_PLAN_PUBLIC_KEY` | Complete contents of `public.asc` |
| Each apply environment secret `TF_PLAN_PRIVATE_KEY` | Complete contents of `private.asc` |

The dedicated private key has no passphrase. Keep a secure backup, remove the
temporary key directory after setup, and rotate the pair before its one-year
expiry. Do not commit the generated files.

## 6. Configure GitHub protections

Create the environments and protections in the
[deployment approval table](deployments.md#approval-and-saved-plans). Restrict
apply environments to `main`, require the documented human approvals, and keep
write credentials and private plan keys in apply environments. Copy the scoped
dev apply settings into `proxmox-dev-auto-apply`, which has no required reviewers.

Configure [main branch protection](deployments.md#main-branch-protection)
separately. Environment names in workflow YAML do not enforce approval by
themselves; GitHub settings must contain the protections.

## 7. Verify the first deployment

Open a pull request and check the required **CI** result and any selected live
plans. Confirm that credentials, state access, networking and intended changes
are correct before merging: pushes to `main` automatically apply changed dev
plans and run selected dev configuration.

Publish [shared cloud images](../terraform/platform/images/README.md) before
creating VMs that depend on them. In the deployment workflow, choose environment
`platform`, scope `single`, target `images`, and mode `infrastructure`.

For a manual workload run, choose its environment and target with scope `single`
and mode `auto`. Review the deployment summary and approve protected jobs when
required. See [manual modes](deployments.md#manual-modes) for configuration-only
runs and explicit destroy, and [VM configuration](deployments.md#vm-configuration-with-ansible)
for the sandbox example and recovery steps.
