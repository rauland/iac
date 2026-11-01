# Deployments and operations

Use this guide to select deployment work, review plans and approvals, and recover
from failed runs. For initial configuration, follow the [setup guide](setup.md).

- [Deployment selection](#deployment-selection)
- [Manual modes](#manual-modes)
- [Main branch protection](#main-branch-protection)
- [Approval and saved plans](#approval-and-saved-plans)
- [VM tag staging](#vm-tag-staging)
- [Concurrency and networking](#concurrency-and-networking)

## Deployment selection

The [deployment workflow](../.github/workflows/terraform.yml) plans and applies
the Terraform roots that build the clusters: `talos` and `flux` per
environment. Workloads are Kubernetes manifests that Flux pulls from Git; CI
never applies them, and no job connects to a host over SSH (see the
[platform direction](decisions/0001-kubernetes-first.md)). It runs on every
pull request to `main`, every push to `main`, merge-queue validation, and
manual requests. Feature branches use the
same PR checks; they cannot deploy. The stable **CI** check runs without
infrastructure secrets and reports even for documentation-only pull requests.

| Change | Work selected |
| --- | --- |
| Workload Terraform files | Plan that enabled root; apply only if the plan has changes. |
| Shared Terraform modules or plan/apply helpers | Plan all enabled roots conservatively. |
| Kubernetes manifests | None in CI; Flux applies them after merge. |
| Documentation, tests, or pipeline implementation only | Run CI; no deployment. |

Administrator roots under `terraform/platform` are never planned or applied by
CI. Removed roots are never destroyed automatically: destroy them explicitly
before removing their configuration.

## Manual modes

Run the deployment workflow from `main`, choose an environment (`dev` or
`prod`), and choose `single` or `all` scope. Single scope also requires a
target; all scope selects enabled targets in the chosen environment.

| Mode | Behavior |
| --- | --- |
| `auto` | Plan the selected roots and apply their changes after approval. |
| `destroy` | Generate and apply an explicitly requested destroy plan after approval. |

## Main branch protection

The main ruleset requires a pull request, a successful **CI** result produced by
GitHub Actions, and an up-to-date branch. Force pushes and branch deletion are
blocked, with no bypass actors. The desired configuration is recorded in
[main-ruleset.json](../.github/policies/main-ruleset.json); enforcement lives in
GitHub repository settings. Required CI jobs cannot depend on deployment approval.

The ruleset requires zero approving PR reviews to support a solo maintainer;
PRs, passing checks, and resolving review conversations are still required.
This is separate from the mandatory production deployment review. If a team
joins the repository, increase the approving PR review count in the ruleset.

## Approval and saved plans

The [Proxmox access root](../terraform/platform/access/README.md) documents scoped
users, token export, and state IAM requirements. GitHub environments supply
credentials and enforce the following deployment policies:

| Environment | Access | Protection |
| --- | --- | --- |
| `proxmox-dev-plan` | Dev audit credentials plus refresh permissions | No required reviewers |
| `proxmox-prod-plan` | Prod audit credentials plus refresh permissions | Required human approval, including PR previews |
| `proxmox-dev-auto-apply` | Dev write credentials and plan decryption key | Automatic deployments from pushes to `main` only |
| `proxmox-dev-apply` | Dev write credentials for manual reconciliation, destroy, and state unlock | Required reviewers; `main` only |
| `proxmox-prod-apply` | Prod write credentials and plan decryption key | Required human approval; `main` only |

Required reviewers and branch restrictions must exist in GitHub environment
settings; referencing an environment in YAML alone does not require approval.
Production currently names the repository owner as required reviewer, allows
that human to approve their own initiated run, and disables administrator
bypasses. Plan approval and deployment approval remain separate.

Live plans are allowed only for same-repository PRs and trusted `main` runs.
Fork PRs and merge queues run the credential-free checks without live plans.
Production plan approval is not a required merge check. Write credentials and
plan decryption keys stay exclusively in deployment environments.

Terraform uses `-detailed-exitcode`: 0 means no changes, 2 means changes, and an
error fails the run. Each matrix target uploads its own non-secret result,
bound to the commit, workflow run, attempt, target, and destroy mode. The
preparation job validates every expected result and publishes a deployment
summary before any deployment approval is requested. Missing or mismatched
results fail closed. No-op targets do not create deployment jobs or request
deployment approval.

Same-repository PRs receive one deployment preview comment with the readable
Terraform plan for every selected target, including no-change plans. Later runs
update the comment and identify the PR commit and workflow run. Large plans are
truncated with a link to the full job logs. The same preview appears in the
workflow run summary; changes that select no roots explicitly say no plans
were needed. Fork PRs do not publish a comment.

Only changed plans from `main` are encrypted and uploaded together with their
provider lock file and a manifest bound to the plan, target, commit and run.
Apply executes the saved infrastructure plan. For newly created VMs, such as
Talos nodes, tags are deferred until pool assignment; see
[VM tag staging](#vm-tag-staging).

The Terraform API token remains ephemeral and is supplied by the job's selected
environment. Result artifacts contain routing flags,
commit/run identifiers, and the human-readable output of `terraform show
-no-color tfplan`, which hides values marked sensitive by Terraform. Raw JSON
plans are not published. Plan text and logs remain visible in this public
repository; saved plan archives are encrypted.

Artifacts are unique to each run attempt and target and expire after seven
days. If a plan becomes stale, an artifact expires, or a deployment fails,
rerun **all jobs** so the plan, result metadata, and approval summary match.
Automatic dev applies may delete or replace resources when an ordinary plan
contains those actions; explicit destroy approval is not a deletion filter on
normal plans. Terraform deployment jobs use version `1.15.8`.

## VM tag staging

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
plan identity to the existing scoped apply identity. Existing VM tag updates
and destroy plans use their original saved plan directly.

`deferred_vm_tags` is an internal staging input, defaulting to an empty set.
Leave it empty in normal configuration; the Talos module forwards it. Do not
permanently suppress tags in a tfvars file.

## Concurrency and networking

Each plan and deployment job joins the tailnet as its own ephemeral `tag:ci`
node through the [Tailscale action](../.github/actions/tailscale/action.yml) and
reaches `10.0.0.0/24` through the subnet router, so jobs for different targets
run in parallel. Plan and deployment jobs for the same environment and target
share an `iac-terraform-<environment>-<target>` concurrency group with
`cancel-in-progress: false`, so one root is never planned and applied at the
same time. GitHub may replace an older pending job in a group with a newer one;
missing plan results prevent partial runs from deploying. Rerun all jobs after
a cancellation. State unlock remains an explicit, approved recovery operation.
The [Talos upgrade workflow](../terraform/modules/talos-cluster/README.md#upgrade-workflow)
joins the same group as the Talos root, so OS and Kubernetes upgrades never
overlap a Talos plan or apply.
