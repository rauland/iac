mock_provider "proxmox" {
  mock_data "proxmox_file" {
    defaults = {
      id = "local:import/test.qcow2"
    }
  }
}
mock_provider "external" {
  mock_data "external" {
    defaults = {
      result = {
        path   = ".cloud-init/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.iso"
        sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      }
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

run "api_iso_preserves_bootstrap_and_avoids_generated_drive" {
  command = plan
  variables {
    cloud_init_iso = { datastore_id = "dev-images" }
  }
  assert {
    condition = (
      length(proxmox_virtual_environment_vm.node.initialization) == 0 &&
      proxmox_virtual_environment_vm.node.cdrom[0].interface == "ide2" &&
      proxmox_virtual_environment_vm.node.boot_order == tolist(["virtio0"]) &&
      proxmox_virtual_environment_file.seed[0].datastore_id == "dev-images" &&
      proxmox_virtual_environment_file.seed[0].content_type == "iso" &&
      !proxmox_virtual_environment_file.seed[0].overwrite
    )
    error_message = "Use an API-uploaded ISO with an explicit disk boot order, without a second initialization drive."
  }
  assert {
    condition = (
      local.seed_user_data.users[0].name == "ansible" &&
      local.seed_user_data.users[0].ssh_authorized_keys == ["ssh-ed25519 AAAA"] &&
      !local.seed_user_data.ssh_pwauth &&
      local.seed_network.ethernets.primary.dhcp4
    )
    error_message = "The ISO must retain the automation account, public key and DHCP bootstrap."
  }
}

run "legacy_guests_keep_generated_initialization" {
  command = plan
  assert {
    condition = (
      length(proxmox_virtual_environment_file.seed) == 0 &&
      length(proxmox_virtual_environment_vm.node.initialization) == 1 &&
      proxmox_virtual_environment_vm.node.initialization[0].user_account[0].username == "ansible"
    )
    error_message = "Existing callers must explicitly opt into the new ISO provisioning path."
  }
}

run "static_seed_preserves_address_and_gateway" {
  command = plan
  variables {
    cloud_init_iso = { datastore_id = "dev-images" }
    vm_config = {
      vm_name                = "podman"
      node_name              = "pve"
      cpu                    = 2
      memory                 = 4096
      image_datastore_id     = "local"
      image_file_name        = "AlmaLinux-10-GenericCloud-latest.x86_64.qcow2"
      ip_config_ipv4_address = "10.0.0.50/24"
      ip_config_ipv4_gateway = "10.0.0.1"
    }
  }
  assert {
    condition = (
      !local.seed_network.ethernets.primary.dhcp4 &&
      local.seed_network.ethernets.primary.addresses[0] == "10.0.0.50/24" &&
      local.seed_network.ethernets.primary.routes[0].via == "10.0.0.1"
    )
    error_message = "An ISO-backed static guest must retain its configured address and gateway."
  }
}
