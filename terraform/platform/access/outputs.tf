output "automation_credentials" {
  description = "Treat as secrets. Export only into a protected local file or GitHub environment secrets; token values are held in encrypted Terraform state."
  sensitive   = true
  value = {
    for name, token in proxmox_user_token.ci : name => {
      user_id    = token.user_id
      token_name = token.token_name
      token_id   = token.id
      secret     = split("=", token.value)[1]
      api_token  = token.value
    }
  }
}
