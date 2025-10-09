module "talos" {
  source        = "./modules/talos"
  pve_nodes     = var.pve_nodes
  iso_url       = var.iso_url
  talos_configs = var.talos_configs
  talos_nodes   = var.talos_nodes
  providers = {
    proxmox = proxmox
  }
}
