# Pinned versions for the prod cluster. Keep them in step with dev, which
# receives Talos and Kubernetes changes first.
cluster_name       = "prod"
cluster_endpoint   = "https://10.0.0.53:6443"
bootstrap_node     = "prod-cp-01"
talos_version      = "v1.14.3"
kubernetes_version = "v1.37.1"
dns_servers        = ["10.0.0.1"]

# Served by terraform/platform/cluster-oidc, so AWS trusts the cluster's
# service account tokens; see the Talos module README.
service_account_issuer = "https://rauland-homelab-oidc.s3.ap-southeast-2.amazonaws.com/prod"

# These api_address values require matching DHCP reservations before the ISO boots.
# No cloud-init is used.
talos_nodes = {
  prod-cp-01 = {
    node_name    = "prod-cp-01"
    node_type    = "controlplane"
    pve_node     = "pve"
    api_address  = "10.0.0.53"
    mac_address  = "02:00:00:00:53:01"
    ipv4_address = "10.0.0.53/24"
    ipv4_gateway = "10.0.0.1"
  }
  prod-worker-01 = {
    node_name    = "prod-worker-01"
    node_type    = "worker"
    pve_node     = "pve"
    api_address  = "10.0.0.54"
    mac_address  = "02:00:00:00:53:02"
    ipv4_address = "dhcp"
    cpu          = 4
    memory       = 16384
    disk_size    = 64
  }
  prod-worker-02 = {
    node_name    = "prod-worker-02"
    node_type    = "worker"
    pve_node     = "pve"
    api_address  = "10.0.0.55"
    mac_address  = "02:00:00:00:53:03"
    ipv4_address = "dhcp"
    cpu          = 4
    memory       = 16384
    disk_size    = 64
  }
}
