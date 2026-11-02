# Pinned versions for the prod cluster. Keep them in step with dev, which
# receives Talos and Kubernetes changes first.
cluster_name       = "prod"
cluster_endpoint   = "https://10.0.0.53:6443"
bootstrap_node     = "prod-cp-01"
talos_version      = "v1.14.5"
kubernetes_version = "v1.37.1"
dns_servers        = ["10.0.0.1"]

# The NVIDIA extensions must not go in this cluster-wide list: the container
# toolkit adds boot services that wait for an NVIDIA GPU, so every node without
# one stays in the Booting stage. They belong only to the GPU node's image.
system_extensions = ["qemu-guest-agent"]

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
  # The GPU node: the Quadro P2200 through the gpu-p2200 mapping from
  # platform/access, and the NVIDIA driver in this node's image only. The
  # P2200 is Pascal, which only the proprietary LTS (580) branch still
  # supports. The container toolkit waits for the GPU at boot, so the device
  # must be attached (VM stopped and started) before the node is upgraded to
  # this image. See the Talos module README.
  prod-worker-02 = {
    node_name         = "prod-worker-02"
    node_type         = "worker"
    pve_node          = "pve"
    api_address       = "10.0.0.55"
    mac_address       = "02:00:00:00:53:03"
    ipv4_address      = "dhcp"
    cpu               = 4
    memory            = 16384
    disk_size         = 64
    pci_devices       = [{ mapping = "gpu-p2200" }]
    system_extensions = ["nonfree-kmod-nvidia-lts", "nvidia-container-toolkit-lts"]
    config_patches = [
      <<-EOT
      machine:
        kernel:
          modules:
            - name: nvidia
            - name: nvidia_uvm
            - name: nvidia_drm
            - name: nvidia_modeset
        sysctls:
          net.core.bpf_jit_harden: "1"
      ---
      # Merges into the node's KubeNodeConfig. NVIDIA's device plugin and the
      # nvidia RuntimeClass schedule on this label.
      apiVersion: v1alpha1
      kind: KubeNodeConfig
      labels:
        nvidia.com/gpu.present: "true"
      EOT
    ]
  }
}
