resource "talos_machine_bootstrap" "this" {
  node                 = "10.0.0.50"
  client_configuration = var.talos_machine_secrets
}

resource "talos_cluster_kubeconfig" "this" {
  depends_on = [
    talos_machine_bootstrap.this
  ]
  client_configuration = var.talos_machine_secrets
  node                 = "10.0.0.50"
}
output "kubeconfig" {
  value     = talos_cluster_kubeconfig.this.kubeconfig_raw
  sensitive = true
}
