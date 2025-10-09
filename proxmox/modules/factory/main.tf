data "talos_image_factory_extensions_versions" "this" {
  # get the latest talos version
  talos_version = "v1.11.2"
  filters = {
    names = [
      "i915",
      "qemu-guest-agent",
    ]
  }
}

resource "talos_image_factory_schematic" "this" {
  schematic = yamlencode(
    {
      customization = {
        systemExtensions = {
          officialExtensions = data.talos_image_factory_extensions_versions.this.extensions_info[*].name
        }
      }
    }
  )
}

output "schematic_id" {
  value = talos_image_factory_schematic.this.id
}

data "talos_image_factory_urls" "this" {
  talos_version = "v1.11.2"
  schematic_id  = talos_image_factory_schematic.this.id
  platform      = "nocloud"
}

output "installer_iso_url" {
  value = data.talos_image_factory_urls.this.urls.iso
}