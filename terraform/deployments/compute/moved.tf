moved {
  to = module.cloud_image.proxmox_virtual_environment_download_file.ubuntu_cloud_image 
  from = module.vm["test-vm"].proxmox_virtual_environment_download_file.ubuntu_cloud_image
}