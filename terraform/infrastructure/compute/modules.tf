module "vm" {
  source   = "../../modules/vm"
  for_each = var.vms

  providers = {
    proxmox = proxmox
  }

  vm_name           = each.key
  node_name         = each.value.node_name
  cpu_cores         = each.value.cpu
  memory_dedicated  = each.value.memory
  tags              = each.value.tags
  cloud_image_id    = data.terraform_remote_state.cloud_images.outputs.id
  user_data_file_id = module.cloud-init[each.key].user_data_cloud_config_id
}
