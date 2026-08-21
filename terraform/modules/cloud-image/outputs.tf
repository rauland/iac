output "ids" {
  description = "IDs of the downloaded cloud images"
  value       = { for k, v in proxmox_download_file.node : k => v.id }
}
