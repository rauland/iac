module "cloud_image" {
  source   = "../../modules/cloud-image"
  for_each = var.cloud_images

  providers = {
    proxmox = proxmox
  }

  url        = each.value.url
  node_names = each.value.node_names
}
