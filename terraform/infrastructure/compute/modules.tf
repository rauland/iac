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
  cloud_image_id    = try(data.terraform_remote_state.images.outputs.cloud_image[each.value.os].ids[each.value.node_name], null)
}
