module "virtual_machine" {
  source          = "../../../modules/virtual-machine"
  pool_id         = "dev"
  ssh_public_keys = [file("${path.root}/../../../../ssh/public_keys/dev/ansible-ci.pub")]

  providers = {
    proxmox = proxmox
  }

  vm_config = {
    vm_name            = "vault"
    node_name          = "pve"
    tags               = ["common", "vault", "dev"]
    cpu                = 2
    memory             = 4096
    image_datastore_id = "local"
    image_file_name    = "AlmaLinux-10-GenericCloud-latest.x86_64.qcow2"
  }
}
