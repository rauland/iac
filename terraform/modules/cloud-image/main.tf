resource "proxmox_download_file" "node" {
  for_each = toset(var.node_names)
  
  file_name      = var.file_name
  content_type   = var.content_type
  datastore_id   = var.datastore_id
  node_name      = each.key
  url            = var.url
  upload_timeout = var.upload_timeout
}
