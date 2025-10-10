resource "proxmox_virtual_environment_download_file" "talos-nocloud-amd64" {
  for_each = toset(var.pve_nodes)

  content_type = "iso"
  datastore_id = "local"
  node_name    = each.key

  url = var.iso_url
}

resource "proxmox_virtual_environment_vm" "talos_vm" {
  for_each = { for node in var.talos_nodes : node.node_name => node }

  name      = each.key
  node_name = each.value.pve_node

  agent {
    enabled = true
  }

  stop_on_destroy = true

  cpu {
    cores = 2
    type  = "x86-64-v2-AES"
  }

  memory {
    dedicated = 2048
  }

  disk {
    datastore_id = "local-lvm"
    file_id      = proxmox_virtual_environment_download_file.talos-nocloud-amd64[each.value.pve_node].id
    interface    = "scsi0"
    discard      = "on"
    size         = 10
  }

  initialization {
    ip_config {
      ipv4 {
        address = each.value.ipv4_address
        gateway = each.value.ipv4_gateway != null ? each.value.ipv4_gateway : null
      }
    }
    user_data_file_id = each.value.node_type == "controlplane" ? proxmox_virtual_environment_file.controlplane_config[each.value.pve_node].id : proxmox_virtual_environment_file.worker_config[each.value.pve_node].id
  }

  network_device {
    bridge = "vmbr0"
  }
}

resource "proxmox_virtual_environment_file" "controlplane_config" {
  for_each = toset(var.pve_nodes)

  content_type = "snippets"
  datastore_id = "local"
  node_name    = each.key

  source_raw {
    file_name = "controlplane.yaml"
    data      = var.controlplane_config
  }
}

resource "proxmox_virtual_environment_file" "worker_config" {
  for_each = toset(var.pve_nodes)

  content_type = "snippets"
  datastore_id = "local"
  node_name    = each.key

  source_raw {
    file_name = "worker.yaml"
    data      = var.worker_config
  }
}

output "controlplane" {
  value = proxmox_virtual_environment_vm.talos_vm["controlplane-01"].id
}
