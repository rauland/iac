variable "pool_id" {
  description = "Environment resource pool. Created by terraform/platform/access."
  type        = string
  nullable    = false
  validation {
    condition     = contains(["dev", "prod"], var.pool_id)
    error_message = "Select the dev or prod resource pool."
  }
}

variable "cluster_name" {
  description = "Unique cluster name, also used to namespace downloaded boot media."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*$", var.cluster_name))
    error_message = "cluster_name must start with a lowercase letter and contain only lowercase letters, digits, and hyphens."
  }
}

variable "cluster_endpoint" {
  description = "Kubernetes API URL, including https:// and port 6443; provide a stable load balancer or control-plane address."
  type        = string
  validation {
    condition     = can(regex("^https://[^/]+:6443$", var.cluster_endpoint))
    error_message = "cluster_endpoint must be an HTTPS Kubernetes API endpoint with port 6443."
  }
}

variable "talos_version" {
  description = "Pinned Talos release for boot media, installer, secrets, and configuration contract. OS upgrades are explicit operations; see README.md."
  type        = string
  validation {
    condition     = can(regex("^v[0-9]+[.][0-9]+[.][0-9]+$", var.talos_version))
    error_message = "talos_version must be a pinned release such as v1.11.2."
  }
}

variable "kubernetes_version" {
  description = "Pinned Kubernetes release used to generate new machine configurations; live upgrades use talosctl upgrade-k8s."
  type        = string
  validation {
    condition     = can(regex("^v[0-9]+[.][0-9]+[.][0-9]+$", var.kubernetes_version))
    error_message = "kubernetes_version must be a pinned release such as v1.34.1."
  }
}

variable "bootstrap_node" {
  description = "Stable key of the control-plane node bootstrapped once. Keep this key and address stable for the lifetime of the cluster."
  type        = string
  validation {
    condition     = try(var.talos_nodes[var.bootstrap_node].node_type == "controlplane", false)
    error_message = "bootstrap_node must select an existing control-plane node."
  }
}

variable "iso_datastore_id" {
  description = "File-based Proxmox storage with ISO content enabled, on every selected Proxmox node."
  type        = string
  default     = "local"
}

variable "disk_datastore_id" {
  description = "Default storage for VM and EFI disks; LVM-Thin is supported."
  type        = string
  default     = "local-lvm"
}

variable "system_extensions" {
  description = "Official Image Factory extensions, included in both the ISO and installer."
  type        = list(string)
  default     = ["qemu-guest-agent"]
  validation {
    condition     = contains(var.system_extensions, "qemu-guest-agent")
    error_message = "Include qemu-guest-agent because the VMs enable its Proxmox interface."
  }
}

variable "dns_servers" {
  description = "DNS resolvers reachable by the nodes. Required when any node uses static networking. DHCP nodes may use DHCP-provided resolvers."
  type        = list(string)
  default     = []
  validation {
    condition     = alltrue([for node in var.talos_nodes : node.ipv4_address == "dhcp"]) || length(var.dns_servers) > 0
    error_message = "Set dns_servers when using static node networking."
  }
}

variable "config_patches" {
  description = "Additional Talos YAML patches applied to every node. Per-node patches follow these. Configuration changes that require reboot fail rather than rebooting the whole cluster in parallel."
  type        = list(string)
  default     = []
}

variable "talos_nodes" {
  description = "VM definitions keyed by stable node identity. api_address must be a known, reserved maintenance-mode IPv4 address reachable from the runner."
  type = map(object({
    node_name         = string
    node_type         = string
    pve_node          = string
    api_address       = string
    ipv4_address      = optional(string, "dhcp")
    ipv4_gateway      = optional(string)
    mac_address       = optional(string)
    cpu               = optional(number, 2)
    cpu_type          = optional(string, "x86-64-v2-AES")
    memory            = optional(number, 4096)
    disk_size         = optional(number, 32)
    disk_datastore_id = optional(string)
    bridge            = optional(string, "vmbr0")
    vlan_id           = optional(number)
    vm_id             = optional(number)
    config_patches    = optional(list(string), [])
  }))

  validation {
    condition     = length(var.talos_nodes) > 0 && alltrue([for node in var.talos_nodes : contains(["controlplane", "worker"], node.node_type)])
    error_message = "Define at least one node; node_type must be controlplane or worker."
  }
  validation {
    condition     = alltrue([for key, node in var.talos_nodes : key == node.node_name])
    error_message = "Map keys must equal node_name to preserve stable VM and configuration addresses."
  }
  validation {
    condition     = alltrue([for node in var.talos_nodes : can(cidrnetmask("${node.api_address}/32"))])
    error_message = "Every api_address must be an IPv4 address without a CIDR suffix."
  }
  validation {
    condition     = length(distinct([for node in var.talos_nodes : node.api_address])) == length(var.talos_nodes)
    error_message = "Each node must have a unique api_address."
  }
  validation {
    condition = alltrue([for node in var.talos_nodes : node.ipv4_address == "dhcp" ? node.ipv4_gateway == null : (
      can(cidrnetmask(node.ipv4_address)) && split("/", node.ipv4_address)[0] == node.api_address && node.ipv4_gateway != null
    )])
    error_message = "Use dhcp without a gateway, or an IPv4 CIDR matching api_address with an explicit gateway. Reserve the same address for ISO maintenance mode."
  }
  validation {
    condition     = alltrue([for node in var.talos_nodes : node.cpu >= 2 && node.memory >= 2048 && node.disk_size >= 10])
    error_message = "Each node requires at least 2 CPU cores, 2048 MiB RAM, and a 10 GiB disk."
  }
}
