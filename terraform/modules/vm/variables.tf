variable "cloud_image_id" {
  description = "ID of the downloaded cloud image"
  type        = string
}

variable "vm_name" {
  description = "Name of the VM"
  type        = string
}

variable "node_name" {
  description = "Name of PVE node where the VM will be created"
  type        = string
}

variable "agent_enabled" {
  description = "Whether to enable the QEMU agent"
  type        = bool
  default     = true
}

variable "tags" {
  description = "List of tags for the VM"
  type        = list(string)
}

variable "description" {
  description = "Description of the VM"
  type        = string
  default     = "Created by Terraform"
}

variable "machine" {
  description = "Machine type for the VM"
  type        = string
  default     = "q35"
}

variable "bios" {
  description = "BIOS type for the VM"
  type        = string
  default     = "ovmf"
}

variable "stop_on_destroy" {
  description = "Whether to stop the VM on destroy"
  type        = bool
  default     = true
}

variable "cpu_cores" {
  description = "Number of CPU cores for the VM"
  type        = number
  default     = 1
}

variable "memory_dedicated" {
  description = "Amount of dedicated memory (in MB) for the VM"
  type        = number
  default     = 1024
}

variable "efi_disk_datastore_id" {
  description = "Datastore ID for the EFI disk"
  type        = string
  default     = "local-lvm"
}

variable "efi_disk_type" {
  description = "Type of the EFI disk"
  type        = string
  default     = "4m"
}

variable "disk_datastore_id" {
  description = "Datastore ID for the main disk"
  type        = string
  default     = "local-lvm"
}

variable "disk_interface" {
  description = "Interface for the main disk"
  type        = string
  default     = "virtio0"
}

variable "disk_size" {
  description = "Size of the main disk (in GB)"
  type        = number
  default     = 20
}

variable "ip_config_ipv4_address" {
  description = "IPv4 address for the VM"
  type        = string
  default     = "dhcp"
}

variable "user_account_username" {
  description = "Username for the user account"
  type        = string
  default     = "ansible"
}

variable "user_account_keys_file" {
  description = "Path to the file containing SSH public keys for the user account"
  type        = string
  default     = "../../ssh/ansible_id_rsa.pub"
}

variable "network_device_bridge" {
  description = "Bridge for the network device"
  type        = string
  default     = "vmbr0"
}
