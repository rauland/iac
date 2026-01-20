module "test-vm" {
  source = "../../modules/test-vm"
  providers = {
    proxmox = proxmox
  }
  vm_name = "test-vm"
}
