resource "proxmox_virtual_environment_file" "user_data_cloud_config" {
  content_type = "snippets"
  datastore_id = "local"
  node_name    = var.node_name

  lifecycle {
    ignore_changes = [node_name]
  }

  source_raw {
    data = <<-EOF
    #cloud-config
    hostname: ${var.vm_name}
    timezone: Australia/Melbourne
    users:
      - default
      - name: ansible
        groups:
          - sudo
        shell: /bin/bash
        ssh_authorized_keys:
          - ${trimspace(data.local_file.ssh_public_key.content)}
        sudo: ALL=(ALL) NOPASSWD:ALL
    package_update: true
    packages:
      - sudo
      - qemu-guest-agent
    runcmd:
      - systemctl enable qemu-guest-agent
      - systemctl start qemu-guest-agent
      - echo "done" > /tmp/cloud-config.done
      - reboot
    EOF

    file_name = "${var.vm_name}-user-data-cloud-config.yaml"
  }
}
