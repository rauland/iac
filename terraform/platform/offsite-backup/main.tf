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

# PBS prunes and garbage-collects its own chunks; object versions would keep
# deleted chunks billable without making them restorable through PBS.
resource "aws_s3_bucket_versioning" "offsite" {
  bucket = aws_s3_bucket.offsite.id
  versioning_configuration {
    status = "Disabled"
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

# PBS authenticates to S3 only with a static access key, so this is the one IAM
# user in the account. It can reach this bucket and nothing else. The key is
# created outside Terraform so its secret never enters state; see the README.
resource "aws_iam_user" "pbs" {
  name = "pbs-offsite"
  path = "/homelab/"
}

locals {
  bucket_arn = "arn:aws:s3:::${var.bucket_name}"
  pbs_policy = {
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ListBucket"
        Effect   = "Allow"
        Action   = ["s3:ListBucket", "s3:GetBucketLocation"]
        Resource = [local.bucket_arn]
      },
      {
        Sid      = "ManageChunks"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = ["${local.bucket_arn}/*"]
      },
    ]
  }
}

resource "aws_iam_user_policy" "pbs" {
  name   = "pbs-offsite-bucket"
  user   = aws_iam_user.pbs.name
  policy = jsonencode(local.pbs_policy)
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
