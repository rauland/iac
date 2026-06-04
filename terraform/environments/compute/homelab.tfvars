vms = {
  k3s-01 = {
    node_name = "pve"
    tags      = ["managed", "k3s"]
    cpu       = 2
    memory    = 4096
  }
  k3s-02 = {
    node_name = "pve"
    tags      = ["managed", "k3s"]
    cpu       = 2
    memory    = 4096
  }
  k3s-03 = {
    node_name = "pve"
    tags      = ["managed", "k3s"]
    cpu       = 2
    memory    = 4096
  }
}

cloud_images = {
  "resolute-raccoon" = {
    url = "https://cloud-images.ubuntu.com/resolute/current/resolute-server-cloudimg-amd64.img"
  }
}
