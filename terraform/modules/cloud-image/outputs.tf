output "ubuntu_cloud_image_id" {
  description = "ID of the downloaded Ubuntu cloud image"
  value       = proxmox_virtual_environment_download_file.ubuntu_cloud_image.id
}
