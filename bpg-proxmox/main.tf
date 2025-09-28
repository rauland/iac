provider "proxmox" {
  endpoint  = var.virtual_environment_endpoint
  api_token = var.virtual_environment_api_token

  # uncomment (unless on Windows...)
  tmp_dir = "/var/tmp"

  ssh {
    agent    = true
    username = var.virtual_environment_ssh_username
  }
}

module "test-vm" {
  source = "./modules/test-vm"
  vm_name = var.vm_name
  
  providers = {
    proxmox = proxmox
  }
}
