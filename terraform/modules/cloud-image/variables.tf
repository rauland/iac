variable "url" {
  description = "URL of the cloud image to download"
  default     = "https://repo.almalinux.org/almalinux/10/cloud/x86_64/images/AlmaLinux-10-GenericCloud-latest.x86_64.qcow2"
}

variable "file_name" {
  description = "Name of the file to save the cloud image as"
  default     = null
}

variable "content_type" {
  description = "Content type of the file to download"
  default     = "import"
}

variable "datastore_id" {
  description = "ID of a file-based datastore with the selected content type enabled (for example, local with import support)"
  default     = "local"
}

variable "node_names" {
  description = "List of nodes to upload the cloud image to"
  type        = list(string)
  default     = [null]
}

variable "upload_timeout" {
  description = "Timeout for the upload operation in seconds"
  default     = 1200
}
