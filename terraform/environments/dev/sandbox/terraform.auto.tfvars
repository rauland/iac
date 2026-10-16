vms = {
  cockpit = {
    vm_name         = "cockpit"
    node_name       = "pve"
    tags            = ["dev", "managed", "sandbox", "cockpit"]
    cpu             = 2
    memory          = 4096
    image_file_name = "AlmaLinux-10-GenericCloud-latest.x86_64.qcow2"
  }
}
