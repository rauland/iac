resource "proxmox_virtual_environment_vm" "node" {
  name      = var.vm_config.vm_name
  tags      = var.vm_config.tags
  node_name = var.vm_config.node_name

  agent {
    enabled = var.vm_config.agent_enabled
  }
  migrate     = true
  description = var.vm_config.description
  machine     = var.vm_config.machine
  bios        = var.vm_config.bios

  stop_on_destroy = var.vm_config.stop_on_destroy

  lifecycle {
    ignore_changes = [
      disk[0].file_id,
      description,
      initialization
    ]
  }

  cpu {
    cores = var.vm_config.cpu
    type  = "host"
  }

  memory {
    dedicated = var.vm_config.memory
  }

  efi_disk {
    datastore_id = var.vm_config.efi_disk_datastore_id
    type         = var.vm_config.efi_disk_type
  }

  disk {
    datastore_id = var.vm_config.disk_datastore_id
    import_from  = data.proxmox_file.iso.id
    interface    = var.vm_config.disk_interface
    iothread     = true
    discard      = "on"
    size         = var.vm_config.disk_size
  }

  initialization {
    ip_config {
      ipv4 {
        address = var.vm_config.ip_config_ipv4_address
      }
    }

    user_account {
      username = var.vm_config.user_account_username
      keys = [data.local_file.ssh_public_key.content]
    }
  }

  network_device {
    bridge = var.vm_config.network_device_bridge
  }
}
