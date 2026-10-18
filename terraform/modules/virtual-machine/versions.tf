terraform {
  required_providers {
    external = {
      source  = "hashicorp/external"
      version = "2.4.2"
    }
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.109.0"
    }
  }
}
