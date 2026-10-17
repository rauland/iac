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
