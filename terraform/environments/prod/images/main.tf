module "cloud_image" {
  source   = "../../../modules/cloud-image"
  for_each = var.cloud_images

  providers = {
    proxmox = proxmox
  }

  url          = each.value.url
  node_names   = each.value.node_names
  file_name    = each.key
  content_type = each.value.content_type
  datastore_id = each.value.datastore_id
}
