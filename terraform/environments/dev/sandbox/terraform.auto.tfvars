vms = {
  cockpit = {
    vm_name       = "cockpit"
    node_name     = "pve"
    tags          = ["managed", "cockpit"]
    cpu           = 2
    memory        = 4096
    iso_file_name = "AlmaLinux-10-GenericCloud-latest.x86_64.qcow2"
    agent_enabled = true
  }
  # ubuntu-test = {
  #   vm_name       = "ubuntu-test"
  #   node_name     = "pve"
  #   tags          = ["managed", "ubuntu"]
  #   cpu           = 2
  #   memory        = 4096
  #   iso_file_name = "resolute-server-cloudimg-amd64.img"
  # }
}
