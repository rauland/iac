output "schematic_id" {
  value = module.factory.schematic_id
}

output "installer_iso_url" {
  value = module.factory.installer_iso_url
}

output "installer_image" {
  value = module.factory.installer_image
}

output "talos_controlpane_configuration" {
  value = module.kube-config.talos_controlpane_configuration
  sensitive = true
}

output "talos_worker_configuration" {
  value = module.kube-config.talos_worker_configuration
  sensitive = true
}

resource "local_file" "debug_sensitive" {
  filename = "talosconfig"
  content  = module.kube-config.talos_client_configuration
}
