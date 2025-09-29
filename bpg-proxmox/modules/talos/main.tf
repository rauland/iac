resource "proxmox_virtual_environment_download_file" "talos-nocloud-amd64" {
  content_type = "iso"
  datastore_id = "local"
  node_name    = "pve"

  url = "https://factory.talos.dev/image/d3dc673627e9b94c6cd4122289aa52c2484cddb31017ae21b75309846e257d30/v1.11.2/nocloud-amd64.iso"
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
    file_id      = proxmox_virtual_environment_download_file.talos-nocloud-amd64.id
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
    user_data_file_id = proxmox_virtual_environment_file.talos_config[each.value.file_name].id
  }

  network_device {
    bridge = "vmbr0"
  }
}

resource "proxmox_virtual_environment_file" "talos_config" {
  for_each = var.talos_configs
  
  content_type = "snippets"
  datastore_id = "local"
  node_name    = "pve"

  source_file {
    path = each.value
  }
}
