variable "deferred_vm_tags" {
  description = "Internal staging selectors (node/name). Leave empty for the final configuration."
  type        = set(string)
  default     = []
}
