output "bucket" {
  description = "Bucket and endpoint for the clusters' restic repositories."
  value = {
    name     = aws_s3_bucket.offsite.bucket
    region   = var.aws_region
    endpoint = "s3.${var.aws_region}.amazonaws.com"
  }
}

output "cluster_users" {
  description = "IAM user per cluster, for creating its access key."
  value       = { for cluster, user in aws_iam_user.cluster : cluster => user.name }
}
