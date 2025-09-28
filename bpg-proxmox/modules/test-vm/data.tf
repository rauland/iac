data "local_file" "ssh_public_key" {
  filename = "./ssh/ansible_id_rsa.pub"
}