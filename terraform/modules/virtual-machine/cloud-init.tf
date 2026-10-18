variable "cloud_init_iso" {
  description = "Opt into API-only AlmaLinux cloud-init and SSH host-key publication. Storage must allow ISO upload and deletion."
  type = object({
    datastore_id = string
  })
  default = null
}

locals {
  seed_enabled = var.cloud_init_iso != null
  seed_user_data = {
    hostname     = var.vm_config.vm_name
    ssh_pwauth   = false
    disable_root = true
    users = [{
      name                = var.vm_config.user_account_username
      shell               = "/bin/bash"
      lock_passwd         = true
      sudo                = "ALL=(ALL) NOPASSWD:ALL"
      ssh_authorized_keys = [for key in var.ssh_public_keys : trimspace(key)]
    }]
    write_files = [
      { path = "/usr/local/sbin/ci-agent-policy", permissions = "0700", owner = "root:root", content = file("${path.module}/cloud-init/agent-policy.py") },
      { path = "/usr/local/sbin/ci-publish-host-key", permissions = "0700", owner = "root:root", content = file("${path.module}/cloud-init/publish-host-key.sh") },
      { path = "/etc/systemd/system/ci-ssh-host-key.service", permissions = "0644", owner = "root:root", content = file("${path.module}/cloud-init/ci-ssh-host-key.service") },
    ]
    runcmd = [
      ["/usr/local/sbin/ci-agent-policy"],
      ["systemctl", "daemon-reload"],
      ["systemctl", "enable", "ci-ssh-host-key.service"],
      ["/usr/local/sbin/ci-publish-host-key"],
      ["systemctl", "restart", "qemu-guest-agent"],
    ]
  }
  seed_network = {
    version = 2
    ethernets = {
      primary = {
        match     = { name = "e*" }
        dhcp4     = var.vm_config.ip_config_ipv4_address == "dhcp"
        addresses = var.vm_config.ip_config_ipv4_address == "dhcp" ? [] : [var.vm_config.ip_config_ipv4_address]
        routes    = var.vm_config.ip_config_ipv4_gateway == null ? [] : [{ to = "default", via = var.vm_config.ip_config_ipv4_gateway }]
      }
    }
  }
}

data "external" "seed" {
  count   = local.seed_enabled ? 1 : 0
  program = ["python3", "${path.module}/scripts/build-seed.py"]
  query = {
    user-data      = "#cloud-config\n${yamlencode(local.seed_user_data)}"
    meta-data      = yamlencode({ instance-id = "${var.pool_id}/${var.vm_config.node_name}/${var.vm_config.vm_name}", local-hostname = var.vm_config.vm_name })
    network-config = yamlencode(local.seed_network)
  }
}

resource "proxmox_virtual_environment_file" "seed" {
  count        = local.seed_enabled ? 1 : 0
  node_name    = var.vm_config.node_name
  datastore_id = var.cloud_init_iso.datastore_id
  content_type = "iso"
  overwrite    = false
  source_file {
    path      = data.external.seed[0].result.path
    file_name = "cloud-init-${var.pool_id}-${var.vm_config.vm_name}-${substr(data.external.seed[0].result.sha256, 0, 16)}.iso"
    checksum  = data.external.seed[0].result.sha256
  }
}

# A stable trigger also exists for callers that do not use an ISO. Watching a
# counted resource directly fails when its count is zero.
resource "terraform_data" "bootstrap" {
  input = local.seed_enabled ? {
    sha256       = data.external.seed[0].result.sha256
    datastore_id = var.cloud_init_iso.datastore_id
  } : null
}
