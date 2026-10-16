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
