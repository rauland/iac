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

variable "vm_name" {
  description = "Name of the VM"
  type        = string
}

variable "talos_configs" {
  description = "List of Talos Configs"
  type        = map(string)
}

variable "talos_nodes" {
  description = "List of Talos Nodes"
  type = map(object({
    node_name = string
    ipv4_address = string
    ipv4_gateway = optional(string)
    pve_node  = string
    file_name = string
  }))
}
