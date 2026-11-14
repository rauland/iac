resource "proxmox_virtual_environment_vm" "node" {
  for_each = var.talos_nodes

  name      = each.value.node_name
  node_name = each.value.pve_node
  vm_id     = each.value.vm_id
  pool_id   = var.pool_id
  # Explicitly empty, so tags set before they were removed are cleared too.
  tags                = []
  bios                = "ovmf"
  machine             = "q35"
  boot_order          = ["scsi0", "ide2"]
  hotplug             = "network,disk,usb"
  stop_on_destroy     = true
  reboot_after_update = false
  # One controller per disk, so each disk, the Proxmox CSI plugin's volumes
  # included, gets its own I/O thread. Takes effect when the VM is stopped and
  # started again.
  scsi_hardware = "virtio-scsi-single"

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

  # A balloon device as large as the VM's memory, so Proxmox shows the guest's
  # own memory use instead of the QEMU process's. Proxmox never reclaims memory
  # from it, so Talos keeps a fixed amount. Takes effect when the VM is stopped
  # and started again.
  memory {
    dedicated = each.value.memory
    floating  = each.value.memory
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

  # Host devices through Proxmox resource mappings, which an API token can use
  # with Mapping.Use; raw device IDs need root@pam. A VM with a passed-through
  # device cannot balloon or live-migrate, and a new device only appears after
  # the VM is stopped and started again, not after a reboot inside Talos. The
  # option ROM is hidden by default: Talos needs no firmware display, and the
  # VM's Secure Boot keys may not verify it.
  dynamic "hostpci" {
    for_each = each.value.pci_devices
    content {
      device  = "hostpci${hostpci.key}"
      mapping = hostpci.value.mapping
      pcie    = hostpci.value.pcie
      rombar  = hostpci.value.rombar
    }
  }

  # The Proxmox CSI plugin hot-plugs PersistentVolume disks into worker VMs.
  # Without this, an apply would detach them from running pods. The boot disk
  # is therefore not resized by Terraform; see README.md.
  lifecycle {
    ignore_changes = [disk]
  }
}
