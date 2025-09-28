variable "virtual_environment_endpoint" {
  type = string
}

variable "virtual_environment_ssh_username" {
  type = string
}  

variable "virtual_environment_api_token" {
  type = string
  sensitive = true
}

variable "vm_name" {
  description = "Name of the VM"
  type        = string
}

variable "talos_node_name" {
  description = "Name of the Talos Node"
  type        = string
}
