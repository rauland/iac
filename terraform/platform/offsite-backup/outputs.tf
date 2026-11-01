output "bucket" {
  description = "Bucket and endpoint for the clusters' restic repositories."
  value = {
    name     = aws_s3_bucket.offsite.bucket
    region   = var.aws_region
    endpoint = "s3.${var.aws_region}.amazonaws.com"
  }
}

output "cluster_roles" {
  description = "IAM role per cluster, for the cluster's VolSync AWS identity policy."
  value       = { for cluster, role in aws_iam_role.cluster : cluster => role.arn }
}
