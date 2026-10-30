# Virtual machines

Create cloud-image guests in an explicit Proxmox pool with environment-specific
SSH public keys. The caller supplies the VM name, node, hardware, image and tags
through `vm_config`. Sandbox uses this module.

## API-only cloud-init ISO

Sandbox opts into `cloud_init_iso = { datastore_id = "dev-images" }`. Other
callers retain Proxmox-generated initialization unless they explicitly opt in.
The ISO path is tested with AlmaLinux 10 GenericCloud, which already includes
cloud-init and qemu-guest-agent. It needs no SSH access to the Proxmox host and
does not use snippets. Install the pinned local builder dependency before
planning: `pip install -r scripts/requirements.txt` from this module directory.
CI installs it automatically.

The external data source builds a deterministic NoCloud ISO from the VM name,
automation account, environment public SSH keys, DHCP or static IPv4 settings,
and guest bootstrap scripts. Timestamps and timezone are fixed. The resulting
`.cloud-init/SHA256.iso` is uploaded through the HTTP API and attached at
`ide2`, replacing the generated initialization drive. Terraform boots the OS
disk explicitly. Seed changes replace an ISO-backed guest so first-boot
configuration is applied; changing only a seed on an existing disk would not
rerun cloud-init. The small `terraform_data.bootstrap` trigger has no guest-side
effect for callers using the original initialization path.

Cloud-init preserves the AlmaLinux agent's existing RPC policy and adds only
`guest-file-open`, `guest-file-read`, and `guest-file-close`. File-write and
guest-exec stay disabled. A root-owned boot service exports the public Ed25519
host key to `/run/ci-ssh-host-key.pub` with an agent-readable SELinux label.
The original public/private SSH key labels remain unchanged; SELinux stays
enforcing. The service runs after cloud-init under `cloud-init.target`, and
republishes the key after every reboot. Restart `ci-ssh-host-key.service` after
an intentional host-key rotation. No broad SELinux boolean is enabled.

The reviewed seed bytes travel inside the encrypted plan artifact. The manifest
checks their content-addressed paths and SHA256 values before the first apply.
Apply does not generate a replacement image from current inputs. Relative paths
allow another runner to use the same artifact. The tag-only follow-up sees the
same deterministic configuration and cannot change the ISO or other resources.

`dev-images` is dedicated storage, separate from shared `local` images. Only
dev apply receives `SeedPublisher` there: audit, ISO upload and
`Datastore.Allocate` for ISO deletion. Matching user/token grants preserve
privilege separation. Plan and inventory permissions are unchanged. Provision
the [access root](../../platform/access/README.md) before using this path.

For an existing guest, opt-in requires a reviewed replacement. The manual
[pinned-host workflow](../../../ssh/README.md#manual-onboarding-without-a-guest-agent) remains
available for existing or agentless guests.

## Pool-scoped creation and tags

Some Proxmox releases check create-time tags on `/vms/ID` before assigning the
new guest to its requested pool. A token with VM administration only on its
own pool therefore cannot create a tagged guest in one request. Keep the
pool-scoped ACLs; CI stages the tags using the same apply identity.

The shared planning helper first saves and renders the intended final plan.
For each VM create or replacement with tags, it records the exact resource
address, node, name, pool and desired tags. It then saves the infrastructure
plan with tags deferred only for those `node/name` selectors. Validation rejects
any other resource or output difference between the plans. The PR preview
shows the intended tags and explicitly identifies staged VM resources.

The encrypted artifact contains the executable infrastructure plan, its exact
provider lock file and `.tf-tags.json`. The manifest binds the target, commit,
run and attempt to hashes of the saved plan and provider selections. The apply
helper checks this identity before changing infrastructure.

After the infrastructure plan completes, the helper binds every staged guest
to its actual VM ID from state. It saves a follow-up plan with refresh disabled
and `deferred_vm_tags = []`. Before applying it, validation requires the exact
reviewed tags on the same node, VM ID, name and pool, with no other resource or
VM-setting changes. Provider-computed network observations may become unknown;
empty CPU flags can normalize from `null` to `[]`. Read-only data sources
already present in the reviewed plan, such as Talos health checks, may run again.
The configuration and ordinary input values must also match the reviewed plan,
including its Proxmox endpoint; the ephemeral API token may change from the
plan identity to the existing scoped apply identity.
The final state must contain the intended tags before Ansible or SSH enrollment
can proceed. Existing VM tag updates and destroy plans use their original saved
plan directly.

`deferred_vm_tags` is an internal staging input, defaulting to an empty set.
Leave it empty in normal configuration. The workload roots and Talos module
forward the same input. Do not permanently suppress tags in a tfvars file.

## Failure recovery

Infrastructure or tag failures stop the deployment before Ansible. Terraform
retains the created guests in their environment pool and state. Request a
fresh `auto` or `infrastructure` workflow run from the updated `main` branch:
an existing untagged guest is planned as a normal tag update, without needing
another creation or a state import. Configuration-only mode cannot repair a
missing service tag because inventory selection uses those tags.

An old workflow run keeps its original commit and plan format. Generate a new
plan after deploying this change; the apply helper rejects old artifacts that
lack the staging manifest. Do not add global VM permissions or manually edit
Terraform state to recover from this tag-check ordering issue.
