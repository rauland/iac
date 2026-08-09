module "cloud_image" {
  source   = "../../modules/cloud-image"
  for_each = var.cloud_images

  providers = {
    proxmox = proxmox
  }

  os_url    = each.value.url
  file_name = each.value.file_name
}

module "virtual_machine" {
  source   = "../../modules/virtual-machine"
  for_each = var.vms

  providers = {
    proxmox = proxmox
  }

  vm_name          = each.key
  node_name        = each.value.node_name
  cpu_cores        = each.value.cpu
  memory_dedicated = each.value.memory
  tags             = each.value.tags
  cloud_image_id   = module.cloud_image[each.value.os].ids[each.value.node_name]
}
