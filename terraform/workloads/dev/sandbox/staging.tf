variable "deferred_vm_tags" {
  description = "Internal CI staging selectors; leave empty for the final configuration."
  type        = set(string)
  default     = []
}
