# Preserve identities and cluster credentials while collapsing child modules.
# These address moves do not make an old VM disk layout safe to convert in place.
# See README.md before applying to an existing cluster.
moved {
  from = module.factory.talos_image_factory_schematic.this
  to   = talos_image_factory_schematic.this
}

moved {
  from = module.cluster.talos_machine_secrets.this
  to   = talos_machine_secrets.this
}

moved {
  from = module.nodes.proxmox_download_file.talos-nocloud-amd64
  to   = proxmox_download_file.iso
}

moved {
  from = module.nodes.proxmox_virtual_environment_vm.talos_vm
  to   = proxmox_virtual_environment_vm.node
}

moved {
  from = module.bootstrap.talos_machine_bootstrap.this
  to   = talos_machine_bootstrap.this
}

moved {
  from = module.bootstrap.talos_cluster_kubeconfig.this
  to   = talos_cluster_kubeconfig.this
}

# Stop managing old snippet and runner-local credentials without deleting them.
# Remove the secret-bearing snippets from Proxmox manually after migration.
removed {
  from = module.nodes.proxmox_virtual_environment_file.controlplane_config
  lifecycle {
    destroy = false
  }
}

removed {
  from = module.nodes.proxmox_virtual_environment_file.worker_config
  lifecycle {
    destroy = false
  }
}

removed {
  from = local_file.talosconfig
  lifecycle {
    destroy = false
  }
}

removed {
  from = local_file.kubeconfig
  lifecycle {
    destroy = false
  }
}
