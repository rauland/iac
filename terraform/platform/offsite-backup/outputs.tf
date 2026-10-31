output "bucket" {
  description = "Bucket and endpoint for the PBS S3 endpoint configuration."
  value = {
    name     = aws_s3_bucket.offsite.bucket
    region   = var.aws_region
    endpoint = "s3.${var.aws_region}.amazonaws.com"
  }
}

output "pbs_user" {
  value = aws_iam_user.pbs.name
}
