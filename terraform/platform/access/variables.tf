variable "virtual_environment_endpoint" {
  type = string
}

variable "virtual_environment_api_token" {
  type      = string
  sensitive = true
  ephemeral = true
}

variable "node_name" {
  type    = string
  default = "pve"
}

variable "disk_datastore_id" {
  type    = string
  default = "local-lvm"
}

variable "shared_image_datastore_id" {
  type    = string
  default = "local"
}

variable "bridge" {
  type    = string
  default = "vmbr0"
}

variable "dev_images_path" {
  description = "Dedicated directory, separate from the shared local datastore."
  type        = string
  default     = "/var/lib/proxmox-dev-images"
}

variable "infra_vm_ids" {
  description = "Existing shared infrastructure guests. Workload roots own dev/prod membership through VM pool_id."
  type        = set(number)
  default     = [100, 101, 105, 116]
}
