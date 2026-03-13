resource "proxmox_virtual_environment_download_file" "ubuntu_cloud_image" {
  content_type = "iso"
  datastore_id = "local"
  node_name    = "pve"
  url          = "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
  upload_timeout = 1200
}

resource "proxmox_virtual_environment_vm" "ubuntu_vm" {
  name            = var.vm_name
  tags            = ["managed"]
  node_name       = "pve"

  description = "Managed by Terraform"
  machine = "q35"
  bios = "ovmf"
  stop_on_destroy = true

  lifecycle {
    ignore_changes = [disk[0].file_id]
  }

  cpu {
    cores = 1
  }

  memory {
    dedicated = 1024
  }
  
  efi_disk {
    datastore_id = "local-lvm"
    type         = "4m"
  }

  disk {
    datastore_id = "local-lvm"
    file_id      = proxmox_virtual_environment_download_file.ubuntu_cloud_image.id
    interface    = "virtio0"
    iothread     = true
    discard      = "on"
    size         = 20
  }

  initialization {
    ip_config {
      ipv4 {
        address = "dhcp"
      }
    }

    user_account {
      username = "ansible"
      keys     = [trimspace(data.local_file.ssh_public_key.content)]
    }
  }

  network_device {
    bridge = "vmbr0"
  }
}
