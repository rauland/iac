variable "pve_nodes" {
  description = "List of Proxmox VE Nodes"
  type        = list(string)
}

variable "iso_url" {
  description = "URL of the Talos ISO"
  type        = string
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

variable "controlplane_config" {
  type = string
}

variable "worker_config" {
  type = string
}