module "vm" {
  for_each = var.vms
  source   = "../../modules/vm"

  providers = {
    proxmox = proxmox
  }

  vm_name   = each.key
  node_name = each.value.node_name
  tags      = each.value.tags

}
