variable "iso_url" {
  description = "URL of the ISO image to be downloaded"
  type        = string
  default     = "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
}

variable "node_name" {
  description = "Name of PVE node where the ISO image will be downloaded"
  type        = string
}
