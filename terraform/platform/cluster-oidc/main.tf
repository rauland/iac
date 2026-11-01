# Publishes each cluster's service account issuer, so AWS can verify tokens
# signed by a cluster whose API server is not reachable from the internet. The
# documents hold only public keys. Apply after the cluster serves the issuer
# set in its Talos root; see the README.
locals {
  issuers = {
    for cluster in keys(var.clusters) : cluster => "https://${var.bucket_name}.s3.${var.aws_region}.amazonaws.com/${cluster}"
  }
  documents = {
    for pair in setproduct(keys(var.clusters), [".well-known/openid-configuration", "openid/v1/jwks"]) :
    "${pair[0]}/${pair[1]}" => { cluster = pair[0], path = pair[1] }
  }
}

data "terraform_remote_state" "cluster" {
  for_each = var.clusters
  backend  = "s3"
  config = {
    bucket = var.state_bucket
    key    = each.value
    region = var.aws_region
  }
}

# Read from the API server with the administrator's client certificate, so the
# keys and key IDs are exactly what the cluster signs with.
data "http" "document" {
  for_each = local.documents

  url             = "${data.terraform_remote_state.cluster[each.value.cluster].outputs.kubernetes_client_configuration.host}/${each.value.path}"
  ca_cert_pem     = base64decode(data.terraform_remote_state.cluster[each.value.cluster].outputs.kubernetes_client_configuration.ca_certificate)
  client_cert_pem = base64decode(data.terraform_remote_state.cluster[each.value.cluster].outputs.kubernetes_client_configuration.client_certificate)
  client_key_pem  = base64decode(data.terraform_remote_state.cluster[each.value.cluster].outputs.kubernetes_client_configuration.client_key)

  lifecycle {
    postcondition {
      condition     = self.status_code == 200
      error_message = "The API server did not return ${each.value.path}."
    }
    postcondition {
      condition     = each.value.path != ".well-known/openid-configuration" || jsondecode(self.response_body).issuer == local.issuers[each.value.cluster]
      error_message = "The cluster's issuer is not ${local.issuers[each.value.cluster]}. Set service_account_issuer in its Talos root and apply that first."
    }
  }
}

resource "aws_s3_bucket" "oidc" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_ownership_controls" "oidc" {
  bucket = aws_s3_bucket.oidc.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Public reads come only from the bucket policy, which names the two documents
# of each cluster; ACLs stay blocked.
resource "aws_s3_bucket_public_access_block" "oidc" {
  bucket                  = aws_s3_bucket.oidc.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_server_side_encryption_configuration" "oidc" {
  bucket = aws_s3_bucket.oidc.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

locals {
  bucket_arn = "arn:aws:s3:::${var.bucket_name}"
  bucket_policy = {
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicDiscoveryDocuments"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = [for key in keys(local.documents) : "${local.bucket_arn}/${key}"]
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [local.bucket_arn, "${local.bucket_arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
    ]
  }
}

resource "aws_s3_bucket_policy" "oidc" {
  bucket     = aws_s3_bucket.oidc.id
  policy     = jsonencode(local.bucket_policy)
  depends_on = [aws_s3_bucket_public_access_block.oidc]
}

resource "aws_s3_object" "document" {
  for_each = local.documents

  bucket       = aws_s3_bucket.oidc.id
  key          = each.key
  content      = data.http.document[each.key].response_body
  content_type = "application/json"
}

# Tokens for AWS carry the audience sts.amazonaws.com; see the VolSync AWS
# identity policy in kubernetes/infrastructure/volsync.
resource "aws_iam_openid_connect_provider" "cluster" {
  for_each = local.issuers

  url            = each.value
  client_id_list = ["sts.amazonaws.com"]

  depends_on = [aws_s3_object.document, aws_s3_bucket_policy.oidc]
}
