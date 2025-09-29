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
