resource "proxmox_virtual_environment_vm" "node" {
  for_each = var.talos_nodes

  name                = each.value.node_name
  node_name           = each.value.pve_node
  vm_id               = each.value.vm_id
  pool_id             = var.pool_id
  tags                = contains(var.deferred_vm_tags, "${each.value.pve_node}/${each.value.node_name}") ? [] : ["talos", var.cluster_name, each.value.node_type, var.pool_id]
  bios                = "ovmf"
  machine             = "q35"
  scsi_hardware       = "virtio-scsi-pci"
  boot_order          = ["scsi0", "ide2"]
  hotplug             = "network,disk,usb"
  stop_on_destroy     = true
  reboot_after_update = false

  agent {
    enabled = true
    # The ISO maintenance environment cannot provide an installed guest agent.
    # Waiting here would deadlock before Talos configuration can be applied.
    wait_for_ip {
      disabled = true
    }
  }

  cpu {
    cores = each.value.cpu
    type  = each.value.cpu_type
  }

  memory {
    dedicated = each.value.memory
  }

  efi_disk {
    datastore_id = coalesce(each.value.disk_datastore_id, var.disk_datastore_id)
    type         = "4m"
    # Start in UEFI setup mode so the Talos ISO can enroll its signing keys.
    pre_enrolled_keys = false
  }

  tpm_state {
    datastore_id = coalesce(each.value.disk_datastore_id, var.disk_datastore_id)
    version      = "v2.0"
  }

  disk {
    datastore_id = coalesce(each.value.disk_datastore_id, var.disk_datastore_id)
    interface    = "scsi0"
    file_format  = "raw"
    size         = each.value.disk_size
    discard      = "on"
  }

  cdrom {
    file_id   = proxmox_download_file.environment_iso[each.value.pve_node].id
    interface = "ide2"
  }

  network_device {
    bridge      = each.value.bridge
    model       = "virtio"
    mac_address = each.value.mac_address
    vlan_id     = each.value.vlan_id
  }

  serial_device {}

  # The Proxmox CSI plugin hot-plugs PersistentVolume disks into worker VMs.
  # Without this, an apply would detach them from running pods. The boot disk
  # is therefore not resized by Terraform; see README.md.
  lifecycle {
    ignore_changes = [disk]
  }
}
