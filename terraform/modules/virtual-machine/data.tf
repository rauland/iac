data "local_file" "ssh_public_key" {
  filename = var.vm_config.user_account_keys_file
}

data "proxmox_file" "image" {
  node_name    = var.vm_config.node_name
  datastore_id = var.vm_config.image_datastore_id
  content_type = var.vm_config.image_content_type
  file_name    = var.vm_config.image_file_name
}
