resource "talos_machine_bootstrap" "this" {
  node                 = local.bootstrap_address
  endpoint             = local.bootstrap_address
  client_configuration = talos_machine_secrets.this.client_configuration
  timeouts             = { create = "15m" }

  depends_on = [talos_machine_configuration_apply.node]
}

data "talos_cluster_health" "this" {
  client_configuration = talos_machine_secrets.this.client_configuration
  endpoints            = [for key, node in local.control_plane_nodes : node.api_address]
  control_plane_nodes  = [for key, node in local.control_plane_nodes : node.api_address]
  worker_nodes         = [for key, node in local.worker_nodes : node.api_address]
  timeouts             = { read = "15m" }

  depends_on = [talos_machine_bootstrap.this, talos_machine_configuration_apply.node]
}

resource "talos_cluster_kubeconfig" "this" {
  node                 = local.bootstrap_address
  endpoint             = local.bootstrap_address
  client_configuration = talos_machine_secrets.this.client_configuration

  depends_on = [data.talos_cluster_health.this]
}
