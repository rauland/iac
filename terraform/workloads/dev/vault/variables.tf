variable "virtual_environment_endpoint" {
  type = string
}

variable "virtual_environment_api_token" {
  ephemeral = true
  type      = string
  sensitive = true
}
