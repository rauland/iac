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

## Checking the sync

`kubectl -n flux-system get fluxinstance flux` should report `Ready`, and
`flux get kustomizations` lists `flux-system` as applied.

Apply the Talos root before the Flux root on a rebuilt cluster. Both plan in
parallel when one push changes both, so the Flux plan can only see the cluster
that existed before that push.

## Adding manifests

Add resources, or directories with their own `kustomization.yaml`, under
`resources` in the cluster's `kustomization.yaml`. CI runs
`kubectl kustomize` on every cluster directory, so a build error fails the
pull request before Flux ever sees it. Flux applies only after merge to `main`.

Talos enforces the Kubernetes `baseline` Pod Security standard by default, so
privileged workloads need a namespace labelled for it.

## Secrets

Secrets are committed encrypted with [SOPS](https://getsops.io) and an age key.
Flux decrypts them in the cluster with the private key in `flux-system/sops-age`.
Only `data` and `stringData` are encrypted, so names, namespaces and labels
stay readable in review. Anyone can encrypt; only the cluster can decrypt.

To add one, write the Secret to a file ending in `.sops.yaml` and encrypt it in
place before committing. [`.sops.yaml`](../.sops.yaml) supplies the recipient:

```sh
sops --encrypt --in-place kubernetes/clusters/dev/my-app/credentials.sops.yaml
```

Add it to `resources` like any other manifest. To change a value, edit it with
`sops kubernetes/clusters/dev/my-app/credentials.sops.yaml`, which needs the
private key (`SOPS_AGE_KEY_FILE`); without it, write a new file and encrypt it
again. CI fails a pull request with a plain `kind: Secret` file or an
unencrypted `*.sops.yaml` file, but check `git diff --staged` before
committing: a plaintext value that reaches a pushed commit stays in Git history
and must be rotated.

### Decryption key

The age private key is the SSM parameter `/iac/dev/flux/SOPS_AGE_KEY`. Only the
dev apply role can read it; plan roles, Terraform state and saved plans never
hold it. After each `dev/flux` apply, the deploy job installs it as
`flux-system/sops-age` with
[`install-sops-key.sh`](../.github/scripts/install-sops-key.sh), which reads the
kubeconfig from the Talos root's state. A rebuilt cluster gets the key when Flux
is reinstalled.

To install or rotate it without a Flux change, run the script as an
administrator with the same inputs:

```sh
export AWS_PROFILE=admin TF_VAR_state_bucket=YOUR_STATE_BUCKET
SOPS_AGE_KEY=$(aws ssm get-parameter --with-decryption \
  --name /iac/dev/flux/SOPS_AGE_KEY --query Parameter.Value --output text) \
  bash .github/scripts/install-sops-key.sh dev
```

To rotate, generate a new pair with `age-keygen`, store the private key in SSM,
add the new public key to `.sops.yaml` alongside the old one, run
`sops updatekeys` on every `*.sops.yaml` file, install the new key, then remove
the old recipient. Keep a backup of the private key outside AWS: without it,
committed secrets cannot be decrypted.
