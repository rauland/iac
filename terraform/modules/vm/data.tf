data "local_file" "ssh_public_key" {
  filename = var.user_account_keys_file
}