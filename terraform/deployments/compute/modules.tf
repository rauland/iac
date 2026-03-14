module "cloud_image" {
  source = "../../modules/cloud-image"
  
  providers = {
    proxmox = proxmox
  }
  node_name = "pve"
}

module "cloud-init" {
  source = "../../modules/cloud-init"
  for_each = var.vms

  providers = {
    proxmox = proxmox
  }

  node_name = each.value.node_name
  vm_name   = each.key
}

module "vm" {
  source   = "../../modules/vm"
  for_each = var.vms

  providers = {
    proxmox = proxmox
  }

  vm_name   = each.key
  node_name = each.value.node_name
  tags      = each.value.tags
  cloud_image_id = module.cloud_image.ubuntu_cloud_image_id
  user_data_file_id  = module.cloud-init[each.key].user_data_cloud_config_id
}
