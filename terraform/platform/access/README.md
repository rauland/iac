# Proxmox environment access

This administrator-operated root owns pools, groups, service users, API tokens,
ACLs, shared infrastructure membership, and the `dev-images` directory storage.
Deployment discovery explicitly excludes this root; only `platform/images` is
automatically deployable under platform. Workload roots own their VM membership
through `pool_id`.

Use a platform administrator's credentials for this root. Do not give its token
or state access to workload CI. The state contains all generated token secrets.

## State and initialization

Use the existing encrypted, versioned S3 backend with its own state key:

```sh
terraform -chdir=terraform/platform/access init \
  -backend-config=bucket=YOUR_STATE_BUCKET \
  -backend-config=region=YOUR_AWS_REGION \
  -backend-config=key=terraform/platform/access.tfstate
terraform -chdir=terraform/platform/access plan -out=tfplan
terraform -chdir=terraform/platform/access apply tfplan
```

Set `TF_VAR_virtual_environment_endpoint` and the ephemeral, sensitive
`TF_VAR_virtual_environment_api_token` through your shell. Normal resource
changes cannot destroy the pools, storage, service users or tokens because they
have `prevent_destroy` enabled. Existing legacy identities are not owned or
revoked by this root.

## Pools and roles

| Pool | Initial guests | Owner |
| --- | --- | --- |
| `dev` | Vault 103, Talos 104/106/107, sandbox Podman VM (replaces Cockpit 113) | Dev workload roots |
| `prod` | Initially empty | Future prod workload roots |
| `infra` | PBS 100, Ansible 101, PDM 105, NFS 116 | This root |

Docker 102 stays unassigned until classified. For the initial migration only,
add the existing dev guests through Datacenter → Pools → dev → Members. This
changes access scope without changing VM hardware or power state. Do not also
declare dev membership resources in this root.

Human groups are initially empty. Assign existing human accounts explicitly:
`platform-admins` has Administrator on `/`; `dev-admins` and `prod-admins` have
VM administration in their own pool, and viewers have audit privileges there.
Administrators also receive disk allocation, shared image read access, bridge
use, and node audit privileges. They do not manage access assignments or publish
shared images.

Automation is separated into plan/apply users for dev/prod, read-only Ansible
inventory users for dev/prod, and plan/apply shared image publishers. Every token
has privilege separation enabled and matching explicit user/token ACLs. No
automation identity created here has a global `/` or `/vms` grant.

Dev/prod plan identities additionally receive `PlanDiskAccess`
(`VM.Config.Disk`) only on their own pool. The pinned provider reads disk
metadata through an endpoint that requires this permission. These plan tokens
can modify disks in their own environment; they are not strictly read-only.
They cannot change memory, power, CPU or access another environment's guests.
Ansible inventory and shared-image plan tokens remain strictly read-only.

`dev-images` stores ISOs under `/var/lib/proxmox-dev-images`, outside the shared
`local` directory. Dev apply can publish there but only read shared images.
Download permission is `Sys.AccessNetwork` on the selected node; it does not
grant `Sys.Modify`. Directory storage shares the host filesystem's capacity;
this does not introduce a quota or a separate disk.

## Credential export and GitHub cutover

See the [cutover and old-secret cleanup checklist](GITHUB-CUTOVER.md) for the
uploaded environment configuration and remaining AWS console setup.

Token values are sensitive. Export them only into a private, ignored directory:

```sh
umask 077
mkdir -p terraform/platform/access/.credentials
terraform -chdir=terraform/platform/access output -json automation_credentials \
  > terraform/platform/access/.credentials/automation.json
```

Each entry contains `user_id`, `token_name`, `token_id`, `secret`, and the full
`api_token`. The full API token is the Terraform secret; Ansible uses the three
separate user/name/secret fields.

