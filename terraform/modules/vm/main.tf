resource "proxmox_virtual_environment_vm" "ubuntu_vm" {
  name      = var.vm_name
  tags      = var.tags
  node_name = var.node_name

  agent {
    enabled = var.agent_enabled
  }
  migrate     = true
  description = var.description
  machine     = var.machine
  bios        = var.bios

  stop_on_destroy = var.stop_on_destroy

  lifecycle {
    ignore_changes = [
      disk[0].file_id,
      description,
      initialization
    ]
  }

  cpu {
    cores = var.cpu_cores
  }

  memory {
    dedicated = var.memory_dedicated
  }

  efi_disk {
    datastore_id = var.efi_disk_datastore_id
    type         = var.efi_disk_type
  }

  disk {
    datastore_id = var.disk_datastore_id
    file_id      = var.cloud_image_id
    interface    = var.disk_interface
    iothread     = true
    discard      = "on"
    size         = var.disk_size
  }

  initialization {
    ip_config {
      ipv4 {
        address = var.ip_config_ipv4_address
      }
    }

    user_data_file_id = var.user_data_file_id
  }

  network_device {
    bridge = var.network_device_bridge
  }
}
