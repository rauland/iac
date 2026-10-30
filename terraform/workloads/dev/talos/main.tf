# See ../../../modules/talos-cluster/README.md for lifecycle procedures.
module "talos_cluster" {
  source           = "../../../modules/talos-cluster"
  pool_id          = "dev"
  deferred_vm_tags = var.deferred_vm_tags
  iso_datastore_id = "dev-images"
  providers = {
    talos   = talos
    proxmox = proxmox
  }
  cluster_name       = var.cluster_name
  cluster_endpoint   = var.cluster_endpoint
  bootstrap_node     = var.bootstrap_node
  talos_version      = var.talos_version
  kubernetes_version = var.kubernetes_version
  talos_nodes        = var.talos_nodes
  dns_servers        = var.dns_servers
}

output "upgrade_inventory" {
  description = "Read by .github/workflows/talos-upgrade.yml."
  value       = module.talos_cluster.upgrade_inventory
}

output "talosconfig" {
  value     = module.talos_cluster.talosconfig
  sensitive = true
}

output "kubeconfig" {
  value     = module.talos_cluster.kubeconfig
  sensitive = true
}
