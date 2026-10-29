variable "aws_region" {
  type    = string
  default = "ap-southeast-2"
}

variable "state_bucket_name" {
  type    = string
  default = "rauland-iac-homelab"
}

variable "github_repository" {
  description = "Repository whose environment OIDC tokens may assume the state roles."
  type        = string
  default     = "rauland/iac"
}
