module "virtual_machine" {
  source   = "../../../modules/virtual-machine"
  for_each = var.vms

  providers = {
    proxmox = proxmox
  }

  vm_config       = each.value
  pool_id         = "dev"
  ssh_public_keys = [file("${path.root}/../../../../ssh/public_keys/dev/ansible-ci.pub")]
}
