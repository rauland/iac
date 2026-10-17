output "state_credentials" {
  description = "Sensitive AWS state credentials. Keep this root's state administrator-only."
  sensitive   = true
  value = {
    for name, key in aws_iam_access_key.state : name => {
      access_key_id     = key.id
      secret_access_key = key.secret
    }
  }
}
