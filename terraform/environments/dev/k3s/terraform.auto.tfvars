vms = {
  k3s-01 = {
    vm_name   = "k3s-01"
    node_name = "pve"
    tags      = ["dev","managed", "k3s", "k3s-server"]
    cpu       = 2
    memory    = 4096
  }
  k3s-02 = {
    vm_name   = "k3s-02"
    node_name = "pve"
    tags      = ["dev","managed", "k3s", "k3s-agent"]
    cpu       = 2
    memory    = 4096
  }
  k3s-03 = {
    vm_name   = "k3s-03"
    node_name = "pve"
    tags      = ["dev","managed", "k3s", "k3s-agent"]
    cpu       = 2
    memory    = 4096
  }
}
