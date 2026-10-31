mock_provider "aws" {}

run "bucket_is_private_and_pbs_is_scoped" {
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
    condition = alltrue([
      for statement in local.pbs_policy.Statement : alltrue([
        for action in statement.Action : contains(["s3:ListBucket", "s3:GetBucketLocation", "s3:GetObject", "s3:PutObject", "s3:DeleteObject"], action)
        ]) && alltrue([
        for resource in statement.Resource : startswith(resource, "arn:aws:s3:::${var.bucket_name}")
      ])
    ])
    error_message = "PBS may only read, write and delete objects in its own bucket."
  }
  assert {
    condition     = length(aws_budgets_budget.monthly) == 0
    error_message = "The budget is created only when an alert address is given."
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
