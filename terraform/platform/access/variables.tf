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

variable "disk_datastores" {
  description = "Storage for each environment's VM disks. Keep busy environments off the Proxmox OS disk's small thin pool."
  type        = map(string)
  default = {
    dev  = "local-lvm"
    prod = "local-data"
  }
}

variable "shared_image_datastore_id" {
  type    = string
  default = "local"
}

variable "bridge" {
  type    = string
  default = "vmbr0"
}

variable "image_paths" {
  description = "Directory for each environment's ISO storage (<environment>-images), outside the shared local directory."
  type        = map(string)
  default = {
    dev  = "/var/lib/proxmox-dev-images"
    prod = "/var/lib/proxmox-prod-images"
  }
}

variable "infra_vm_ids" {
  description = "Existing shared infrastructure guests. Workload roots own dev/prod membership through VM pool_id."
  type        = set(number)
  default     = [100, 101, 116]
}

variable "csi_volume_owner_vmid" {
  description = "Placeholder VM ID in the Proxmox CSI plugin's volume names (vm-<id>-pvc-...). No VM may use it."
  type        = number
  default     = 9999
}

variable "kubernetes_storage_pools" {
  description = "Existing ZFS dataset per environment for Kubernetes volumes. Each becomes storage k8s-<environment>, the only storage that environment's CSI identity can allocate on or delete from. Create the datasets first with scripts/prepare-host.sh."
  type        = map(string)
  default     = { dev = "nas/k8s-dev", prod = "nas/k8s-prod" }
  validation {
    condition     = alltrue([for environment in keys(var.kubernetes_storage_pools) : contains(["dev", "prod"], environment)])
    error_message = "Kubernetes storage pools must be keyed by dev or prod."
  }
}

variable "pci_mappings" {
  description = "Host PCI devices that one environment's VMs may pass through, keyed by Proxmox resource mapping name. Only that environment's apply identity may use each mapping. Read id, subsystem and IOMMU group from pvesh get /nodes/NODE/hardware/pci."
  type = map(object({
    environment  = string
    path         = string
    id           = string
    subsystem_id = string
    iommu_group  = number
    comment      = optional(string, "")
  }))
  default = {
    gpu-p2200 = {
      environment  = "prod"
      path         = "0000:65:00.0"
      id           = "10de:1c31"
      subsystem_id = "1028:131b"
      iommu_group  = 2
      comment      = "NVIDIA Quadro P2200 for media transcoding"
    }
  }
  validation {
    condition     = alltrue([for mapping in var.pci_mappings : contains(["dev", "prod"], mapping.environment)])
    error_message = "PCI mappings must belong to dev or prod."
  }
}

