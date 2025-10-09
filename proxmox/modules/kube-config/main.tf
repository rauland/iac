resource "talos_machine_secrets" "this" {}

data "talos_machine_configuration" "controlplane" {
  cluster_name     = "homelab"
  machine_type     = "controlplane"
  cluster_endpoint = "https://10.0.0.50:6443"
  machine_secrets  = talos_machine_secrets.this.machine_secrets
  config_patches = [
    yamlencode({
      machine = {
        install = {
          image = var.installer_image
        }
      }
    })
  ]
}

output "talos_controlpane_configuration" {
  value = data.talos_machine_configuration.controlplane.machine_configuration
}

data "talos_machine_configuration" "worker" {
  cluster_name     = "homelab"
  machine_type     = "worker"
  cluster_endpoint = "https://10.0.0.50:6443"
  machine_secrets  = talos_machine_secrets.this.machine_secrets
  config_patches = [
    yamlencode({
      machine = {
        install = {
          image = var.installer_image
        }
      }
    })
  ]
}

output "talos_worker_configuration" {
  value = data.talos_machine_configuration.worker.machine_configuration
}

data "talos_client_configuration" "this" {
  cluster_name         = "homelab"
  client_configuration = talos_machine_secrets.this.client_configuration
  nodes                = ["10.0.0.50"]
  endpoints            = ["10.0.0.50"]
}

output "talos_client_configuration" {
  value = data.talos_client_configuration.this.client_configuration
}
