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

variable "pve_nodes" {
  description = "List of Proxmox VE Nodes"
  type        = list(string)
}

variable "talos_nodes" {
  description = "List of Talos Nodes"
  type = map(object({
    node_name    = string
    node_type    = string
    pve_node     = string
    ipv4_address = string
    ipv4_gateway = optional(string)
  }))
}
