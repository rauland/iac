data "talos_image_factory_extensions_versions" "this" {
  talos_version = var.talos_version
  filters = {
    names = var.system_extensions
  }
}

resource "talos_image_factory_schematic" "this" {
  schematic = yamlencode({
    customization = {
      systemExtensions = {
        officialExtensions = data.talos_image_factory_extensions_versions.this.extensions_info[*].name
      }
    }
  })
}

data "talos_image_factory_urls" "this" {
  talos_version = var.talos_version
  schematic_id  = talos_image_factory_schematic.this.id
  platform      = "metal"
  architecture  = "amd64"
}

# A node with its own system_extensions gets its own image: the cluster's
# extensions plus its own. Extensions that wait for hardware, such as NVIDIA's,
# must stay on the nodes that have it. The boot ISO stays the cluster's: it is
# only used to install a new VM, and installation pulls the node's installer.
locals {
  node_extensions = {
    for key, node in var.talos_nodes :
    key => sort(distinct(concat(var.system_extensions, node.system_extensions)))
    if length(node.system_extensions) > 0
  }
  installer_images = {
    for key, node in var.talos_nodes : key => (
      contains(keys(local.node_extensions), key)
      ? data.talos_image_factory_urls.node[key].urls.installer_secureboot
      : data.talos_image_factory_urls.this.urls.installer_secureboot
    )
  }
}

data "talos_image_factory_extensions_versions" "node" {
  for_each      = local.node_extensions
  talos_version = var.talos_version
  filters = {
    names = each.value
  }
}

resource "talos_image_factory_schematic" "node" {
  for_each = local.node_extensions
  schematic = yamlencode({
    customization = {
      systemExtensions = {
        officialExtensions = data.talos_image_factory_extensions_versions.node[each.key].extensions_info[*].name
      }
    }
  })
}

data "talos_image_factory_urls" "node" {
  for_each      = local.node_extensions
  talos_version = var.talos_version
  schematic_id  = talos_image_factory_schematic.node[each.key].id
  platform      = "metal"
  architecture  = "amd64"
}

# Preserve pre-RBAC media on shared storage. Dev credentials cannot delete
# shared images, and existing running guests may still have this ISO attached.
removed {
  from = proxmox_download_file.iso
  lifecycle {
    destroy = false
  }
}

resource "proxmox_download_file" "environment_iso" {
  for_each = local.proxmox_nodes

  node_name    = each.key
  datastore_id = var.iso_datastore_id
  content_type = "iso"
  file_name    = "${var.cluster_name}-talos-${var.talos_version}-${talos_image_factory_schematic.this.id}-secureboot.iso"
  url          = data.talos_image_factory_urls.this.urls.iso_secureboot

  lifecycle {
    create_before_destroy = true
  }
}
