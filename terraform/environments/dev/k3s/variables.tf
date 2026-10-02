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
    vms = {
      k3s-01 = {
        node_name = "pve"
        tags      = ["managed", "k3s", "k3s-server"]
        cpu       = 2
        memory    = 4096
      }
      k3s-02 = {
        node_name = "pve"
        tags      = ["managed", "k3s", "k3s-agent"]
        cpu       = 2
        memory    = 4096
      }
      k3s-03 = {
        node_name = "pve"
        tags      = ["managed", "k3s", "k3s-agent"]
        cpu       = 2
        memory    = 4096
      }
    }
  }
}
