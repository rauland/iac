resource "proxmox_virtual_environment_download_file" "cloud_image" {
  for_each = toset(data.proxmox_virtual_environment_nodes.nodes.names)

  content_type   = "iso"
  datastore_id   = "local"
  node_name      = each.key
  url            = var.os_url
  upload_timeout = 1200
}
