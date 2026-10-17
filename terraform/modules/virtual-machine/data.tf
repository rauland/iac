data "proxmox_file" "image" {
  node_name    = var.vm_config.node_name
  datastore_id = var.vm_config.image_datastore_id
  content_type = var.vm_config.image_content_type
  file_name    = var.vm_config.image_file_name
}
