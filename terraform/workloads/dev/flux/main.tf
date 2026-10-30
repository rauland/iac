# Installs the Flux Operator and a FluxInstance that reconciles sync_path from
# Git. Kubernetes workloads are then changed through pull requests to that
# directory, not through Terraform. Apply the talos root first: this root reads
# the cluster's API credentials from its state.
data "terraform_remote_state" "talos" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = "terraform/dev/talos.tfstate"
  }
}

locals {
  cluster = data.terraform_remote_state.talos.outputs.kubernetes_client_configuration
}

provider "helm" {
  kubernetes = {
    host                   = local.cluster.host
    cluster_ca_certificate = base64decode(local.cluster.ca_certificate)
    client_certificate     = base64decode(local.cluster.client_certificate)
    client_key             = base64decode(local.cluster.client_key)
  }
}

resource "helm_release" "flux_operator" {
  name             = "flux-operator"
  namespace        = "flux-system"
  create_namespace = true
  repository       = "oci://ghcr.io/controlplaneio-fluxcd/charts"
  chart            = "flux-operator"
  version          = var.flux_operator_version
  wait             = true
}

resource "helm_release" "flux_instance" {
  name       = "flux"
  namespace  = "flux-system"
  repository = "oci://ghcr.io/controlplaneio-fluxcd/charts"
  chart      = "flux-instance"
  version    = var.flux_operator_version
  wait       = true

  values = [yamlencode({
    instance = {
      distribution = {
        version  = var.flux_version
        registry = "ghcr.io/fluxcd"
        # Pin the manifests to the operator release instead of :latest.
        artifact = "oci://ghcr.io/controlplaneio-fluxcd/flux-operator-manifests:v${var.flux_operator_version}"
      }
      components = ["source-controller", "kustomize-controller", "helm-controller", "notification-controller"]
      cluster = {
        type          = "kubernetes"
        networkPolicy = true
      }
      sync = {
        kind = "GitRepository"
        url  = var.sync_url
        ref  = var.sync_ref
        path = var.sync_path
      }
    }
  })]

  depends_on = [helm_release.flux_operator]
}
