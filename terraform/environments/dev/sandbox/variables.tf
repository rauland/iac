variable "virtual_environment_endpoint" {
  type = string
}

variable "virtual_environment_api_token" {
  type      = string
  sensitive = true
}

variable "vms" {
  type = map(object({
    vm_name                = string
    node_name              = string
    tags                   = list(string)
    cpu                    = optional(number)
    memory                 = optional(number)
    image_datastore_id     = optional(string, "local")
    image_file_name        = string
  }))
}
