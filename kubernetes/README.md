# Kubernetes GitOps

Flux keeps each Talos cluster in step with a directory here. Terraform installs
Flux once; after that, Kubernetes changes go through pull requests to
`kubernetes/clusters/<environment>`. CI never applies these manifests: Flux
pulls `main` itself, about once a minute.

| Path | Reconciled by |
| --- | --- |
| [clusters/dev](clusters/dev/kustomization.yaml) | Flux on the dev Talos cluster |
| [clusters/prod](clusters/prod/kustomization.yaml) | Flux on the prod Talos cluster: the same infrastructure, with apps added once they have been tried in dev |
| [clusters/dev/infrastructure.yaml](clusters/dev/infrastructure.yaml) | Flux Kustomizations that install the shared infrastructure in order |
| [clusters/dev/apps.yaml](clusters/dev/apps.yaml) | One Flux Kustomization per app |
| [clusters/dev/podinfo](clusters/dev/podinfo) | Demo app whose UI message is a SOPS-encrypted Secret |
| [infrastructure](infrastructure) | MetalLB, Traefik, the Proxmox CSI plugin and VolSync, shared by every cluster |

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

Give each app its own directory under `kubernetes/clusters/<environment>` and
its own Flux Kustomization in the cluster's [`apps.yaml`](clusters/dev/apps.yaml),
pointing at that directory, with `dependsOn` for the infrastructure it uses and
SOPS decryption if it has Secrets. Each app can then be paused on its own with
`flux suspend kustomization <app>`, for example during a volume restore. The
root `flux-system` Kustomization cannot be paused: the Flux Operator resumes it.

CI runs `kubectl kustomize` on every directory with a `kustomization.yaml`, so
a build error fails the pull request before Flux ever sees it. Flux applies
only after merge to `main`.

To move existing objects from one Flux Kustomization to another, annotate them
first with `kustomize.toolkit.fluxcd.io/prune=disabled`; otherwise the old
Kustomization deletes them, namespace and volumes included, when it stops
listing them. Remove the annotation once the new Kustomization has applied
them.

Talos enforces the Kubernetes `baseline` Pod Security standard by default, so
privileged workloads need a namespace labelled for it.

### Apps in a private repository

The apps you run can live in a separate, private repository, keeping this one
a reusable platform. Each cluster's `homelab-apps.yaml` adds that repository as
a second Flux `GitRepository`, read over SSH with a **read-only deploy key**,
and a Kustomization that applies its `clusters/<environment>` directory. That
directory lists one Flux Kustomization per app, as `apps.yaml` does here.

- Give each cluster its own deploy key, so either can be revoked alone. Store
  the private half and GitHub's host keys as the SOPS-encrypted Secret
  `flux-system/homelab-apps-deploy-key` (`identity` and `known_hosts`).
- Use the same age keys in the private repository's `.sops.yaml`, so Flux
  decrypts its Secrets with the key it already holds.
- Apps there use this platform's storage, backups, certificates and ingress
  in the same way as the examples here.

## Load balancing and ingress

