# Platform setup

Follow these steps when bootstrapping a fork or a new platform. Existing
installations can go straight to [deployments and operations](deployments.md).
Use separate administrator credentials for bootstrap and scoped credentials for
workload CI, as described in the access guides below.

## 1. Prepare infrastructure and networking

You need a Proxmox VE host with storage and networking for the configured guests,
an AWS account for Terraform state, and a GitHub repository with Actions enabled.
Adapt the workload variables, node names, storage and VM addresses to your
infrastructure before deploying.

The only VMs are the Talos Kubernetes nodes; workloads run on Kubernetes. Talos
requires the reservations and networking in the
[Talos module guide](../terraform/modules/talos-cluster/README.md).

GitHub-hosted runners reach the private network through Tailscale. Each job
joins the tailnet as an ephemeral `tag:ci` node using its GitHub OIDC token, so
no Tailscale secret is stored. Set up:

1. A subnet router (for example the LAN router) advertising the private network,
   currently `10.0.0.0/24`, with the route approved in the Tailscale admin
   console and IP masquerading enabled.
2. Access rules that keep `tag:ci` to that subnet and the ports CI needs
   (Proxmox API `8006`, Talos API `50000`, Kubernetes API `6443`), and
   that no rule grants all tagged devices broader access.
3. Split DNS sending the Proxmox hostname's domain to the LAN resolver, and an
   access rule letting `tag:ci` reach that resolver on `udp:53` and `tcp:53`.
   Without it, CI nodes cannot resolve internal names and the Proxmox API
   check times out.
4. A workload identity federation trust credential for issuer GitHub, subject
   `repo:<owner>/<repo>:environment:*`, scope `auth_keys` (write) and tag
   `tag:ci`. Store its client ID and audience as repository variables
   `TS_OAUTH_CLIENT_ID` and `TS_AUDIENCE`; neither is secret.

The [Tailscale action](../.github/actions/tailscale/action.yml) waits until the
Proxmox API answers before Terraform runs.

For local Terraform work, CI currently uses version `1.15.8`.

## 2. Configure Terraform state

Create the versioned, encrypted state bucket once, locally, using a temporary
administrator session (see
[authenticate with temporary administrator credentials](../terraform/platform/state-access/README.md#authenticate-with-temporary-administrator-credentials)).
No AWS keys are stored in GitHub for this step:

```sh
(
  unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
  export AWS_PROFILE=admin bucket=rauland-iac-homelab region=ap-southeast-2
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

Also create the repository variable `TF_STATE_BUCKET` holding just the bucket
name. The [Flux root](../kubernetes/README.md) uses it to read the Talos root's
state for the cluster's API credentials. Locally, export it as `TF_VAR_state_bucket`.

For local use, authenticate to AWS and export the variable:

```sh
export TF_CLI_ARGS_init='-backend-config=bucket=YOUR_STATE_BUCKET -backend-config=region=YOUR_AWS_REGION'
terraform -chdir=terraform/workloads/dev/talos init \
  -backend-config="key=terraform/dev/talos.tfstate"
```

The exported arguments apply to every `terraform init` in that shell. The
[State Unlock workflow](../.github/workflows/state-unlock.yml) accepts an environment,
target, and lock ID for the corresponding state.

## 3. Configure scoped Proxmox and AWS access

First prepare the Proxmox host once, as root from its console: the
[host preparation script](../terraform/platform/access/scripts/prepare-host.sh)
creates the ZFS datasets for each environment's Kubernetes storage, which the
Proxmox API cannot create. Then use the administrator-operated
[Proxmox access root](../terraform/platform/access/README.md)
to configure pools, users, API tokens, storage and ACLs. Follow its credential
export instructions for the matching GitHub environments. Keep this root's
state inaccessible to workload CI.

Use the [state-access guide](../terraform/platform/state-access/README.md) to
configure scoped AWS identities through IAM or Terraform. Adapt the example
policies to your state bucket. Bootstrap initial state objects with an
administrator before read-only plan credentials initialize a new root.

Each plan/apply environment needs its matching `AWS_ROLE_ARN` and
`AWS_DEFAULT_REGION` variables (see
[GitHub OIDC roles](../terraform/platform/state-access/README.md#github-oidc-roles)).
Proxmox endpoints and tokens are SSM parameters, listed in
[CI parameters](../terraform/platform/state-access/README.md#ci-parameters).

## 4. Expire saved plans and snapshots

Deployments keep each saved plan in the state bucket under
`plans/<environment>/`, and the Talos upgrade keeps an etcd snapshot under
`etcd-snapshots/<environment>/`. Both hold secrets in plain form, so the
[state-access roles](../terraform/platform/state-access/README.md#state-permission-boundaries)
let only the matching environment's plan role write a plan, its apply role
read it, and administrators read the snapshots. Nothing needs a key of its own.

Expire both after seven days, as the bucket is versioned. Adding a lifecycle
configuration replaces any rules the bucket already has, so check first:

```sh
aws s3api get-bucket-lifecycle-configuration --profile admin --bucket rauland-iac-homelab
```

If that reports `NoSuchLifecycleConfiguration`, add the rules; otherwise add
these two to the existing ones:

```sh
aws s3api put-bucket-lifecycle-configuration --profile admin --bucket rauland-iac-homelab \
  --lifecycle-configuration '{"Rules": [
    {"ID": "expire-saved-plans", "Status": "Enabled", "Filter": {"Prefix": "plans/"},
     "Expiration": {"Days": 7}, "NoncurrentVersionExpiration": {"NoncurrentDays": 1}},
    {"ID": "expire-etcd-snapshots", "Status": "Enabled", "Filter": {"Prefix": "etcd-snapshots/"},
     "Expiration": {"Days": 7}, "NoncurrentVersionExpiration": {"NoncurrentDays": 1}}]}'
```

## 5. Configure GitHub protections

Create the environments and protections in the
[deployment approval table](deployments.md#approval-and-saved-plans). Restrict
apply environments to `main`, require the documented human approvals, and keep
write credentials in apply environments. Copy the scoped
dev apply settings into `proxmox-dev-auto-apply`, which has no required reviewers.

Configure [main branch protection](deployments.md#main-branch-protection)
separately. Environment names in workflow YAML do not enforce approval by
themselves; GitHub settings must contain the protections.

## 6. Verify the first deployment

Open a pull request and check the required **CI** result and any selected live
plans. Confirm that credentials, state access, networking and intended changes
are correct before merging: pushes to `main` automatically apply changed dev
plans.

For a manual run, choose the environment and target (`talos` or `flux`) with
scope `single` and mode `auto`. Review the deployment summary and approve
protected jobs when required. See [manual modes](deployments.md#manual-modes)
for explicit destroy.
