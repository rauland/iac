output "clusters" {
  description = "Per cluster: the issuer, and the IAM identity provider that roles trust."
  value = {
    for cluster, issuer in local.issuers : cluster => {
      issuer       = issuer
      provider_arn = aws_iam_openid_connect_provider.cluster[cluster].arn
      # Prefix of the provider's condition keys, such as <provider>:sub.
      provider = trimprefix(issuer, "https://")
    }
  }
}
