module "factory" {
  source = "./modules/factory"
  providers = {
    talos = talos
  }
}

module "kube-config" {
  source          = "./modules/kube-config"
  installer_image = module.factory.installer_image
  providers = {
    talos = talos
  }
  depends_on = [module.factory]
}

module "talos" {
  source              = "./modules/talos"
  pve_nodes           = var.pve_nodes
  iso_url             = module.factory.installer_iso_url
  controlplane_config = module.kube-config.talos_controlpane_configuration
  worker_config       = module.kube-config.talos_worker_configuration
  talos_nodes         = var.talos_nodes
  providers = {
    proxmox = proxmox
  }
  depends_on = [module.kube-config]
}


