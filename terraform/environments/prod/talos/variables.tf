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
  default     = ["pve"]
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
  default = {
    controlplane-01 = {
      node_name    = "controlplane-01"
      node_type    = "controlplane"
      pve_node     = "pve"
      ipv4_address = "10.0.0.50/24"
      ipv4_gateway = "10.0.0.1"
    }
    worker-01 = {
      node_name    = "worker-01"
      node_type    = "worker"
      pve_node     = "pve"
      ipv4_address = "dhcp"
    }
    worker-02 = {
      node_name    = "worker-02"
      node_type    = "worker"
      pve_node     = "pve"
      ipv4_address = "dhcp"
    }
  }
}
