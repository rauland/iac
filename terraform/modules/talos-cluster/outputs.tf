output "schematic_id" {
  value = talos_image_factory_schematic.this.id
}

output "installer_iso_url" {
  value = data.talos_image_factory_urls.this.urls.iso_secureboot
}

output "installer_image" {
  value = data.talos_image_factory_urls.this.urls.installer_secureboot
}

output "node_addresses" {
  value = { for key, node in var.talos_nodes : key => node.api_address }
}

output "talosconfig" {
  description = "Talos administrator configuration. Retrieve deliberately with terraform output -raw; do not upload as a public artifact."
  value       = data.talos_client_configuration.this.talos_config
  sensitive   = true
}

output "kubeconfig" {
  description = "Kubernetes administrator configuration, available after cluster health checks pass."
  value       = talos_cluster_kubeconfig.this.kubeconfig_raw
  sensitive   = true
}

output "upgrade_inventory" {
  description = "Non-secret node lists and installer image for the Talos upgrade workflow."
  value = {
    talos_version   = var.talos_version
    installer_image = data.talos_image_factory_urls.this.urls.installer_secureboot
    control_planes  = [for key in sort(keys(var.talos_nodes)) : var.talos_nodes[key].api_address if var.talos_nodes[key].node_type == "controlplane"]
    workers         = [for key in sort(keys(var.talos_nodes)) : var.talos_nodes[key].api_address if var.talos_nodes[key].node_type == "worker"]
  }
}

output "kubernetes_client_configuration" {
  description = "Kubernetes API host and base64-encoded administrator certificates, for providers in other roots."
  value       = talos_cluster_kubeconfig.this.kubernetes_client_configuration
  sensitive   = true
}
