data "local_file" "ssh_public_key" {
  filename = var.vm_config.user_account_keys_file
}

data "proxmox_file" "iso" {
  node_name    = var.vm_config.node_name
  datastore_id = var.vm_config.iso_datastore_id
  content_type = "import"
  file_name    = var.vm_config.iso_file_name
}
