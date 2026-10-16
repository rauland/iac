locals {
  control_plane_nodes = { for key, node in var.talos_nodes : key => node if node.node_type == "controlplane" }
  worker_nodes        = { for key, node in var.talos_nodes : key => node if node.node_type == "worker" }
  bootstrap_address   = try(var.talos_nodes[var.bootstrap_node].api_address, "")
  proxmox_nodes       = toset([for node in var.talos_nodes : node.pve_node])
}
