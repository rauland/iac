# Exercise the real Talos configuration generator and cryptographic secrets
# locally. Every operation that would call Proxmox, Image Factory, or a node is
# mocked or overridden; no network/infrastructure calls are permitted by design.
mock_provider "proxmox" {
  mock_resource "proxmox_download_file" {
    defaults = { id = "local:iso/test.iso" }
  }
}
provider "talos" {}

override_data {
  target = data.talos_image_factory_extensions_versions.this
  values = { extensions_info = [] }
}
override_resource {
  target = talos_image_factory_schematic.this
  values = { id = "test-schematic" }
}
override_data {
  target = data.talos_image_factory_urls.this
  values = {
    urls = {
      iso                  = "https://factory.example/metal-amd64.iso"
      installer            = "factory.example/installer/test:v1.14.3"
      iso_secureboot       = "https://factory.example/metal-amd64-secureboot.iso"
      installer_secureboot = "factory.example/installer-secureboot/test:v1.14.3"
    }
  }
}
override_resource {
  target = talos_machine_configuration_apply.node
}
override_resource {
  target = talos_machine_bootstrap.this
}
override_data {
  target = data.talos_cluster_health.this
}
override_resource {
  target = talos_cluster_kubeconfig.this
}

variables {
  pool_id            = "dev"
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

run "generate_valid_talos_configuration_offline" {
  command = apply
  assert {
    condition = alltrue([for node in data.talos_machine_configuration.node : (
      one([for doc in split("\n---\n", node.machine_configuration) : yamldecode(doc) if try(yamldecode(doc).kind, "") == "UnattendedInstallConfig"]).installer.image == "factory.example/installer-secureboot/test:v1.14.3"
    )])
    error_message = "The real Talos generator must select the Secure Boot installer for every node."
  }
  assert {
    condition = alltrue([for node in data.talos_machine_configuration.node : (
      length([for doc in split("\n---\n", node.machine_configuration) : doc if try(yamldecode(doc).kind, "") == "VolumeConfig"]) == 2 &&
      alltrue([for volume in [for doc in split("\n---\n", node.machine_configuration) : yamldecode(doc) if try(yamldecode(doc).kind, "") == "VolumeConfig"] : (
        contains(["STATE", "EPHEMERAL"], volume.name) &&
        volume.encryption.provider == "luks2" &&
        length(volume.encryption.keys) == 1 &&
        volume.encryption.keys[0].slot == 0 &&
        volume.encryption.keys[0].tpm.checkSecurebootStatusOnEnroll &&
        volume.encryption.keys[0].tpm.options.pcrs == [7] &&
        try(volume.encryption.keys[0].lockToState, false) == (volume.name == "EPHEMERAL")
      )])
    )])
    error_message = "Every node must encrypt STATE and EPHEMERAL with only a TPM key, require Secure Boot, bind PCR 7, and lock only EPHEMERAL to STATE."
  }
  assert {
    condition = (
      one([for doc in split("\n---\n", data.talos_machine_configuration.node["cp-01"].machine_configuration) : yamldecode(doc) if try(yamldecode(doc).kind, "") == "UnattendedInstallConfig"]).provisioning.diskSelector.match == "disk.dev_path == \"/dev/sda\"" &&
      one([for doc in split("\n---\n", data.talos_machine_configuration.node["cp-01"].machine_configuration) : yamldecode(doc) if try(yamldecode(doc).kind, "") == "ResolverConfig"]).nameservers[0].address == "192.0.2.1" &&
      one([for doc in split("\n---\n", data.talos_machine_configuration.node["cp-01"].machine_configuration) : yamldecode(doc) if try(yamldecode(doc).kind, "") == "KubeClusterConfig"]).endpoint == var.cluster_endpoint &&
      one([for doc in split("\n---\n", data.talos_machine_configuration.node["worker-01"].machine_configuration) : yamldecode(doc) if try(yamldecode(doc).version, "") == "v1alpha1"]).machine.type == "worker" &&
      one([for doc in split("\n---\n", data.talos_machine_configuration.node["cp-01"].machine_configuration) : yamldecode(doc) if try(yamldecode(doc).kind, "") == "HostnameConfig"]).hostname == "cp-01" &&
      !can(one([for doc in split("\n---\n", data.talos_machine_configuration.node["cp-01"].machine_configuration) : yamldecode(doc) if try(yamldecode(doc).kind, "") == "HostnameConfig"]).auto) &&
      !can(one([for doc in split("\n---\n", data.talos_machine_configuration.node["cp-01"].machine_configuration) : yamldecode(doc) if try(yamldecode(doc).version, "") == "v1alpha1"]).machine.install)
    )
    error_message = "The real Talos generator must accept the patches and preserve networking, endpoint, and node roles."
  }
  assert {
    condition = alltrue([for key, node in data.talos_machine_configuration.node : (
      one([for doc in split("\n---\n", node.machine_configuration) : yamldecode(doc) if try(yamldecode(doc).kind, "") == "KubeNodeConfig"]).labels["topology.kubernetes.io/region"] == "pve" &&
      one([for doc in split("\n---\n", node.machine_configuration) : yamldecode(doc) if try(yamldecode(doc).kind, "") == "KubeNodeConfig"]).labels["topology.kubernetes.io/zone"] == var.talos_nodes[key].pve_node &&
      !can(one([for doc in split("\n---\n", node.machine_configuration) : yamldecode(doc) if try(yamldecode(doc).version, "") == "v1alpha1"]).machine.nodeLabels)
    )])
    error_message = "Talos 1.14 nodes need the CSI region and zone labels in KubeNodeConfig; nodes reject machine.nodeLabels alongside that document."
  }
  assert {
    condition     = one([for doc in split("\n---\n", data.talos_machine_configuration.node["cp-01"].machine_configuration) : yamldecode(doc) if try(yamldecode(doc).kind, "") == "KubeNodeConfig"]).labels["node-role.kubernetes.io/control-plane"] == ""
    error_message = "The topology labels must merge with, not replace, the generated control-plane role labels."
  }
}

run "generate_legacy_talos_configuration_offline" {
  command = apply
  variables {
    talos_version      = "v1.11.2"
    kubernetes_version = "v1.34.1"
  }
  assert {
    condition = alltrue([for node in data.talos_machine_configuration.node : (
      one([for doc in split("\n---\n", node.machine_configuration) : yamldecode(doc) if try(yamldecode(doc).version, "") == "v1alpha1"]).machine.install.image == "factory.example/installer-secureboot/test:v1.14.3" &&
      length([for doc in split("\n---\n", node.machine_configuration) : doc if try(yamldecode(doc).kind, "") == "VolumeConfig"]) == 2
    )])
    error_message = "The legacy machine configuration layout must also use the Secure Boot installer and accept both encrypted system volumes."
  }
  assert {
    condition = alltrue([for key, node in data.talos_machine_configuration.node : (
      one([for doc in split("\n---\n", node.machine_configuration) : yamldecode(doc) if try(yamldecode(doc).version, "") == "v1alpha1"]).machine.nodeLabels["topology.kubernetes.io/zone"] == var.talos_nodes[key].pve_node &&
      length([for doc in split("\n---\n", node.machine_configuration) : doc if try(yamldecode(doc).kind, "") == "KubeNodeConfig"]) == 0
    )])
    error_message = "Talos releases before 1.14 take the CSI topology labels in machine.nodeLabels."
  }
}

run "public_service_account_issuer_on_control_planes_only" {
  command = apply
  variables {
    service_account_issuer = "https://issuer.example/test-cluster"
  }

  assert {
    condition = (
      one([for doc in split("\n---\n", data.talos_machine_configuration.node["cp-01"].machine_configuration) : yamldecode(doc) if try(yamldecode(doc).kind, "") == "KubeAPIServerConfig"]).extraArgs["service-account-issuer"] == ["https://issuer.example/test-cluster", "https://192.0.2.10:6443"] &&
      one([for doc in split("\n---\n", data.talos_machine_configuration.node["cp-01"].machine_configuration) : yamldecode(doc) if try(yamldecode(doc).kind, "") == "KubeAPIServerConfig"]).extraArgs["api-audiences"] == "https://192.0.2.10:6443"
    )
    error_message = "Control planes sign with the public issuer, still accept the old one, and keep the token audience."
  }
  assert {
    # Talos 1.14 nodes reject .cluster.apiServer next to KubeAPIServerConfig.
    condition     = try(yamldecode(split("\n---\n", data.talos_machine_configuration.node["cp-01"].machine_configuration)[0]).cluster.apiServer, null) == null
    error_message = "The API server is configured only through its own document on Talos 1.14."
  }
  assert {
    condition     = !strcontains(data.talos_machine_configuration.node["worker-01"].machine_configuration, "issuer.example")
    error_message = "Workers do not run the API server and get no issuer settings."
  }
}
