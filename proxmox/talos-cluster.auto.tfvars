pve_nodes = ["pve", "pve3"]

talos_configs = {
  controlplane = "./_out/controlplane.yaml"
  worker       = "./_out/worker.yaml"
}

talos_nodes = {
  controlplane-01 = {
    node_name    = "controlplane-01"
    node_type    = "controlplane"
    pve_node     = "pve"
    ipv4_address = "10.0.0.50/24"
    ipv4_gateway = "10.0.0.1"
  }
  worker-01 = {
    node_name    = "worker-01"
    node_type    = "worker"
    pve_node     = "pve"
    ipv4_address = "dhcp"
  }
  worker-02 = {
    node_name    = "worker-02"
    node_type    = "worker"
    pve_node     = "pve3"
    ipv4_address = "dhcp"
  }
}
