resource "aws_s3_bucket" "offsite" {
  bucket = var.bucket_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_ownership_controls" "offsite" {
  bucket = aws_s3_bucket.offsite.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "offsite" {
  bucket                  = aws_s3_bucket.offsite.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "offsite" {
  bucket = aws_s3_bucket.offsite.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# A cluster's key can delete objects, because restic's prune must. Versioning
# keeps deleted or overwritten objects for deleted_retention_days, so a stolen
# key cannot destroy the backups before someone notices.
resource "aws_s3_bucket_versioning" "offsite" {
  bucket = aws_s3_bucket.offsite.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "offsite" {
  bucket = aws_s3_bucket.offsite.id
  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
  rule {
    id     = "expire-deleted-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = var.deleted_retention_days
    }
    expiration {
      expired_object_delete_marker = true
    }
  }
  depends_on = [aws_s3_bucket_versioning.offsite]
}

resource "aws_s3_bucket_policy" "offsite" {
  bucket = aws_s3_bucket.offsite.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.offsite.arn, "${aws_s3_bucket.offsite.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.offsite]
}

# restic authenticates to S3 with a static access key, so each cluster gets one
# IAM user, limited to its own prefix in this bucket. The keys are created
# outside Terraform so their secrets never enter state; see the README.
resource "aws_iam_user" "cluster" {
  for_each = toset(var.clusters)
  name     = "backup-${each.key}"
  path     = "/homelab/"
}

locals {
  bucket_arn = "arn:aws:s3:::${var.bucket_name}"
  cluster_policies = {
    for cluster in var.clusters : cluster => {
      Version = "2012-10-17"
      Statement = [
        {
          Sid       = "ListOwnPrefix"
          Effect    = "Allow"
          Action    = ["s3:ListBucket"]
          Resource  = [local.bucket_arn]
          Condition = { StringLike = { "s3:prefix" = ["${cluster}/*"] } }
        },
        {
          Sid      = "LocateBucket"
          Effect   = "Allow"
          Action   = ["s3:GetBucketLocation"]
          Resource = [local.bucket_arn]
        },
        {
          Sid      = "ManageOwnObjects"
          Effect   = "Allow"
          Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
          Resource = ["${local.bucket_arn}/${cluster}/*"]
        },
      ]
    }
  }
}

resource "aws_iam_user_policy" "cluster" {
  for_each = aws_iam_user.cluster
  name     = "backup-${each.key}-prefix"
  user     = each.value.name
  policy   = jsonencode(local.cluster_policies[each.key])
}

resource "aws_budgets_budget" "monthly" {
  count        = var.budget_email == null ? 0 : 1
  name         = "homelab-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    notification_type          = "FORECASTED"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    subscriber_email_addresses = [var.budget_email]
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    notification_type          = "ACTUAL"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    subscriber_email_addresses = [var.budget_email]
  }
}
