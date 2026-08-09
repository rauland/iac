vms = {
  vault = {
    node_name = "pve"
    tags      = ["managed", "vault"]
    cpu       = 2
    memory    = 4096
    os        = "centos-10"
  }
}

cloud_images = {
  "centos-10" = {
    url = "https://cloud.centos.org/centos/10-stream/x86_64/images/CentOS-Stream-GenericCloud-x86_64-10-latest.x86_64.qcow2"
    file_name = "CentOS-Stream-GenericCloud-x86_64-10-latest.x86_64.img"
  }
}
