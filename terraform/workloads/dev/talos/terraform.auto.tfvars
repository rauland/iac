# Pinned versions for the fresh dev cluster rebuild.
cluster_name       = "dev"
cluster_endpoint   = "https://10.0.0.50:6443"
bootstrap_node     = "dev-cp-01"
talos_version      = "v1.14.3"
kubernetes_version = "v1.37.1"
dns_servers        = ["10.0.0.1"]

# Served by terraform/platform/cluster-oidc, so AWS trusts the cluster's
# service account tokens; see the Talos module README.
service_account_issuer = "https://rauland-homelab-oidc.s3.ap-southeast-2.amazonaws.com/dev"

# These api_address values require matching DHCP reservations before the ISO boots.
# MACs below are examples: reserve these addresses on your DHCP server or replace
# both MACs and addresses with your own reservations. No cloud-init is used.
talos_nodes = {
  dev-cp-01 = {
    node_name    = "dev-cp-01"
    node_type    = "controlplane"
    pve_node     = "pve"
    api_address  = "10.0.0.50"
    mac_address  = "02:00:00:00:50:01"
    ipv4_address = "10.0.0.50/24"
    ipv4_gateway = "10.0.0.1"
  }
  dev-worker-01 = {
    api_address  = "10.0.0.51"
    mac_address  = "02:00:00:00:50:02"
    node_name    = "dev-worker-01"
    node_type    = "worker"
    pve_node     = "pve"
    ipv4_address = "dhcp"
  }
  dev-worker-02 = {
    api_address  = "10.0.0.52"
    mac_address  = "02:00:00:00:50:03"
    node_name    = "dev-worker-02"
    node_type    = "worker"
    pve_node     = "pve"
    ipv4_address = "dhcp"
  }
}
