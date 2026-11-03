mock_provider "proxmox" {}

variables {
  virtual_environment_endpoint  = "https://pve.example.invalid:8006"
  virtual_environment_api_token = "test@pve!ci=placeholder"
}

run "environment_boundaries" {
  command = plan

  assert {
    condition = alltrue([
      for grant in local.service_grants : (
        grant.path != "/" && grant.path != "/vms" &&
        (!startswith(grant.path, "/pool/") || grant.path == "/pool/${local.services[grant.name].environment}")
      )
    ])
    error_message = "Automation must never receive global or cross-environment VM access."
  }
  assert {
    condition = alltrue([
      for name, service in local.services : contains(["apply", "csi"], service.operation) || alltrue([
        for grant in local.service_grants :
        contains(concat(["PVEAuditor", "NodeAudit", "StorageRead", "NetworkRead"], service.operation == "plan" ? ["PlanDiskAccess", "CSIVolumeRead"] : []), grant.role) if grant.name == name
      ])
    ])
    error_message = "Read identities must have only audit privileges plus the explicit plan-only disk permissions."
  }
  assert {
    condition = (
      toset(local.roles.PlanDiskAccess) == toset(["VM.Config.Disk"]) &&
      alltrue([for grant in local.service_grants : local.services[grant.name].operation == "plan" && grant.path == "/pool/${local.services[grant.name].environment}" if grant.role == "PlanDiskAccess"])
    )
    error_message = "The disk-metadata compatibility grant belongs only to plan identities in their own pool."
  }
  assert {
    condition = (
      alltrue([for token in proxmox_user_token.ci : token.privileges_separation]) &&
      toset(keys(proxmox_acl.service_user)) == toset(keys(proxmox_acl.service_token)) &&
      alltrue([for user in proxmox_virtual_environment_user.service : length(user.groups) == 0])
    )
    error_message = "Tokens must be privilege separated, with matching owner ACLs and no inherited group access."
  }
  assert {
    condition = (
      toset(keys(local.services)) == toset(["tf-dev-plan", "tf-dev-apply", "tf-prod-plan", "tf-prod-apply", "k8s-csi-dev", "k8s-csi-prod"]) &&
      alltrue([for grant in local.service_grants : grant.role == "StorageRead" if grant.path == "/storage/local"]) &&
      alltrue([for storage in proxmox_storage_directory.environment_images : !startswith(storage.path, "/var/lib/vz")])
    )
    error_message = "Only the Terraform and CSI identities exist, and none can write to shared image storage."
  }
  assert {
    condition = (
      toset(local.roles.SeedPublisher) == toset(["Datastore.Audit", "Datastore.AllocateTemplate", "Datastore.Allocate"]) &&
      toset([for grant in local.service_grants : "${grant.name}:${grant.path}" if grant.role == "SeedPublisher"]) == toset(["tf-dev-apply:/storage/dev-images", "tf-prod-apply:/storage/prod-images"]) &&
      alltrue([for grant in local.service_grants : grant.path == "/storage/${local.services[grant.name].environment}-images" if endswith(grant.path, "-images")])
    )
    error_message = "ISO cleanup belongs only to each environment's apply identity on its own images storage, never another environment's, shared images or read identities."
  }
  assert {
    condition = (
      !contains(local.roles.DownloadAccess, "Sys.Modify") &&
      alltrue([for grant in local.service_grants : local.services[grant.name].operation == "apply" if grant.role == "DownloadAccess"])
    )
    error_message = "Downloads must use node-scoped Sys.AccessNetwork and never grant Sys.Modify."
  }
  assert {
    condition = (
      toset(local.roles.KubernetesDisk) == toset(["VM.Audit", "VM.Config.Disk"]) &&
      toset(local.roles.KubernetesStorage) == toset(["Datastore.Audit", "Datastore.Allocate", "Datastore.AllocateSpace"]) &&
      toset([for name, service in local.services : name if service.operation == "csi"]) == toset(["k8s-csi-dev", "k8s-csi-prod"]) &&
      alltrue([
        for grant in local.service_grants : contains([
          "${grant.role}:/nodes/${var.node_name}" == "NodeAudit:${grant.path}",
          grant.role == "KubernetesDisk" && grant.path == "/pool/${local.services[grant.name].environment}",
          grant.role == "KubernetesStorage" && contains(["/storage/k8s-${local.services[grant.name].environment}", "/storage/k8s-${local.services[grant.name].environment}-bulk"], grant.path),
        ], true) if local.services[grant.name].operation == "csi"
      ]) &&
      alltrue([for grant in local.service_grants : local.services[grant.name].operation == "csi" if contains(["KubernetesDisk", "KubernetesStorage"], grant.role)])
    )
    error_message = "CSI identities may only attach disks in their own pool and allocate on their own Kubernetes storage."
  }
  assert {
    condition = (
      toset([for grant in local.service_grants : grant.name if grant.path == "/storage/k8s-dev" && grant.role == "StorageRead"]) == toset(["tf-dev-plan", "tf-dev-apply"]) &&
      toset([for grant in local.service_grants : grant.name if grant.path == "/storage/k8s-dev-bulk" && grant.role == "StorageRead"]) == toset(["tf-dev-plan", "tf-dev-apply"]) &&
      toset([for grant in local.service_grants : grant.name if grant.path == "/storage/k8s-prod-bulk" && grant.role == "KubernetesStorage"]) == toset(["k8s-csi-prod"]) &&
      alltrue([for grant in local.service_grants : contains(["StorageRead", "KubernetesStorage"], grant.role) if startswith(grant.path, "/storage/k8s-")]) &&
      toset([for grant in local.service_grants : "${grant.name}:${grant.role}" if grant.path == "/vms/9999"]) == toset(["tf-dev-plan:CSIVolumeRead", "tf-dev-apply:CSIVolumeRead", "tf-prod-plan:CSIVolumeRead", "tf-prod-apply:CSIVolumeRead"]) &&
      alltrue([for grant in local.service_grants : grant.path == "/vms/9999" if grant.role == "CSIVolumeRead"])
    )
    error_message = "Terraform identities may only read their environment's Kubernetes storage, so VM refreshes can see CSI disks."
  }
  assert {
    condition = (
      proxmox_storage_zfspool.kubernetes["dev"].id == "k8s-dev" &&
      proxmox_storage_zfspool.kubernetes["dev"].zfs_pool != "nas" &&
      toset(proxmox_storage_zfspool.kubernetes["dev"].content) == toset(["images"])
    )
    error_message = "Kubernetes volumes need a dedicated dataset, never the shared ZFS pool root."
  }
  assert {
    condition = (
      proxmox_storage_zfspool.kubernetes_bulk["prod"].id == "k8s-prod-bulk" &&
      proxmox_storage_zfspool.kubernetes_bulk["prod"].zfs_pool == "nas/k8s-prod-bulk" &&
      proxmox_storage_zfspool.kubernetes_bulk["prod"].blocksize == "128k" &&
      proxmox_storage_zfspool.kubernetes_bulk["prod"].thin_provision
    )
    error_message = "Bulk volumes need their own sibling dataset with large blocks."
  }
  assert {
    condition = (
      toset(local.roles.PCIMappingUser) == toset(["Mapping.Use"]) &&
      toset([for grant in local.service_grants : "${grant.name}:${grant.path}" if grant.role == "PCIMappingUser"]) == toset(["tf-prod-apply:/mapping/pci/gpu-p2200"]) &&
      alltrue([for grant in local.service_grants : grant.role == "PCIMappingUser" if startswith(grant.path, "/mapping/")])
    )
    error_message = "Only an environment's apply identity may use that environment's PCI mappings, and only to attach them."
  }
}

run "reject_unknown_pci_environment" {
  command = plan
  variables {
    pci_mappings = {
      gpu = { environment = "staging", path = "0000:01:00.0", id = "10de:0000", subsystem_id = "10de:0000", iommu_group = 1 }
    }
  }
  expect_failures = [var.pci_mappings]
}

run "reject_invalid_bulk_blocksize" {
  command = plan
  variables {
    kubernetes_bulk_blocksize = "1M"
  }
  expect_failures = [var.kubernetes_bulk_blocksize]
}

run "reject_unknown_storage_environment" {
  command = plan
  variables {
    kubernetes_storage_pools = { staging = "nas/k8s-staging" }
  }
  expect_failures = [var.kubernetes_storage_pools]
}
