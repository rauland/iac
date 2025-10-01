pve_nodes = ["pve", "pve3"]
iso_url   = "https://factory.talos.dev/image/d3dc673627e9b94c6cd4122289aa52c2484cddb31017ae21b75309846e257d30/v1.11.2/nocloud-amd64.iso"

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
