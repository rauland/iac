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
  value = module.cluster.talos_controlpane_configuration
  sensitive = true
}

output "talos_worker_configuration" {
  value = module.cluster.talos_worker_configuration
  sensitive = true
}

resource "local_file" "worker_configuration" {
  filename = "debug.txt"
  content  = module.cluster.talos_worker_configuration
}

resource "local_file" "talosconfig" {
  filename = "talosconfig"
  content  = module.cluster.talos_client_configuration
}
