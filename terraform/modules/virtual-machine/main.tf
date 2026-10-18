# CI defers tags on new guests until Proxmox has assigned their pool ACLs.
resource "proxmox_virtual_environment_vm" "node" {
  name      = var.vm_config.vm_name
  tags      = contains(var.deferred_vm_tags, "${var.vm_config.node_name}/${var.vm_config.vm_name}") ? [] : var.vm_config.tags
  node_name = var.vm_config.node_name
  pool_id   = var.pool_id

  agent {
    enabled = var.vm_config.agent_enabled
  }
  migrate     = true
  description = var.vm_config.description
  machine     = var.vm_config.machine
  bios        = var.vm_config.bios

  stop_on_destroy = var.vm_config.stop_on_destroy

  lifecycle {
    replace_triggered_by = [terraform_data.bootstrap.input]
    precondition {
      condition     = !local.seed_enabled || (var.vm_config.agent_enabled && startswith(var.vm_config.image_file_name, "AlmaLinux-10-"))
      error_message = "API seed enrollment requires an AlmaLinux 10 image with the guest agent enabled."
    }
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
    import_from  = data.proxmox_file.image.id
    interface    = var.vm_config.disk_interface
    iothread     = true
    discard      = "on"
    size         = var.vm_config.disk_size
  }

  dynamic "initialization" {
    for_each = local.seed_enabled ? [] : [true]
    content {
      ip_config {
        ipv4 {
          address = var.vm_config.ip_config_ipv4_address
          gateway = var.vm_config.ip_config_ipv4_gateway
        }
      }
      user_account {
        username = var.vm_config.user_account_username
        keys     = [for key in var.ssh_public_keys : trimspace(key)]
      }
    }
  }

  dynamic "cdrom" {
    for_each = local.seed_enabled ? [true] : []
    content {
      file_id   = proxmox_virtual_environment_file.seed[0].id
      interface = "ide2"
    }
  }

  boot_order = local.seed_enabled ? [var.vm_config.disk_interface] : null

  network_device {
    bridge = var.vm_config.network_device_bridge
  }
}
