locals {
  identities = merge([
    for scope in ["dev", "prod"] : {
      for operation in ["plan", "apply"] :
      "tf-${scope}-${operation}" => {
        scope     = scope
        operation = operation
        state_key = "terraform/${scope}/*.tfstate"
        # GitHub environments whose OIDC tokens may assume this identity's role.
        github_environments = concat(
          ["proxmox-${scope}-${operation}"],
          scope == "dev" && operation == "apply" ? ["proxmox-dev-auto-apply"] : [],
        )
        # SSM parameter prefixes under /iac whose values CI may read.
        parameter_paths = concat(
          ["shared/proxmox", "shared/wireguard", "${scope}/${operation}"],
          operation == "apply" ? ["shared/apply"] : [],
          operation == "apply" ? ["${scope}/flux"] : [],
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
        ], [
        {
          # Values are SecureStrings under the AWS-managed aws/ssm key, whose key
          # policy already allows decryption through SSM for this account.
          Sid    = "ReadOwnParameters"
          Effect = "Allow"
          Action = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
          Resource = flatten([
            for path in identity.parameter_paths : [
              "arn:aws:ssm:${var.aws_region}:*:parameter/iac/${path}",
              "arn:aws:ssm:${var.aws_region}:*:parameter/iac/${path}/*",
            ]
          ])
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
