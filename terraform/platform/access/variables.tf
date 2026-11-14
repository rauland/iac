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
  default     = [101]
}

variable "csi_volume_owner_vmid" {
  description = "Placeholder VM ID in the Proxmox CSI plugin's volume names (vm-<id>-pvc-...). No VM may use it."
  type        = number
  default     = 9999
}

variable "kubernetes_storage_pools" {
  description = "Existing ZFS dataset per environment for Kubernetes volumes. Each becomes storage k8s-<environment>, and <dataset>-bulk becomes k8s-<environment>-bulk; these are the only storages that environment's CSI identity can allocate on or delete from. Create the datasets first with scripts/prepare-host.sh."
  type        = map(string)
  default     = { dev = "nas/k8s-dev", prod = "nas/k8s-prod" }
  validation {
    condition     = alltrue([for environment in keys(var.kubernetes_storage_pools) : contains(["dev", "prod"], environment)])
    error_message = "Kubernetes storage pools must be keyed by dev or prod."
  }
}

variable "kubernetes_bulk_blocksize" {
  description = "ZFS block size of volumes on each environment's bulk storage (k8s-<environment>-bulk, on dataset <pool>-bulk), for large files written once such as media. Small blocks waste space to parity padding on RAIDZ; large blocks slow small random writes, so databases stay on k8s-<environment>."
  type        = string
  default     = "128k"
  validation {
    condition     = can(regex("^(4|8|16|32|64|128)k$", var.kubernetes_bulk_blocksize))
    error_message = "Use a ZFS volume block size from 4k to 128k."
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
    # The GPU and its audio function share IOMMU group 4, so the VM takes both.
    gpu-rtx3060 = {
      environment  = "prod"
      path         = "0000:17:00.0"
      id           = "10de:2503"
      subsystem_id = "1462:397b"
      iommu_group  = 4
      comment      = "NVIDIA GeForce RTX 3060 12GB for local AI models"
    }
    gpu-rtx3060-audio = {
      environment  = "prod"
      path         = "0000:17:00.1"
      id           = "10de:228e"
      subsystem_id = "1462:397b"
      iommu_group  = 4
      comment      = "Audio function of the RTX 3060, in the same IOMMU group"
    }
  }
  validation {
    condition     = alltrue([for mapping in var.pci_mappings : contains(["dev", "prod"], mapping.environment)])
    error_message = "PCI mappings must belong to dev or prod."
  }
}

