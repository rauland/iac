variable "aws_region" {
  type    = string
  default = "ap-southeast-2"
}

variable "bucket_name" {
  description = "Globally unique bucket that holds the clusters' restic repositories."
  type        = string
  default     = "rauland-homelab-backups"
}

variable "state_bucket" {
  description = "S3 bucket holding Terraform state, from which platform/cluster-oidc's identity providers are read."
  type        = string
}

variable "clusters" {
  description = "Clusters that back up to the bucket. Each gets an IAM role limited to the <cluster>/ prefix; each must be published by platform/cluster-oidc."
  type        = list(string)
  default     = ["dev"]

  validation {
    condition     = alltrue([for cluster in var.clusters : can(regex("^[a-z0-9-]+$", cluster))])
    error_message = "Cluster names may contain only lowercase letters, digits and hyphens."
  }
}

variable "deleted_retention_days" {
  description = "Days that deleted or overwritten objects stay recoverable as noncurrent versions."
  type        = number
  default     = 30
}

variable "budget_limit_usd" {
  description = "Monthly account spend that triggers an email alert."
  type        = number
  default     = 15
}

variable "budget_email" {
  description = "Address for the monthly spend alert. Leave null to skip the budget."
  type        = string
  default     = null
}
