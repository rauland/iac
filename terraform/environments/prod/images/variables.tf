variable "virtual_environment_endpoint" {
  type = string
}

variable "virtual_environment_ssh_username" {
  type = string
}

variable "virtual_environment_api_token" {
  type      = string
  sensitive = true
}

variable "cloud_images" {
  type = map(object({
    url        = string
    node_names = list(string)
  }))
  default = {
    "resolute-server-cloudimg-amd64.img" = {
      url        = "https://cloud-images.ubuntu.com/resolute/current/resolute-server-cloudimg-amd64.img"
      node_names = ["pve"]
    }
    "AlmaLinux-10-GenericCloud-latest.x86_64.img" = {
      url        = "https://repo.almalinux.org/almalinux/10/cloud/x86_64/images/AlmaLinux-10-GenericCloud-latest.x86_64.qcow2"
      node_names = ["pve"]
    }
  }
}
