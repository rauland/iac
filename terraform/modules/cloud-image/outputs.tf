output "ids" {
  description = "IDs of the downloaded cloud images"
  value       = { for k, v in proxmox_virtual_environment_download_file.cloud_image : k => v.id }
}