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
  iso_datastore_id = each.value.iso_datastore_id
  iso_file_name    = each.value.iso_file_name
}
