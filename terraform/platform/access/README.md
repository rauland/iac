# Proxmox environment access

This administrator-operated root owns pools, groups, service users, API tokens,
ACLs, shared infrastructure membership, and the `dev-images` directory storage.
Deployment discovery excludes every root under `platform`. Workload roots own
their VM membership through `pool_id`.

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
| `dev` | Talos 104/106/107, sandbox testing VM | Dev workload roots |
| `prod` | Initially empty | Future prod workload roots |
| `infra` | Existing shared guests in `infra_vm_ids` | This root |

Docker 102 stays unassigned until classified. For the initial migration only,
add the existing dev guests through Datacenter → Pools → dev → Members. This
changes access scope without changing VM hardware or power state. Do not also
declare dev membership resources in this root.

Human groups are initially empty. Assign existing human accounts explicitly:
`platform-admins` has Administrator on `/`; `dev-admins` and `prod-admins` have
VM administration in their own pool, and viewers have audit privileges there.
Administrators also receive disk allocation, shared image read access, bridge
use, and node audit privileges. They do not manage access assignments.

Automation is separated into plan/apply users for dev/prod and Kubernetes CSI
users for environments with Kubernetes storage. Every token
has privilege separation enabled and matching explicit user/token ACLs. No
automation identity created here has a global `/` or `/vms` grant.

VM creation stages tags after pool assignment to handle Proxmox's create-time
tag permission check. Both stages use the existing environment apply token;
no additional ACLs are needed. The tag-only follow-up plan is validated against
the original reviewed intent. See [VM tag staging](../../../docs/deployments.md#vm-tag-staging)
for the plan/artifact checks and recovery procedure.

Dev/prod plan identities additionally receive `PlanDiskAccess`
(`VM.Config.Disk`) only on their own pool. The pinned provider reads disk
metadata through an endpoint that requires this permission. These plan tokens
can modify disks in their own environment; they are not strictly read-only.
They cannot change memory, power, CPU or access another environment's guests.
Only the apply identities, which administer their own pool's VMs, have
guest-agent access; the live verifier checks that plan identities cannot read
guest files. Nothing logs in to guests; see the
[platform direction](../../../docs/decisions/0001-kubernetes-first.md).

`dev-images` stores ISOs under `/var/lib/proxmox-dev-images`, outside the shared
`local` directory. Dev apply receives `SeedPublisher` only on `/storage/dev-images`:
`Datastore.Audit`, `Datastore.AllocateTemplate`, and `Datastore.Allocate`.
The last privilege is required by the API to delete seed ISOs during Terraform
replacement/destroy; upload permission alone does not allow cleanup. Both the
privilege-separated token and its owner have matching grants. Plan identities
remain audit-only on this storage, and dev apply can only read shared images.
The shared `ImagePublisher` role does not receive the deletion privilege.
Download permission is `Sys.AccessNetwork` on the selected node; it does not
grant `Sys.Modify`. Directory storage shares the host filesystem's capacity;
this does not introduce a quota or a separate disk.

### Kubernetes volumes

Each environment in `kubernetes_storage_pools` gets a ZFS storage named
`k8s-<environment>` and a `k8s-csi-<environment>@pve` identity for the
[Proxmox CSI plugin](../../../kubernetes/README.md#persistent-storage). Dev uses
the `nas/k8s-dev` dataset. Create the dataset on the host before the first apply:
the provider registers storage but cannot create ZFS datasets.

```sh
zfs create nas/k8s-dev
```

The identity has `KubernetesDisk` (`VM.Audit`, `VM.Config.Disk`) on its
environment's pool and `KubernetesStorage` (`Datastore.Audit`,
`Datastore.Allocate`, `Datastore.AllocateSpace`) only on its own storage.
`Datastore.Allocate` deletes any volume on a storage, which is why Kubernetes
volumes do not use a shared storage: there it could delete other guests'
disks. `VM.Config.Disk` covers every
guest in the pool, so the token can detach a disk from any dev VM, though it
cannot delete disks outside `k8s-dev`. It cannot change memory, power or CPU.

The token secret goes into the cluster as a SOPS-encrypted Secret; see the
[Kubernetes guide](../../../kubernetes/README.md#persistent-storage).

## Credential export and GitHub cutover

Token values are sensitive. Export them only into a private, ignored directory:

```sh
umask 077
mkdir -p terraform/platform/access/.credentials
terraform -chdir=terraform/platform/access output -json automation_credentials \
  > terraform/platform/access/.credentials/automation.json
```

Each entry contains `user_id`, `token_name`, `token_id`, `secret`, and the full
`api_token`. The full API token is the Terraform secret.

| GitHub environment | Terraform identity |
| --- | --- |
| `proxmox-dev-plan` | `tf-dev-plan` |
| `proxmox-dev-apply` | `tf-dev-apply` |
| `proxmox-dev-auto-apply` | `tf-dev-apply` |
| `proxmox-prod-plan` | `tf-prod-plan` |
| `proxmox-prod-apply` | `tf-prod-apply` |

Store each identity's full token as the matching
`/iac/<scope>/<plan|apply>/TF_VAR_virtual_environment_api_token` SSM parameter.
The full layout, including the API URL and saved plan key, is in
[CI parameters](../state-access/README.md#ci-parameters). Runners reach Proxmox
through Tailscale and need no network secret.
Keep the public plan encryption key in the repository variable.

Allow deployment only from `main` for all apply environments. Dev Terraform
apply uses `proxmox-dev-auto-apply` without required reviewers, with the same
scoped credentials and variables as `proxmox-dev-apply`. Keep reviewers on
`proxmox-dev-apply` for explicit destroy and state unlock, and on
`proxmox-prod-apply`. Also require reviewers for `proxmox-prod-plan`, because
its credentials permit disk changes. The dev plan environment can run without
reviewers. Configure all secrets and deployment protections
before running the workflows.

**AWS permissions must be scoped before retiring legacy access.** Workload CI
credentials must not be able to read `terraform/platform/access.tfstate`, its
S3 lock file or historical versions. Scope dev and prod credentials to their own
state prefixes. Scope plan
credentials to reading state (planning uses `-lock=false`); apply credentials
also need the corresponding state write/lock permissions. Shared AWS credentials
that can read every state would bypass the Proxmox separation. Backend
encryption alone does not provide this separation.
The [state-access root](../state-access/README.md) provisions these four scoped
AWS identities using an IAM administrator's credentials.

Verify normal plans and disposable guest lifecycle operations before revoking
the old shared credentials. Keep a working platform administrator available.
Then remove the propagated `PVEVMAdmin` ACLs on `/vms` for both
`proxmox-ro@pve` and `proxmox-ro@pve!proxmox-ro`, and retire the old
`proxmox-rw` CI identity/token after all workflows have moved. The local
`terraform@pve` administrator remains the bootstrap identity for this root until
a replacement platform administration mechanism is configured. Remove obsolete
CI secrets from the old environments and repository scope.

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
block. When the export includes `k8s-csi-dev`, it also checks that the token can
create and delete a 4 MiB volume on `k8s-dev` but not on `zfs` or `local-lvm`,
and cannot read prod guests or change memory. It prints no secrets.

The Talos module's `removed` block stops managing pre-RBAC boot media without
deleting it. The next dev Talos apply creates new media in `dev-images` and
updates CD-ROM references; review that saved plan normally. Do not reintroduce
the old ISO resource or grant dev permission to delete shared images.
