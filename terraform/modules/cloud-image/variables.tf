variable "os_url" {
  description = "URL of the cloud image to download"
  default     = "https://cloud-images.ubuntu.com/resolute/current/resolute-server-cloudimg-amd64.img"
}

variable "file_name" {
  description = "Name of the file to save the cloud image as"
  default     = null
}