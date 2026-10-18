mock_provider "proxmox" {
  mock_data "proxmox_file" {
    defaults = {
      id = "local:import/test.qcow2"
    }
  }
}

variables {
  pool_id         = "dev"
  ssh_public_keys = ["ssh-ed25519 AAAA"]
  vm_config = {
    vm_name            = "podman"
    node_name          = "pve"
    cpu                = 2
    memory             = 4096
    tags               = ["common", "sandbox", "podman"]
    image_datastore_id = "local"
    image_file_name    = "AlmaLinux-10-GenericCloud-latest.x86_64.qcow2"
  }
}

run "final_configuration_keeps_tags" {
  command = plan
  assert {
    condition     = proxmox_virtual_environment_vm.node.tags == tolist(["common", "sandbox", "podman"])
    error_message = "The final VM configuration must retain its declared tags."
  }
}

run "new_guest_defers_tags_and_retains_pool" {
  command = plan
  variables {
    deferred_vm_tags = ["pve/podman"]
  }
  assert {
    condition     = length(proxmox_virtual_environment_vm.node.tags) == 0 && proxmox_virtual_environment_vm.node.pool_id == "dev"
    error_message = "Create the selected guest in its pool without submitting tags."
  }
}

run "other_identity_is_not_deferred" {
  command = plan
  variables {
    deferred_vm_tags = ["other/podman", "pve/other"]
  }
  assert {
    condition     = contains(proxmox_virtual_environment_vm.node.tags, "sandbox")
    error_message = "Deferral must match the exact node and VM name."
  }
}
