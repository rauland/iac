resource "proxmox_virtual_environment_download_file" "ubuntu_cloud_image" {
  content_type   = "iso"
  datastore_id   = "local"
  node_name      = var.node_name
  url            = var.iso_url
  upload_timeout = 1200
}
