module "virtual_machine" {
  source = "../../../modules/virtual-machine"

  providers = {
    proxmox = proxmox
  }

  vm_config = {
    vm_name            = "vault"
    node_name          = "pve"
    tags               = ["managed", "vault", "dev"]
    cpu                = 2
    memory             = 4096
    image_datastore_id = "local"
    image_file_name    = "AlmaLinux-10-GenericCloud-latest.x86_64.qcow2"
  }
}
