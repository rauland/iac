resource "proxmox_virtual_environment_download_file" "talos-nocloud-amd64" {
  content_type = "iso"
  datastore_id = "local"
  node_name    = "pve"

  url = "https://factory.talos.dev/image/ce4c980550dd2ab1b17bbf2b08801c7eb59418eafe8f279833297925d67c7515/v1.11.2/nocloud-amd64.iso"
}
