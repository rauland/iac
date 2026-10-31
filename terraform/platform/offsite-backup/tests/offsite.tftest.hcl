mock_provider "aws" {}

run "bucket_is_private_and_clusters_are_scoped" {
  command = plan

  assert {
    condition = (
      aws_s3_bucket_public_access_block.offsite.block_public_acls &&
      aws_s3_bucket_public_access_block.offsite.block_public_policy &&
      aws_s3_bucket_public_access_block.offsite.ignore_public_acls &&
      aws_s3_bucket_public_access_block.offsite.restrict_public_buckets
    )
    error_message = "The off-site bucket must block all public access."
  }
  assert {
    condition = alltrue(flatten([
      for cluster, policy in local.cluster_policies : [
        for statement in policy.Statement : alltrue([
          for action in statement.Action : contains(["s3:ListBucket", "s3:GetBucketLocation", "s3:GetObject", "s3:PutObject", "s3:DeleteObject"], action)
          ]) && alltrue([
          for resource in statement.Resource : resource == "arn:aws:s3:::${var.bucket_name}" || resource == "arn:aws:s3:::${var.bucket_name}/${cluster}/*"
        ])
      ]
    ]))
    error_message = "A cluster may only list, read, write and delete objects under its own prefix."
  }
  assert {
    condition = alltrue([
      for cluster, policy in local.cluster_policies : alltrue([
        for statement in policy.Statement : statement.Condition.StringLike["s3:prefix"] == ["${cluster}/*"]
        if contains(statement.Action, "s3:ListBucket")
      ])
    ])
    error_message = "Listing is limited to the cluster's own prefix."
  }
  assert {
    condition     = aws_s3_bucket_versioning.offsite.versioning_configuration[0].status == "Enabled"
    error_message = "Versioning keeps objects deleted with a cluster key recoverable."
  }
  assert {
    condition     = keys(aws_iam_user.cluster) == ["dev"]
    error_message = "Only the dev cluster has a backup user by default."
  }
  assert {
    condition     = length(aws_budgets_budget.monthly) == 0
    error_message = "The budget is created only when an alert address is given."
  }
}

run "one_user_per_cluster" {
  command = plan
  variables {
    clusters = ["dev", "prod"]
  }

  assert {
    condition     = aws_iam_user.cluster["prod"].name == "backup-prod"
    error_message = "Each cluster gets its own IAM user."
  }
  assert {
    condition     = local.cluster_policies["prod"].Statement[2].Resource == ["arn:aws:s3:::${var.bucket_name}/prod/*"]
    error_message = "The prod user reaches only the prod prefix."
  }
}

run "budget_with_email" {
  command = plan
  variables {
    budget_email = "alerts@example.invalid"
  }

  assert {
    condition     = length(aws_budgets_budget.monthly) == 1 && aws_budgets_budget.monthly[0].limit_amount == "15"
    error_message = "A budget email creates the monthly spend alert."
  }
}
