vms = {
  k3s-01 = {
    node_name = "pve"
    tags      = ["managed", "k3s"]
    cpu       = 2
    memory    = 2048
  }
  k3s-02 = {
    node_name = "pve3"
    tags      = ["managed", "k3s"]
    cpu       = 2
    memory    = 2048
  }
  k3s-03 = {
    node_name = "pvenas"
    tags      = ["managed", "k3s"]
    cpu       = 2
    memory    = 2048
  }
}

cloud_images = {
  "noble-numbat" = {
    url = "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
  }
}
