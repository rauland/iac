variable "state_bucket" {
  description = "S3 bucket holding Terraform state; CI sets it from the TF_STATE_BUCKET repository variable."
  type        = string
}

variable "flux_operator_version" {
  description = "Pinned flux-operator and flux-instance chart release."
  type        = string
  validation {
    condition     = can(regex("^[0-9]+[.][0-9]+[.][0-9]+$", var.flux_operator_version))
    error_message = "flux_operator_version must be a pinned chart release such as 0.62.1."
  }
}

variable "flux_version" {
  description = "Pinned Flux distribution installed by the operator."
  type        = string
  validation {
    condition     = can(regex("^[0-9]+[.][0-9]+[.][0-9]+$", var.flux_version))
    error_message = "flux_version must be a pinned release such as 2.10.0."
  }
}

variable "sync_url" {
  description = "Public HTTPS Git repository Flux reconciles from. Private repositories also need a pull secret."
  type        = string
  validation {
    condition     = startswith(var.sync_url, "https://")
    error_message = "sync_url must be an HTTPS Git URL."
  }
}

variable "sync_ref" {
  description = "Git reference Flux follows; keep it on the protected main branch."
  type        = string
  default     = "refs/heads/main"
}

variable "sync_path" {
  description = "Repository directory holding this cluster's manifests."
  type        = string
}
