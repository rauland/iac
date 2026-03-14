variable "node_name" {
  description = "Name of PVE node where the ISO image will be downloaded"
  type        = string
}

variable "vm_name" {
  type = string
}

variable "user_account_keys_file" {
  description = "Path to the file containing SSH public keys for the user account"
  type        = string
  default     = "../../ssh/ansible_id_rsa.pub"
}