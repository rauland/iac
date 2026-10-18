module "virtual_machine" {
  source   = "../../../modules/virtual-machine"
  for_each = var.vms

  providers = {
    proxmox = proxmox
  }

  vm_config        = each.value
  deferred_vm_tags = var.deferred_vm_tags
  pool_id          = "dev"
  ssh_public_keys  = [file("${path.root}/../../../../ssh/public_keys/dev/ansible-ci.pub")]
}
