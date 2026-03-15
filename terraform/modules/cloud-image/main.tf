resource "proxmox_virtual_environment_download_file" "cloud_image" {
  content_type   = "iso"
  datastore_id   = "local"
  node_name      = var.node_name
  url            = local.images[var.os].url
  upload_timeout = 1200
}
