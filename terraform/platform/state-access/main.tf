locals {
  identities = merge([
    for scope in ["dev", "prod", "platform"] : {
      for operation in ["plan", "apply"] :
      (scope == "platform" ? "tf-platform-images-${operation}" : "tf-${scope}-${operation}") => {
        scope     = scope
        operation = operation
        state_key = scope == "platform" ? "terraform/platform/images.tfstate" : "terraform/${scope}/*.tfstate"
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
