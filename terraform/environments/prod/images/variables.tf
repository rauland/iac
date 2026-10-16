variable "virtual_environment_endpoint" {
  type = string
}

variable "virtual_environment_api_token" {
  type      = string
  sensitive = true
}

variable "cloud_images" {
  description = "Cloud images to download; datastore_id must reference file-based storage with the selected content type enabled."
  type = map(object({
    url          = string
    node_names   = list(string)
    content_type = optional(string, "import")
    datastore_id = optional(string, "local")
  }))
}
