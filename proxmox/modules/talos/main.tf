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
    user_data_file_id = proxmox_virtual_environment_file.talos_configs["${each.value.pve_node}-${each.value.node_type}"].id
  }

  network_device {
    bridge = "vmbr0"
  }
}

resource "proxmox_virtual_environment_file" "talos_configs" {
  for_each = {
    for key in flatten([
      for node in var.pve_nodes : [
        for config_name, config_path in var.talos_configs :
    "${node}-${config_name}"]]) :
    key => {
      node_name = split("-", key)[0]
      node_type = split("-", key)[1]
      path      = var.talos_configs[split("-", key)[1]]
    }
  }

  content_type = "snippets"
  datastore_id = "local"
  node_name    = each.value.node_name

  source_file {
    path = each.value.path
  }
}