[MetalLB](https://metallb.io) gives LoadBalancer Services an address from the
cluster's pool and answers ARP for it from one node (layer 2 mode). Dev uses
`10.0.0.60`–`10.0.0.69`, which is outside the router's DHCP pool; see
[`metallb-pool`](clusters/dev/metallb-pool/pool.yaml). A Service can ask for a
fixed address with the `metallb.io/loadBalancerIPs` annotation. If a node fails,
another node takes over its addresses within a few seconds.

[Traefik](https://doc.traefik.io/traefik/) is the default IngressClass and owns
the first pool address, `10.0.0.60`, set as `ingress_ip` in
[`infrastructure.yaml`](clusters/dev/infrastructure.yaml). To expose an HTTP
app, add an `Ingress` with a host name, as
[podinfo](clusters/dev/podinfo/ingress.yaml) does, and point that name at the
ingress IP in DNS. Until DNS exists, test with a `Host` header:

```sh
curl -H 'Host: podinfo.dev.netkuki.com' http://10.0.0.60/
```

Only plain HTTP is configured; TLS certificates are not yet managed. Non-HTTP
apps use their own LoadBalancer Service instead of the ingress.

The three steps are separate Flux Kustomizations, each waiting for the last:
MetalLB installs its CRDs, the pool uses them, and Traefik then gets its
address. `flux get kustomizations` shows where a failed rollout stopped. Chart
versions are pinned in each `release.yaml`; upgrade them through a pull request.

## Persistent storage

The [Proxmox CSI plugin](https://github.com/sergelogvinov/proxmox-csi-plugin)
provides the default `proxmox` StorageClass. Each PersistentVolume is a Proxmox
disk on the cluster's dedicated storage (`k8s-dev` on the `nas/k8s-dev` ZFS
dataset), attached to the VM that runs the pod. Every node is on host `pve`, so
a volume follows its pod to any node. Volumes are `ReadWriteOnce`: use the
`Recreate` strategy, as [podinfo](clusters/dev/podinfo/deployment.yaml) does, so
the old pod releases the disk before the new one starts. Set `fsGroup` for
non-root containers so they can write to the volume.

Switching a running Deployment from `RollingUpdate` to `Recreate` fails the
`flux-system` dry-run with ``spec.strategy.rollingUpdate: Forbidden``, which
blocks every other change in the cluster. Server-side apply keeps the defaulted
`rollingUpdate` values, so remove them once before or after merging:

```sh
kubectl -n <namespace> patch deployment <name> --type=json -p \
  '[{"op":"remove","path":"/spec/strategy/rollingUpdate"},{"op":"replace","path":"/spec/strategy/type","value":"Recreate"}]'
```

New Deployments are unaffected.

The StorageClass uses `reclaimPolicy: Retain`, so deleting a
PersistentVolumeClaim, its namespace or the app that owns it never deletes the
disk: the PersistentVolume becomes `Released` and keeps its data. To reuse the
data, bind a new claim to that PersistentVolume. To free the space, delete the
PersistentVolume, then the disk on the Proxmox host:

```sh
kubectl get pv <pv> -o jsonpath='{.spec.csi.volumeHandle}'   # <region>/<node>/<storage>/<volume>
pvesm free <storage>:<volume>
```

A StorageClass's reclaim policy and parameters cannot be changed in place, so
Helm fails to upgrade one that already exists with different settings. Delete
the StorageClass (`kubectl delete storageclass proxmox`) and let Flux recreate
it; existing volumes are unaffected. Each existing PersistentVolume keeps the
policy it was created with, so set it too:
`kubectl patch pv <pv> -p '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}'`.

### Volume encryption

Both StorageClasses encrypt their volumes with LUKS on the node: the plugin
formats each new volume as LUKS, opens it before mounting, and the pod sees
only the decrypted filesystem. Proxmox and the ZFS pool hold only ciphertext,
so the host, its backups and disks that leave the house never see the data.

The passphrase is the `encryption-passphrase` key of the SOPS-encrypted Secret
`csi-proxmox/proxmox-csi-encryption`
([`encryption.sops.yaml`](clusters/dev/proxmox-csi/encryption.sops.yaml)). The
kubelet hands it to the plugin when it stages a volume, so volumes unlock on
their own after a reboot or when a pod moves to another node. A rebuilt cluster
gets the same Secret from Git and can open retained volumes.

Without the passphrase, every volume is unreadable; restic backups are
encrypted separately and still restore. Keep a copy outside the cluster. As an
administrator, create it in SSM and the Secret together, without the value
touching disk unencrypted:

```sh
(
  export AWS_PROFILE=admin
  file=kubernetes/clusters/dev/proxmox-csi/encryption.sops.yaml
  p=$(openssl rand -base64 48)
  aws ssm put-parameter --name /iac/admin/k8s-dev/CSI_ENCRYPTION_PASSPHRASE \
    --type SecureString --value "$p" >/dev/null &&
  printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: proxmox-csi-encryption\n  namespace: csi-proxmox\nstringData:\n  encryption-passphrase: %s\n' "$p" |
    sops --encrypt --filename-override "$file" --input-type yaml --output-type yaml /dev/stdin > "$file"
)
```

The parameter has no `--overwrite`: existing volumes keep the passphrase they
were formatted with, so replacing it locks them out. Encryption applies only to
volumes created after it is enabled. To encrypt an existing volume, back it up,
recreate its claim on the encrypted class and restore it; see
[restore a volume](../docs/backups.md#restore-a-volume).

The `proxmox-scratch` StorageClass deletes its disks with their claims. Use it
only for volumes that hold nothing worth keeping, such as VolSync's caches.

Volumes are backed up only when their app declares it: see
[Kubernetes volumes](../docs/backups.md#kubernetes-volumes) for opting a
volume in and restoring it.

The plugin uses the `k8s-csi-dev@pve` token from
[`platform/access`](../terraform/platform/access/README.md#kubernetes-volumes),
which can only create and delete disks on `k8s-dev`. Its config is the
SOPS-encrypted Secret [`config.sops.yaml`](clusters/dev/proxmox-csi/config.sops.yaml).
The `region` must match the Talos nodes' `topology.kubernetes.io/region` label
(`pve`). To create or rotate it, as an administrator, without the token
touching disk unencrypted:

```sh
secret=$(terraform -chdir=terraform/platform/access output -json automation_credentials |
  jq -r '."k8s-csi-dev".secret')
token_id='k8s-csi-dev@pve!ci'
cat <<YAML | sops --encrypt --filename-override kubernetes/clusters/dev/proxmox-csi/config.sops.yaml \
  --input-type yaml --output-type yaml /dev/stdin > kubernetes/clusters/dev/proxmox-csi/config.sops.yaml
apiVersion: v1
kind: Secret
metadata:
  name: proxmox-csi-plugin
  namespace: csi-proxmox
stringData:
  config.yaml: |
    clusters:
      - url: https://pve.netkuki.com:8006/api2/json
        insecure: false
        token_id: $token_id
        token_secret: $secret
        region: pve
YAML
unset secret token_id
```

The plugin is its own Flux Kustomization, `proxmox-csi`, which declares SOPS
decryption itself; only the root Kustomization gets it from the FluxInstance.

## TLS certificates

[cert-manager](https://cert-manager.io) issues one wildcard certificate per
cluster from Let's Encrypt, `*.<cluster_domain>` and the bare domain, and
Traefik serves it as its default certificate. Apps need no TLS configuration:
an Ingress for any name under the cluster's domain is served over HTTPS, and
Traefik redirects HTTP to HTTPS.

| Cluster | `cluster_domain` | Example app |
| --- | --- | --- |
| dev | `dev.<domain>` | `podinfo.dev.<domain>` |
| prod | `<domain>` | `<app>.<domain>` |

Let's Encrypt proves domain control through a DNS-01 challenge in Cloudflare,
so nothing needs to be reachable from the internet. cert-manager checks the
challenge record against public resolvers, because a LAN resolver that
answers for the domain itself would never see it. Each cluster's
`certificates` Flux Kustomization sets `cluster_domain` and `acme_issuer`, and
adds the Cloudflare token as a SOPS-encrypted Secret. Start with
`letsencrypt-staging`, whose untrusted certificates have generous rate limits,
and switch to `letsencrypt` once a staging certificate is issued.

Create a Cloudflare API token with only **Zone → DNS → Edit** on the zone, then
encrypt it into the cluster's Secret without it touching disk unencrypted:

```sh
cluster=dev
file=kubernetes/clusters/$cluster/certificates/cloudflare.sops.yaml
read -rs -p 'Cloudflare API token: ' token; echo
printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: cloudflare-api-token\n  namespace: cert-manager\nstringData:\n  api-token: %s\n' "$token" |
  sops --encrypt --filename-override "$file" --input-type yaml --output-type yaml /dev/stdin > "$file"
unset token
```

Check issuance with `kubectl -n traefik get certificate wildcard` and
`kubectl describe certificaterequest -n traefik`.

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

Add it to `resources` like any other manifest;
[podinfo](clusters/dev/podinfo) is a working example. Its message proves
decryption end to end:

```sh
kubectl get --raw /api/v1/namespaces/podinfo/services/podinfo:9898/proxy/ | jq -r .message
``` To change a value, edit it with
`sops kubernetes/clusters/dev/my-app/credentials.sops.yaml`, which needs the
private key (`SOPS_AGE_KEY_FILE`); without it, write a new file and encrypt it
again. CI fails a pull request with a plain `kind: Secret` file or an
unencrypted `*.sops.yaml` file, but check `git diff --staged` before
committing: a plaintext value that reaches a pushed commit stays in Git history
and must be rotated.

### Decryption key

The age private key is the SSM parameter `/iac/dev/flux/SOPS_AGE_KEY`. Only the
dev apply role can read it; plan roles, Terraform state and saved plans never
hold it. Before each `dev/flux` apply, the deploy job installs it as
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
