variable "node_name" {
  description = "Name of PVE node where the ISO image will be downloaded"
  type        = string
}

variable "os" {
  description = "Operating system for the cloud image"
  default     = "ubuntu"
}
