variable "url" {
  description = "URL of the cloud image to download"
  default     = "https://cloud-images.ubuntu.com/resolute/current/resolute-server-cloudimg-amd64.img"
}

variable "file_name" {
  description = "Name of the file to save the cloud image as"
  default     = null
}

variable "content_type" {
  description = "Content type of the file to download"
  default     = "iso"
}

variable "datastore_id" {
  description = "ID of the datastore to upload the cloud image to"
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
