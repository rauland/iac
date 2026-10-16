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
      iso       = "https://factory.example/metal-amd64.iso"
      installer = "factory.example/installer/test:v1.14.3"
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
}
