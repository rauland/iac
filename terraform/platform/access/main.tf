locals {
  environments = toset(["dev", "prod"])
  roles = {
    NodeAudit      = ["Sys.Audit"]
    StorageRead    = ["Datastore.Audit"]
    NetworkRead    = ["SDN.Audit"]
    ImagePublisher = ["Datastore.Audit", "Datastore.AllocateTemplate"]
    SeedPublisher  = ["Datastore.Audit", "Datastore.AllocateTemplate", "Datastore.Allocate"]
    DownloadAccess = ["Sys.AccessNetwork"]
    PlanDiskAccess = ["VM.Config.Disk"]
    # The Proxmox CSI plugin attaches volumes to VMs in its pool and creates
    # and deletes them only on its environment's dedicated Kubernetes storage.
    KubernetesDisk    = ["VM.Audit", "VM.Config.Disk"]
    KubernetesStorage = ["Datastore.Audit", "Datastore.Allocate", "Datastore.AllocateSpace"]
    # Lets Terraform identities read CSI volumes when refreshing the VMs they
    # are attached to; deleting them still needs Datastore.Allocate.
    CSIVolumeRead = ["VM.Config.Disk"]
  }
  groups = merge({ "platform-admins" = "Platform administrators" }, merge([
    for environment in local.environments : {
      "${environment}-admins"  = "${environment} VM administrators"
      "${environment}-viewers" = "${environment} VM viewers"
    }
  ]...))
  services = merge(merge([
    for environment in local.environments : {
      for operation in ["plan", "apply", "ansible"] :
      (operation == "ansible" ? "ansible-${environment}" : "tf-${environment}-${operation}") => {
        environment = environment
        operation   = operation
      }
    }
    ]...), {
    "tf-platform-images-plan"  = { environment = "platform", operation = "plan" }
    "tf-platform-images-apply" = { environment = "platform", operation = "apply" }
    }, {
    for environment in keys(var.kubernetes_storage_pools) :
    "k8s-csi-${environment}" => { environment = environment, operation = "csi" }
  })
  # Explicit ACLs apply to both owners and privilege-separated tokens.
  service_grants = flatten([
    for name, service in local.services : service.operation == "csi" ? [
      { path = "/nodes/${var.node_name}", role = "NodeAudit", name = name },
      { path = "/pool/${service.environment}", role = "KubernetesDisk", name = name },
      { path = "/storage/k8s-${service.environment}", role = "KubernetesStorage", name = name }
      ] : concat(
      [{ path = "/nodes/${var.node_name}", role = "NodeAudit", name = name }],
      service.environment == "platform" ? [] : [
        for role in(service.operation == "apply" ? ["PVEVMAdmin", "PVEPoolAdmin"] : ["PVEAuditor"]) :
        { path = "/pool/${service.environment}", role = role, name = name }
      ],
      service.environment != "platform" && service.operation == "plan" ? [
        { path = "/pool/${service.environment}", role = "PlanDiskAccess", name = name }
      ] : [],
      service.operation == "ansible" ? [] : [
        { path = "/storage/${var.shared_image_datastore_id}", role = service.environment == "platform" && service.operation == "apply" ? "ImagePublisher" : "StorageRead", name = name }
      ],
      service.environment == "platform" || service.operation == "ansible" ? [] : [
        { path = "/storage/${var.disk_datastore_id}", role = service.operation == "apply" ? "PVEDatastoreUser" : "StorageRead", name = name },
        { path = "/sdn/zones/localnetwork/${var.bridge}", role = service.operation == "apply" ? "PVESDNUser" : "NetworkRead", name = name }
      ],
      # The CSI plugin attaches volumes from this storage to the environment's
      # VMs, and refreshing a VM reads every attached disk. The volumes are
      # named for placeholder VM 9999, and Proxmox requires VM.Config.Disk on
      # a volume's owner to read it.
      contains(["plan", "apply"], service.operation) && contains(keys(var.kubernetes_storage_pools), service.environment) ? [
        { path = "/storage/k8s-${service.environment}", role = "StorageRead", name = name },
        { path = "/vms/${var.csi_volume_owner_vmid}", role = "CSIVolumeRead", name = name }
      ] : [],
      service.environment == "dev" && service.operation != "ansible" ? [
        { path = "/storage/dev-images", role = service.operation == "apply" ? "SeedPublisher" : "StorageRead", name = name }
      ] : [],
      service.operation == "apply" && contains(["dev", "platform"], service.environment) ? [
        { path = "/nodes/${var.node_name}", role = "DownloadAccess", name = name }
      ] : []
    )
  ])
  service_acl = { for grant in local.service_grants : "${grant.name}:${grant.path}:${grant.role}" => grant }
  group_grants = concat(
    [{ group = "platform-admins", path = "/", role = "Administrator" }],
    flatten([
      for environment in local.environments : concat(
        [for role in ["PVEVMAdmin", "PVEPoolUser"] : { group = "${environment}-admins", path = "/pool/${environment}", role = role }],
        [{ group = "${environment}-viewers", path = "/pool/${environment}", role = "PVEAuditor" }],
        [for suffix in ["admins", "viewers"] : { group = "${environment}-${suffix}", path = "/nodes/${var.node_name}", role = "NodeAudit" }],
        [
          { group = "${environment}-admins", path = "/storage/${var.disk_datastore_id}", role = "PVEDatastoreUser" },
          { group = "${environment}-admins", path = "/storage/${var.shared_image_datastore_id}", role = "StorageRead" },
          { group = "${environment}-admins", path = "/sdn/zones/localnetwork/${var.bridge}", role = "PVESDNUser" }
        ],
        environment == "dev" ? [{ group = "dev-admins", path = "/storage/dev-images", role = "StorageRead" }] : []
      )
    ])
  )
}

