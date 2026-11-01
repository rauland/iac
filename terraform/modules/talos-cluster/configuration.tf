locals {
  # Talos 1.14 generates dedicated install, hostname, resolver, and Kubernetes
  # node documents, and rejects the matching v1alpha1 fields alongside them.
  split_machine_config = tonumber(split(".", trimprefix(var.talos_version, "v"))[0]) > 1 || tonumber(split(".", trimprefix(var.talos_version, "v"))[1]) >= 14
  # The Proxmox CSI plugin places volumes by these labels; see README.md.
  topology_labels = {
    for key, node in var.talos_nodes : key => {
      "topology.kubernetes.io/region" = var.proxmox_region
      "topology.kubernetes.io/zone"   = node.pve_node
    }
  }
}

resource "talos_machine_secrets" "this" {
  talos_version = var.talos_version

  # Seed material belongs to the cluster lifetime, not an OS upgrade.
  lifecycle {
    ignore_changes = [talos_version]
  }
}

data "talos_machine_configuration" "node" {
  for_each = var.talos_nodes

  cluster_name       = var.cluster_name
  cluster_endpoint   = var.cluster_endpoint
  machine_type       = each.value.node_type
  machine_secrets    = talos_machine_secrets.this.machine_secrets
  talos_version      = var.talos_version
  kubernetes_version = var.kubernetes_version
  config_patches = concat([
    yamlencode({
      machine = merge({ for key, value in {
        install = {
          disk  = "/dev/sda"
          image = data.talos_image_factory_urls.this.urls.installer_secureboot
        }
        nodeLabels = local.topology_labels[each.key]
        } : key => value if !local.split_machine_config }, {
        network = merge({ for key, value in {
          hostname    = each.value.node_name
          nameservers = var.dns_servers
          } : key => value if !local.split_machine_config }, {
          interfaces = [{
            deviceSelector = { physical = true }
            dhcp           = each.value.ipv4_address == "dhcp"
            addresses      = each.value.ipv4_address == "dhcp" ? [] : [each.value.ipv4_address]
            routes         = each.value.ipv4_address == "dhcp" ? [] : [{ network = "0.0.0.0/0", gateway = each.value.ipv4_gateway }]
          }]
        })
      })
    })
    ], local.split_machine_config ? [
    yamlencode({
      apiVersion = "v1alpha1"
      kind       = "UnattendedInstallConfig"
      installer  = { image = data.talos_image_factory_urls.this.urls.installer_secureboot }
      provisioning = {
        diskSelector = { match = "disk.dev_path == \"/dev/sda\"" }
        wipe         = false
      }
    }),
    # Replace the generated automatic hostname before setting a static one.
    yamlencode({
      apiVersion = "v1alpha1"
      kind       = "HostnameConfig"
      "$patch"   = "delete"
    }),
    yamlencode({
      apiVersion = "v1alpha1"
      kind       = "HostnameConfig"
      hostname   = each.value.node_name
    }),
    yamlencode({
      apiVersion  = "v1alpha1"
      kind        = "ResolverConfig"
      nameservers = [for address in var.dns_servers : { address = address }]
    }),
    # Merges with the generated document's role labels.
    yamlencode({
      apiVersion = "v1alpha1"
      kind       = "KubeNodeConfig"
      labels     = local.topology_labels[each.key]
    })
    ] : [], [for volume in ["STATE", "EPHEMERAL"] : yamlencode({
      apiVersion = "v1alpha1"
      kind       = "VolumeConfig"
      name       = volume
      encryption = {
        provider = "luks2"
        keys = [merge({
          slot = 0
          tpm = {
            checkSecurebootStatusOnEnroll = true
            options                       = { pcrs = [7] }
          }
        }, volume == "EPHEMERAL" ? { lockToState = true } : {})]
      }
    })], each.value.node_type == "controlplane" && var.service_account_issuer != null ? [
    # Sign service account tokens as the public issuer, keep accepting tokens
    # from the old one, and keep their audience so existing clients still pass.
    yamlencode({
      cluster = {
        apiServer = {
          extraArgs = {
            "service-account-issuer" = [var.service_account_issuer, var.cluster_endpoint]
            "api-audiences"          = var.cluster_endpoint
          }
        }
      }
    })
  ] : [], var.config_patches, each.value.config_patches)
}

resource "talos_machine_configuration_apply" "node" {
  for_each = var.talos_nodes

  node                        = each.value.api_address
  endpoint                    = each.value.api_address
  client_configuration        = talos_machine_secrets.this.client_configuration
  machine_configuration_input = data.talos_machine_configuration.node[each.key].machine_configuration
  # Maintenance mode accepts auto for initial installation, but rejects no_reboot.
  apply_mode = "auto"

  timeouts = {
    create = "15m"
    update = "15m"
  }

  lifecycle {
    replace_triggered_by = [proxmox_virtual_environment_vm.node[each.key].id]
  }

  # VM creation is not proof that the Talos API is ready. The provider retries
  # the API connection during initial application within the create timeout.
  depends_on = [proxmox_virtual_environment_vm.node]
}

data "talos_client_configuration" "this" {
  cluster_name         = var.cluster_name
  client_configuration = talos_machine_secrets.this.client_configuration
  endpoints            = [for key, node in local.control_plane_nodes : node.api_address]
  nodes                = [for key, node in var.talos_nodes : node.api_address]
}
