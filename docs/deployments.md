# Deployments and operations

Use this guide to select deployment work, review plans and approvals, and recover
from failed runs. For initial configuration, follow the [setup guide](setup.md).

- [Deployment selection](#deployment-selection)
- [Manual modes](#manual-modes)
- [Main branch protection](#main-branch-protection)
- [Approval and saved plans](#approval-and-saved-plans)
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
The apply job checks that manifest, then applies the saved plan unchanged.

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
