variable "virtual_environment_endpoint" {
  type = string
}

variable "virtual_environment_ssh_username" {
  type = string
}  

variable "virtual_environment_api_token" {
  type = string
  sensitive = true
}
