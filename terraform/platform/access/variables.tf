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

variable "kubernetes_storage_pools" {
  description = "Existing ZFS dataset per environment for Kubernetes volumes. Each becomes storage k8s-<environment>, the only storage that environment's CSI identity can allocate on or delete from. Create the dataset before applying."
  type        = map(string)
  default     = { dev = "nas/k8s-dev" }
  validation {
    condition     = alltrue([for environment in keys(var.kubernetes_storage_pools) : contains(["dev", "prod"], environment)])
    error_message = "Kubernetes storage pools must be keyed by dev or prod."
  }
}
