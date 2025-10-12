module "factory" {
  source = "./modules/factory"
  providers = {
    talos = talos
  }
}

module "cluster" {
  source          = "./modules/cluster"
  installer_image = module.factory.installer_image
  providers = {
    talos = talos
  }
  depends_on = [module.factory]
}

module "nodes" {
  source              = "./modules/nodes"
  pve_nodes           = var.pve_nodes
  iso_url             = module.factory.installer_iso_url
  controlplane_config = module.cluster.talos_controlpane_configuration
  worker_config       = module.cluster.talos_worker_configuration
  talos_nodes         = var.talos_nodes
  providers = {
    proxmox = proxmox
  }
  depends_on = [module.cluster]
}

module "bootstrap" {
  source                = "./modules/bootstrap"
  talos_machine_secrets = module.cluster.talos_machine_secrets
  depends_on            = [module.nodes]
}
