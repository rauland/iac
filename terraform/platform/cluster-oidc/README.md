# Cluster OIDC discovery

This administrator-operated root lets AWS trust the service account tokens of
each Kubernetes cluster, so pods reach AWS with short-lived credentials instead
of stored access keys. It is excluded from automatic deployment discovery; CI
cannot plan or apply it.

AWS verifies a token by fetching its issuer's discovery document and signing
keys over public HTTPS. The clusters' API servers are not reachable from the
internet, so this root copies the two documents from each API server to a
public S3 bucket, and registers each cluster as an IAM identity provider.

## What it creates

| Resource | Notes |
| --- | --- |
| S3 bucket (`bucket_name`) | Serves `<cluster>/.well-known/openid-configuration` and `<cluster>/openid/v1/jwks` publicly, and nothing else. The documents hold only public keys. TLS only. |
| IAM OIDC identity provider per cluster | Issuer `https://<bucket>.s3.<region>.amazonaws.com/<cluster>`, audience `sts.amazonaws.com`. Roles that trust it are defined where they are used, such as [`platform/offsite-backup`](../offsite-backup/README.md). |

The provider alone grants nothing: a pod gets AWS access only through a role
whose trust policy names the provider, the audience and the pod's service
account.

## Prepare the cluster

Set the cluster's Talos root to sign tokens as the bucket's issuer, and let CI
apply it:

```hcl
service_account_issuer = "https://<bucket>.s3.<region>.amazonaws.com/<cluster>"
```

See [public service account issuer](../../modules/talos-cluster/README.md#public-service-account-issuer).
This root refuses to publish a cluster whose API server still reports another
issuer.

## Apply

Run from the repository root, on a machine that can reach the clusters' API
servers, after authenticating with the `admin` profile as described in
[state-access](../state-access/README.md#authenticate-with-temporary-administrator-credentials).
The root reads each cluster's administrator certificate from its Talos state:

```sh
(
  unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_SECURITY_TOKEN
  export AWS_PROFILE=admin
  aws sts get-caller-identity &&
  terraform -chdir=terraform/platform/cluster-oidc init \
    -backend-config=bucket=rauland-iac-homelab \
    -backend-config=region=ap-southeast-2 \
    -backend-config=key=terraform/platform/cluster-oidc.tfstate &&
  terraform -chdir=terraform/platform/cluster-oidc plan -out=tfplan \
    -var state_bucket=rauland-iac-homelab
)
```

Review the plan, then apply it with
`terraform -chdir=terraform/platform/cluster-oidc apply tfplan` in the same kind
of subshell. Bucket names are global, so a fork must set its own `bucket_name`.
If the account blocks public bucket policies account-wide, the bucket policy
is rejected; allow it for this bucket.

Apply again whenever a cluster's signing keys change, which happens only when
its Talos machine secrets are recreated, such as when the cluster is built from
scratch. Until then, AWS rejects the new cluster's tokens.

## Checks

Run `terraform validate` and the offline tests with `terraform test` from this
directory. The tests assert that the documents come from the API server, that
only they are public, and that a cluster still on its private issuer is refused.
