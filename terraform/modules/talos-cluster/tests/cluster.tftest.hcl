mock_provider "proxmox" {
  mock_resource "proxmox_download_file" {
    defaults = {
      id = "local:iso/talos-test.iso"
    }
  }
}

mock_provider "talos" {
  override_during = plan

  mock_data "talos_image_factory_urls" {
    defaults = {
      urls = {
        iso                  = "https://factory.example/metal-amd64.iso"
        installer            = "factory.example/installer/test:v1.14.3"
        iso_secureboot       = "https://factory.example/metal-amd64-secureboot.iso"
        installer_secureboot = "factory.example/installer-secureboot/test:v1.14.3"
      }
    }
  }
}

variables {
  pool_id            = "dev"
  iso_datastore_id   = "dev-images"
  cluster_name       = "test-cluster"
  cluster_endpoint   = "https://192.0.2.10:6443"
  bootstrap_node     = "cp-01"
  talos_version      = "v1.14.3"
  kubernetes_version = "v1.37.1"
  dns_servers        = ["192.0.2.1"]
  talos_nodes = {
    cp-01 = {
      node_name    = "cp-01"
      node_type    = "controlplane"
      pve_node     = "pve-a"
      api_address  = "192.0.2.10"
      ipv4_address = "192.0.2.10/24"
      ipv4_gateway = "192.0.2.1"
    }
    worker-01 = {
      node_name   = "worker-01"
      node_type   = "worker"
      pve_node    = "pve-b"
      api_address = "192.0.2.11"
      cpu         = 4
      memory      = 8192
      disk_size   = 64
      bridge      = "vmbr1"
    }
  }
}

