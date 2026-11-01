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
        contains(concat(["PVEAuditor", "NodeAudit", "StorageRead", "NetworkRead"], service.operation == "plan" ? ["PlanDiskAccess"] : []), grant.role) if grant.name == name
      ])
    ])
    error_message = "Read identities must have only audit privileges plus the explicit plan-only disk permission."
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
      alltrue([for grant in local.service_grants : !contains(["PVEVMAdmin", "PVEPoolAdmin", "Administrator"], grant.role) if local.services[grant.name].environment == "platform"]) &&
      alltrue([for grant in local.service_grants : grant.role != "ImagePublisher" if local.services[grant.name].environment == "dev" && grant.path == "/storage/local"]) &&
      proxmox_storage_directory.dev_images.path != "/var/lib/vz"
    )
    error_message = "Shared image publishers must have no VM administration, and dev must not publish to shared image storage."
  }
  assert {
    condition = (
      toset(local.roles.SeedPublisher) == toset(["Datastore.Audit", "Datastore.AllocateTemplate", "Datastore.Allocate"]) &&
      alltrue([for grant in local.service_grants : grant.name == "tf-dev-apply" && grant.path == "/storage/dev-images" if grant.role == "SeedPublisher"]) &&
      !contains(local.roles.ImagePublisher, "Datastore.Allocate")
    )
    error_message = "ISO cleanup belongs only to dev apply on dedicated dev-images storage, never shared images or read identities."
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
      toset([for name, service in local.services : name if service.operation == "csi"]) == toset(["k8s-csi-dev"]) &&
      alltrue([
        for grant in local.service_grants : contains([
          "${grant.role}:/nodes/${var.node_name}" == "NodeAudit:${grant.path}",
          grant.role == "KubernetesDisk" && grant.path == "/pool/${local.services[grant.name].environment}",
          grant.role == "KubernetesStorage" && grant.path == "/storage/k8s-${local.services[grant.name].environment}",
        ], true) if local.services[grant.name].operation == "csi"
      ]) &&
      alltrue([for grant in local.service_grants : local.services[grant.name].operation == "csi" if contains(["KubernetesDisk", "KubernetesStorage"], grant.role)])
    )
    error_message = "CSI identities may only attach disks in their own pool and allocate on their own Kubernetes storage."
  }
  assert {
    condition = (
      toset([for grant in local.service_grants : grant.name if grant.path == "/storage/k8s-dev" && grant.role == "StorageRead"]) == toset(["tf-dev-plan", "tf-dev-apply"]) &&
      alltrue([for grant in local.service_grants : contains(["StorageRead", "KubernetesStorage"], grant.role) if startswith(grant.path, "/storage/k8s-")])
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
}

run "reject_unknown_storage_environment" {
  command = plan
  variables {
    kubernetes_storage_pools = { staging = "nas/k8s-staging" }
  }
  expect_failures = [var.kubernetes_storage_pools]
}
