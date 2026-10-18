# Virtual machines

Create cloud-image guests in an explicit Proxmox pool with environment-specific
SSH public keys. The caller supplies the VM name, node, hardware, image and tags
through `vm_config`. Sandbox and Vault use this module.

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
