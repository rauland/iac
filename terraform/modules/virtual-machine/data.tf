data "local_file" "ssh_public_key" {
  filename = var.vm_config.user_account_keys_file
}
