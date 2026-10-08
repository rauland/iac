variable "vm_config" {
  description = <<EOT
    Virtual machine configuration object containing the following attributes:
    -------------------------------------------------------------------------
    vm_name                | Name of the virtual machine.
    node_name              | Proxmox node on which the VM will run.
    cpu                    | Number of CPU cores allocated to the VM.
    memory                 | Amount of memory allocated to the VM in MB.
    tags                   | Tags assigned to the VM.
    image_datastore_id     | Datastore containing the installation ISO.
    image_file_name        | Installation ISO filename.
    image_content_type     | Content type of the image (e.g., "import", "iso").
    agent_enabled          | Whether the QEMU agent is enabled for the VM.
    description            | Description of the VM.
    machine                | Machine type for the VM.
    bios                   | BIOS type for the VM.
    stop_on_destroy        | Whether to stop the VM on destroy.
    cpu_cores              | Number of CPU cores for the VM.
    memory_dedicated       | Amount of dedicated memory (in MB) for the VM.
    efi_disk_datastore_id  | Datastore ID for the EFI disk.
    efi_disk_type          | Type of the EFI disk.
    disk_datastore_id      | Datastore ID for the main disk.
    disk_interface         | Interface for the main disk.
    disk_size              | Size of the main disk (in GB).
    ip_config_ipv4_address | IPv4 address for the VM.
    user_account_username  | Username for the user account.
    user_account_keys_file | Path to the public SSH key file for the user account.
    network_device_bridge  | Bridge for the network device.
  EOT

  type = object({
    vm_name                = string
    node_name              = string
    cpu                    = number
    memory                 = number
    tags                   = optional(list(string), [])
    image_datastore_id     = string
    image_file_name        = string
    image_content_type     = string
    agent_enabled          = optional(bool, false)
    description            = optional(string, "Created by Terraform")
    machine                = optional(string, "q35")
    bios                   = optional(string, "ovmf")
    stop_on_destroy        = optional(bool, true)
    cpu_cores              = optional(number, 1)
    memory_dedicated       = optional(number, 1024)
    efi_disk_datastore_id  = optional(string, "local-lvm")
    efi_disk_type          = optional(string, "4m")
    disk_datastore_id      = optional(string, "local-lvm")
    disk_interface         = optional(string, "virtio0")
    disk_size              = optional(number, 20)
    ip_config_ipv4_address = optional(string, "dhcp")
    user_account_username  = optional(string, "ansible")
    user_account_keys_file = optional(string, "../../../ssh/id_ed25519.pub")
    network_device_bridge  = optional(string, "vmbr0")
  })
}
