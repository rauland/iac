resource "proxmox_virtual_environment_download_file" "talos-nocloud-amd64" {
  content_type = "iso"
  datastore_id = "local"
  node_name    = "pve"

  url = "https://factory.talos.dev/image/ce4c980550dd2ab1b17bbf2b08801c7eb59418eafe8f279833297925d67c7515/v1.11.2/nocloud-amd64.iso"
}

resource "proxmox_virtual_environment_vm" "talos_vm" {
  name      = var.talos_node_name
  node_name = "pve"

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
    interface    = "virtio0"
    iothread     = true
    discard      = "on"
    size         = 10
  }

  initialization {
    ip_config {
      ipv4 {
        address = "dhcp"
      }
    }
  }

  network_device {
    bridge = "vmbr0"
  }
}
