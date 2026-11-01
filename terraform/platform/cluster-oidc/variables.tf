variable "aws_region" {
  type    = string
  default = "ap-southeast-2"
}

variable "bucket_name" {
  description = "Globally unique public bucket that serves each cluster's OIDC discovery documents."
  type        = string
  default     = "rauland-homelab-oidc"
}

variable "state_bucket" {
  description = "S3 bucket holding Terraform state, from which each cluster's API credentials are read."
  type        = string
}

variable "clusters" {
  description = "Clusters to publish, mapped to the state key of the Talos root that outputs kubernetes_client_configuration."
  type        = map(string)
  default = {
    dev = "terraform/dev/talos.tfstate"
  }

  validation {
    condition     = alltrue([for cluster in keys(var.clusters) : can(regex("^[a-z0-9-]+$", cluster))])
    error_message = "Cluster names may contain only lowercase letters, digits and hyphens."
  }
}
