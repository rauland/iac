# Kubernetes GitOps

Flux keeps each Talos cluster in step with a directory here. Terraform installs
Flux once; after that, Kubernetes changes go through pull requests to
`kubernetes/clusters/<environment>`. CI never applies these manifests: Flux
pulls `main` itself, about once a minute.

| Path | Reconciled by |
| --- | --- |
| [clusters/dev](clusters/dev/kustomization.yaml) | Flux on the dev Talos cluster |

## How Flux is installed

The [`dev/flux`](../terraform/workloads/dev/flux) Terraform root installs two
pinned Helm charts into `flux-system`:

- `flux-operator`, which manages the Flux controllers.
- `flux-instance`, a `FluxInstance` that runs the source, kustomize, helm and
  notification controllers and syncs `sync_path` from `sync_url` at `sync_ref`.

The repository is public, so Flux needs no Git credentials. A private fork needs
a pull secret in `flux-system` and `sync.pullSecret` set in the root. The root
reads the cluster's API address and administrator certificates from the
`kubernetes_client_configuration` output of the
[Talos root](../terraform/workloads/dev/talos)'s state, so it needs the
`TF_STATE_BUCKET` repository variable described in [setup](../docs/setup.md).

Upgrade Flux by changing `flux_operator_version` or `flux_version` in
[`terraform.auto.tfvars`](../terraform/workloads/dev/flux/terraform.auto.tfvars)
through a reviewed pull request.

## First deployment

The `dev/flux` root ships with a `.disabled` marker, because it needs an output
that the Talos root only exports after its next deployment.

1. Create the `TF_STATE_BUCKET` repository variable.
2. Deploy `dev/talos` from `main`, so its state has `kubernetes_client_configuration`.
3. Remove `terraform/workloads/dev/flux/.disabled` in a pull request. Merging it
   plans and, after approval, applies the Flux install.
4. Check the sync: `kubectl -n flux-system get fluxinstance flux` should report
   `Ready`, and `flux get kustomizations` lists `flux-system` as applied.

Apply the Talos root before the Flux root on a rebuilt cluster. Both plan in
parallel when one push changes both, so the Flux plan can only see the cluster
that existed before that push.

## Adding manifests

Add resources, or directories with their own `kustomization.yaml`, under
`resources` in the cluster's `kustomization.yaml`. CI runs
`kubectl kustomize` on every cluster directory, so a build error fails the
pull request before Flux ever sees it. Flux applies only after merge to `main`.

Talos enforces the Kubernetes `baseline` Pod Security standard by default, so
privileged workloads need a namespace labelled for it. Do not commit plain
Secrets: encrypted secret delivery is not configured yet.
