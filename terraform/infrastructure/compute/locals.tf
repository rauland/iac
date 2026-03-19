locals {
  cloud_images = toset([for vm in var.vms : "${vm.node_name}-${vm.os}"])
}