resource "proxmox_virtual_environment_pool" "environment" {
  for_each = toset(["dev", "prod", "infra"])
  pool_id  = each.key
  comment  = "Managed by terraform/platform/access"
  lifecycle {
    prevent_destroy = true
  }
}

resource "proxmox_storage_directory" "dev_images" {
  id      = "dev-images"
  path    = var.dev_images_path
  nodes   = [var.node_name]
  content = ["iso"]
  shared  = false
  disable = false
  lifecycle {
    prevent_destroy = true
  }
}

# Kubernetes volumes get their own storage so the CSI identity's
# Datastore.Allocate cannot delete other disks in the same ZFS pool.
resource "proxmox_storage_zfspool" "kubernetes" {
  for_each       = var.kubernetes_storage_pools
  id             = "k8s-${each.key}"
  zfs_pool       = each.value
  nodes          = [var.node_name]
  content        = ["images"]
  thin_provision = true
  lifecycle {
    prevent_destroy = true
  }
}

resource "proxmox_pool_membership" "infra" {
  for_each = { for vm_id in var.infra_vm_ids : tostring(vm_id) => vm_id }
  pool_id  = proxmox_virtual_environment_pool.environment["infra"].pool_id
  vm_id    = each.value
}

resource "proxmox_virtual_environment_role" "custom" {
  for_each   = local.roles
  role_id    = each.key
  privileges = each.value
}

resource "proxmox_virtual_environment_group" "human" {
  for_each = local.groups
  group_id = each.key
  comment  = each.value
}

resource "proxmox_virtual_environment_user" "service" {
  for_each = local.services
  user_id  = "${each.key}@pve"
  enabled  = true
  groups   = []
  comment  = "${each.value.environment} ${each.value.operation}; managed by terraform/platform/access"
  lifecycle {
    prevent_destroy = true
  }
}

resource "proxmox_user_token" "ci" {
  for_each              = local.services
  user_id               = proxmox_virtual_environment_user.service[each.key].user_id
  token_name            = "ci"
  privileges_separation = true
  comment               = "${each.value.environment} ${each.value.operation} automation"
  lifecycle {
    prevent_destroy = true
  }
}

resource "proxmox_acl" "service_user" {
  for_each  = local.service_acl
  user_id   = proxmox_virtual_environment_user.service[each.value.name].user_id
  path      = each.value.path
  role_id   = each.value.role
  propagate = true
  depends_on = [
    proxmox_virtual_environment_pool.environment,
    proxmox_virtual_environment_role.custom,
    proxmox_storage_directory.dev_images,
    proxmox_storage_zfspool.kubernetes,
  ]
}

resource "proxmox_acl" "service_token" {
  for_each  = local.service_acl
  token_id  = proxmox_user_token.ci[each.value.name].id
  path      = each.value.path
  role_id   = each.value.role
  propagate = true
  depends_on = [
    proxmox_virtual_environment_pool.environment,
    proxmox_virtual_environment_role.custom,
    proxmox_storage_directory.dev_images,
    proxmox_storage_zfspool.kubernetes,
  ]
}

resource "proxmox_acl" "human" {
  for_each  = { for grant in local.group_grants : "${grant.group}:${grant.path}:${grant.role}" => grant }
  group_id  = proxmox_virtual_environment_group.human[each.value.group].group_id
  path      = each.value.path
  role_id   = each.value.role
  propagate = true
  depends_on = [
    proxmox_virtual_environment_pool.environment,
    proxmox_virtual_environment_role.custom,
    proxmox_storage_directory.dev_images,
    proxmox_storage_zfspool.kubernetes,
  ]
}
