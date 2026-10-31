variable "aws_region" {
  type    = string
  default = "ap-southeast-2"
}

variable "bucket_name" {
  description = "Globally unique bucket that holds the Proxmox Backup Server off-site datastore."
  type        = string
  default     = "rauland-homelab-pbs-offsite"
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
