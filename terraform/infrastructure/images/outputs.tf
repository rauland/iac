output "cloud_image_ids" {
  value = { for k, v in proxmox_virtual_environment_download_file.cloud_image : k => v.id }
}