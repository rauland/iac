terraform {
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.84.0"
    }
    talos = {
      source  = "siderolabs/talos"
      version = "0.9.0"
    }
  }
}