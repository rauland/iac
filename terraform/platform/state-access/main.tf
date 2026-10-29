locals {
  identities = merge([
    for scope in ["dev", "prod", "platform"] : {
      for operation in ["plan", "apply"] :
      (scope == "platform" ? "tf-platform-images-${operation}" : "tf-${scope}-${operation}") => {
        scope     = scope
        operation = operation
        state_key = scope == "platform" ? "terraform/platform/images.tfstate" : "terraform/${scope}/*.tfstate"
        # GitHub environments whose OIDC tokens may assume this identity's role.
        github_environments = concat(
          ["proxmox-${scope}-${operation}"],
          scope == "dev" && operation == "apply" ? ["proxmox-dev-auto-apply"] : [],
        )
      }
    }
  ]...)
  policies = {
    for name, identity in local.identities : name => {
      Version = "2012-10-17"
      Statement = concat([
        {
          Sid      = "ListBackendMetadata"
          Effect   = "Allow"
          Action   = ["s3:ListBucket", "s3:GetBucketLocation"]
          Resource = ["arn:aws:s3:::${var.state_bucket_name}"]
        },
        {
          Sid      = "ReadOwnState"
          Effect   = "Allow"
          Action   = ["s3:GetObject"]
          Resource = ["arn:aws:s3:::${var.state_bucket_name}/${identity.state_key}"]
        },
        {
          Sid         = "DenyObjectsOutsideOwnState"
          Effect      = "Deny"
          Action      = ["s3:GetObject*", "s3:PutObject*", "s3:DeleteObject*"]
          NotResource = ["arn:aws:s3:::${var.state_bucket_name}/${identity.state_key}", "arn:aws:s3:::${var.state_bucket_name}/${identity.state_key}.tflock"]
        }
        ], identity.operation == "apply" ? [
        {
          Sid      = "WriteOwnState"
          Effect   = "Allow"
          Action   = ["s3:PutObject"]
          Resource = ["arn:aws:s3:::${var.state_bucket_name}/${identity.state_key}"]
        },
        {
          Sid      = "ManageOwnLocks"
          Effect   = "Allow"
          Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
          Resource = ["arn:aws:s3:::${var.state_bucket_name}/${identity.state_key}.tflock"]
        }
        ] : [
        {
          Sid      = "DenyPlanWrites"
          Effect   = "Deny"
          Action   = ["s3:PutObject*", "s3:DeleteObject*"]
          Resource = ["*"]
        }
      ])
    }
  }

  trust_policies = {
    for name, identity in local.identities : name => {
      Version = "2012-10-17"
      Statement = [{
        Sid       = "GitHubEnvironmentOIDC"
        Effect    = "Allow"
        Action    = "sts:AssumeRoleWithWebIdentity"
        Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
            "token.actions.githubusercontent.com:sub" = [
              for environment in identity.github_environments :
              "repo:${var.github_repository}:environment:${environment}"
            ]
          }
        }
      }]
    }
  }
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

resource "aws_iam_role" "state" {
  for_each             = local.identities
  name                 = "iac-${each.key}"
  path                 = "/"
  max_session_duration = 3600
  assume_role_policy   = jsonencode(local.trust_policies[each.key])
}

resource "aws_iam_role_policy" "state" {
  for_each = local.identities
  name     = "terraform-state"
  role     = aws_iam_role.state[each.key].name
  policy   = jsonencode(local.policies[each.key])
}

resource "aws_iam_user" "state" {
  for_each = local.identities
  name     = "iac-${each.key}"
  path     = "/"
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_user_policy" "state" {
  for_each = local.identities
  name     = "terraform-state"
  user     = aws_iam_user.state[each.key].name
  policy   = jsonencode(local.policies[each.key])
}

resource "aws_iam_access_key" "state" {
  for_each   = local.identities
  user       = aws_iam_user.state[each.key].name
  status     = "Active"
  depends_on = [aws_iam_user_policy.state]
  lifecycle {
    prevent_destroy = true
  }
}
