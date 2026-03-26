module "cloud_image" {
  source   = "../../modules/cloud-image"
  for_each = var.cloud_images

  providers = {
    proxmox = proxmox
  }

  os_url = each.value.url
}
