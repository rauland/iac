module "virtual_machine" {
  source   = "../../../modules/virtual-machine"
  for_each = var.vms

  providers = {
    proxmox = proxmox
  }
  
  vm_config = each.value
}
