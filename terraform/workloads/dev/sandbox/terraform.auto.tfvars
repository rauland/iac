vms = {
  podman = {
    vm_name         = "podman"
    node_name       = "pve"
    tags            = ["dev", "common", "sandbox", "podman"]
    cpu             = 2
    memory          = 4096
    image_file_name = "AlmaLinux-10-GenericCloud-latest.x86_64.qcow2"
  }
}
