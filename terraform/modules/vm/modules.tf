module "cloud_init" {
  source = "../cloud-init"

  providers = {
    proxmox = proxmox
  }

  node_name = var.node_name
  vm_name   = var.vm_name
}
