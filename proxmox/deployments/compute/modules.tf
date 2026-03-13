module "test-vm" {
  source = "../../modules/vm"
  providers = {
    proxmox = proxmox
  }
  vm_name = "test-vm"
}