run "boot_and_configuration_contract" {
  command = apply

  assert {
    condition = (
      alltrue([for node in proxmox_virtual_environment_vm.node : node.pool_id == "dev"]) &&
      alltrue([for iso in proxmox_download_file.environment_iso : iso.datastore_id == "dev-images"])
    )
    error_message = "Keep every Talos VM and its boot media within the selected environment."
  }

  assert {
    condition = (
      proxmox_virtual_environment_vm.node["cp-01"].cdrom[0].file_id != null &&
      proxmox_virtual_environment_vm.node["cp-01"].disk[0].file_id == null &&
      proxmox_virtual_environment_vm.node["cp-01"].disk[0].import_from == null &&
      proxmox_virtual_environment_vm.node["cp-01"].boot_order == tolist(["scsi0", "ide2"])
    )
    error_message = "Boot the installer from a CD-ROM with a separate empty installation disk and disk-first boot order."
  }
  assert {
    condition     = proxmox_virtual_environment_vm.node["cp-01"].agent[0].wait_for_ip[0].disabled
    error_message = "Waiting for a guest agent before applying Talos configuration would deadlock installation."
  }
  assert {
    condition     = length(proxmox_download_file.environment_iso) == 2 && data.talos_image_factory_urls.this.platform == "metal"
    error_message = "Download metal ISO boot media to each Proxmox host used by the nodes."
  }
  assert {
    condition = alltrue([for node in proxmox_virtual_environment_vm.node : (
      node.bios == "ovmf" && node.machine == "q35" &&
      node.efi_disk[0].type == "4m" && !node.efi_disk[0].pre_enrolled_keys &&
      node.tpm_state[0].version == "v2.0" &&
      node.tpm_state[0].datastore_id == node.disk[0].datastore_id
    )])
    error_message = "Every node needs UEFI setup mode for Talos key enrollment and a persistent TPM 2.0 on its disk datastore."
  }
  assert {
    condition = (
      alltrue([for iso in proxmox_download_file.environment_iso : iso.url == "https://factory.example/metal-amd64-secureboot.iso" && endswith(iso.file_name, "-secureboot.iso")]) &&
      output.installer_iso_url == "https://factory.example/metal-amd64-secureboot.iso" &&
      output.installer_image == "factory.example/installer-secureboot/test:v1.14.3"
    )
    error_message = "Boot media and exported installation/upgrade images must use the Secure Boot variants."
  }
  assert {
    condition = (
      output.upgrade_inventory.installer_image == output.installer_image &&
      output.upgrade_inventory.talos_version == var.talos_version &&
      output.upgrade_inventory.control_planes == ["192.0.2.10"] &&
      output.upgrade_inventory.workers == ["192.0.2.11"]
    )
    error_message = "The upgrade workflow needs the Secure Boot installer and addresses split by node role."
  }
  assert {
    condition     = talos_machine_bootstrap.this.node == "192.0.2.10" && talos_machine_bootstrap.this.endpoint == "192.0.2.10"
    error_message = "Bootstrap must use the selected control plane rather than a hardcoded address."
  }
  assert {
    condition = (
      data.talos_machine_configuration.node["worker-01"].cluster_endpoint == var.cluster_endpoint &&
      data.talos_machine_configuration.node["cp-01"].talos_version == var.talos_version &&
      data.talos_machine_configuration.node["cp-01"].kubernetes_version == var.kubernetes_version &&
      yamldecode(data.talos_machine_configuration.node["cp-01"].config_patches[1]).provisioning.diskSelector.match == "disk.dev_path == \"/dev/sda\"" &&
      yamldecode(data.talos_machine_configuration.node["worker-01"].config_patches[0]).machine.network.interfaces[0].dhcp
    )
    error_message = "Node configurations must use explicit versions, the SCSI installation disk, and the requested networking."
  }
  assert {
    condition = (
      yamldecode(data.talos_machine_configuration.node["cp-01"].config_patches[0]).machine.network.interfaces[0].addresses[0] == "192.0.2.10/24" &&
      talos_machine_configuration_apply.node["worker-01"].node == "192.0.2.11" &&
      talos_machine_configuration_apply.node["cp-01"].apply_mode == "auto"
    )
    error_message = "Apply configuration to the reserved node address using a mode supported during initial installation."
  }
  assert {
    condition = (
      proxmox_virtual_environment_vm.node["worker-01"].cpu[0].cores == 4 &&
      proxmox_virtual_environment_vm.node["worker-01"].memory[0].dedicated == 8192 &&
      proxmox_virtual_environment_vm.node["worker-01"].disk[0].size == 64 &&
      proxmox_virtual_environment_vm.node["worker-01"].network_device[0].bridge == "vmbr1"
    )
    error_message = "Honor per-node VM sizing and network configuration."
  }
}

run "reject_worker_bootstrap" {
  command = plan
  variables {
    bootstrap_node = "worker-01"
  }
  expect_failures = [var.bootstrap_node]
}

run "vms_carry_no_tags" {
  command = plan
  assert {
    condition     = alltrue([for node in proxmox_virtual_environment_vm.node : node.tags == null || length(node.tags) == 0])
    error_message = "Pool-scoped tokens cannot set create-time tags, and nothing reads them; the pool and VM name identify each node."
  }
}

run "reject_unknown_bootstrap" {
  command = plan
  variables {
    bootstrap_node = "missing"
  }
  expect_failures = [var.bootstrap_node]
}

run "reject_unpinned_release" {
  command = plan
  variables {
    talos_version = "latest"
  }
  expect_failures = [var.talos_version]
}

run "reject_unreachable_static_address" {
  command = plan
  variables {
    talos_nodes = {
      cp-01 = {
        node_name    = "cp-01"
        node_type    = "controlplane"
        pve_node     = "pve-a"
        api_address  = "192.0.2.10"
        ipv4_address = "192.0.2.99/24"
        ipv4_gateway = "192.0.2.1"
      }
    }
  }
  expect_failures = [var.talos_nodes]
}

run "reject_static_network_without_dns" {
  command = plan
  variables {
    dns_servers = []
  }
  expect_failures = [var.dns_servers]
}
