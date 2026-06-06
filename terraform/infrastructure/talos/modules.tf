module "talos_cluster" {
  source = "../../modules/talos-cluster"
  providers = {
    talos = talos
    proxmox = proxmox
  }
  pve_nodes = var.pve_nodes
  talos_nodes = var.talos_nodes
}
