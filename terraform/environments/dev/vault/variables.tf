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

variable "vms" {
  type = map(object({
    node_name        = string
    tags             = list(string)
    cpu              = optional(number)
    memory           = optional(number)
    iso_datastore_id = optional(string, "local")
    iso_file_name    = optional(string, "resolute-server-cloudimg-amd64.img")
  }))
  default = {
    vault = {
      node_name     = "pve"
      tags          = ["managed", "vault"]
      cpu           = 2
      memory        = 4096
      iso_file_name = "AlmaLinux-10-GenericCloud-latest.x86_64.img"
    }
  }
}