| GitHub environment | Terraform identity | Inventory identity |
| --- | --- | --- |
| `proxmox-dev-plan` | `tf-dev-plan` | — |
| `proxmox-dev-apply` | `tf-dev-apply` | `ansible-dev` |
| `proxmox-dev-auto-apply` | `tf-dev-apply` | `ansible-dev` |
| `proxmox-prod-plan` | `tf-prod-plan` | — |
| `proxmox-prod-apply` | `tf-prod-apply` | `ansible-prod` |
| `proxmox-platform-plan` | `tf-platform-images-plan` | — |
| `proxmox-platform-apply` | `tf-platform-images-apply` | — |

The [platform/images root](../images/README.md) uses platform image credentials
and state key `terraform/platform/images.tfstate`: its output is shared by dev
workloads too.

In each environment, set `TF_VAR_VIRTUAL_ENVIRONMENT_API_TOKEN` to the matching
full token, and `TF_VAR_VIRTUAL_ENVIRONMENT_ENDPOINT` / `PROXMOX_URL` to the API
URL. In dev/prod apply environments, set `PROXMOX_USER_ANSIBLE`,
`PROXMOX_TOKEN_ID_ANSIBLE` and `PROXMOX_TOKEN_SECRET_ANSIBLE` from the inventory
identity. Retain the existing WireGuard secrets, AWS credentials/region, and
backend init settings. Apply environments also need `TF_PLAN_PRIVATE_KEY`;
dev/prod apply environments need their distinct Ansible SSH private keys and
the Cloudflare secret. See [SSH access and rotation](../../../ssh/README.md).
Keep the public plan encryption key in the repository variable.

Allow deployment only from `main` for all apply environments. Dev Terraform
apply uses `proxmox-dev-auto-apply` without required reviewers, with the same
scoped credentials and variables as `proxmox-dev-apply`. Keep reviewers on
`proxmox-dev-apply` for explicit destroy, state unlock, and standalone Ansible,
and on the prod/platform apply environments. Also require reviewers for
`proxmox-prod-plan`, because
its credentials permit disk changes. Dev plan and shared-image plan environments
can run without reviewers. Configure all secrets and deployment protections
before running the workflows.

**AWS permissions must be scoped before retiring legacy access.** Workload CI
credentials must not be able to read `terraform/platform/access.tfstate`, its
S3 lock file or historical versions. Scope dev and prod credentials to their own
state prefixes; scope image CI to `terraform/platform/images.tfstate`. Scope plan
credentials to reading state (planning uses `-lock=false`); apply credentials
also need the corresponding state write/lock permissions. Shared AWS credentials
that can read every state would bypass the Proxmox separation. Backend
encryption alone does not provide this separation.
The [state-access root](../state-access/README.md) provisions these six scoped
AWS identities using an IAM administrator's credentials.

Verify normal plans and disposable guest lifecycle operations before revoking
the old shared credentials. Keep a working platform administrator available.
Then remove the propagated `PVEVMAdmin` ACLs on `/vms` for both
`proxmox-ro@pve` and `proxmox-ro@pve!proxmox-ro`, and retire the old
`proxmox-rw` CI identity/token after all workflows have moved. The local
`terraform@pve` administrator remains the bootstrap identity for this root until
a replacement platform administration mechanism is configured. Also retire or
rescope the old global Ansible inventory identity after the new ones are in use.
Remove obsolete CI secrets from the old environments and repository scope.

## Validation and live verification

```sh
terraform -chdir=terraform/platform/access validate
terraform -chdir=terraform/platform/access test
python3 terraform/platform/access/verify_access.py
```

The Terraform tests mock Proxmox and assert environment boundaries, the explicit
plan-only disk exception, matching token/user ACLs and image-publisher restrictions.
The Python verifier requires `requests`, reads the protected credential export,
creates two stopped diskless guests in dev/prod, tests owner lifecycle access
and denied cross-environment writes, and deletes both guests in a `finally`
block. It prints no secrets.

The Talos module's `removed` block stops managing pre-RBAC boot media without
deleting it. The next dev Talos apply creates new media in `dev-images` and
updates CD-ROM references; review that saved plan normally. Do not reintroduce
the old ISO resource or grant dev permission to delete shared images.
