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
    node_name = string
    tags      = list(string)
    os        = optional(string, "ubuntu")
    cpu       = optional(number)
    memory    = optional(number)
  }))
}
