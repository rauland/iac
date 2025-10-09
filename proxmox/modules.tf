module "factory" {
  source = "./modules/factory"
  providers = {
    talos = talos
  }
}

module "talos" {
  source        = "./modules/talos"
  pve_nodes     = var.pve_nodes
  iso_url       = module.factory.installer_iso_url
  talos_configs = var.talos_configs
  talos_nodes   = var.talos_nodes
  providers = {
    proxmox = proxmox
  }
  depends_on = [module.factory]
}
  