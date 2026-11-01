mock_provider "aws" {}

variables {
  state_bucket = "state.example"
}

override_data {
  target = data.terraform_remote_state.cluster_oidc
  values = {
    outputs = {
      clusters = {
        dev = {
          issuer       = "https://oidc.example/dev"
          provider     = "oidc.example/dev"
          provider_arn = "arn:aws:iam::111111111111:oidc-provider/oidc.example/dev"
        }
        prod = {
          issuer       = "https://oidc.example/prod"
          provider     = "oidc.example/prod"
          provider_arn = "arn:aws:iam::111111111111:oidc-provider/oidc.example/prod"
        }
      }
    }
  }
}

run "bucket_is_private_and_clusters_are_scoped" {
  command = plan

  assert {
    condition = (
      aws_s3_bucket_public_access_block.backups.block_public_acls &&
      aws_s3_bucket_public_access_block.backups.block_public_policy &&
      aws_s3_bucket_public_access_block.backups.ignore_public_acls &&
      aws_s3_bucket_public_access_block.backups.restrict_public_buckets
    )
    error_message = "The backup bucket must block all public access."
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
    condition     = aws_s3_bucket_versioning.backups.versioning_configuration[0].status == "Enabled"
    error_message = "Versioning keeps objects deleted with a cluster key recoverable."
  }
  assert {
    condition     = keys(aws_iam_role.cluster) == ["dev"]
    error_message = "Only the dev cluster has a backup role by default."
  }
  assert {
    condition = (
      local.cluster_trust["dev"].Statement[0].Principal.Federated == "arn:aws:iam::111111111111:oidc-provider/oidc.example/dev" &&
      local.cluster_trust["dev"].Statement[0].Condition.StringEquals["oidc.example/dev:aud"] == "sts.amazonaws.com" &&
      alltrue([for sub in local.cluster_trust["dev"].Statement[0].Condition.StringLike["oidc.example/dev:sub"] : startswith(sub, "system:serviceaccount:*:volsync-")])
    )
    error_message = "Only VolSync movers of the cluster, with the STS audience, may assume its role."
  }
  assert {
    condition     = length(aws_budgets_budget.monthly) == 0
    error_message = "The budget is created only when an alert address is given."
  }
}

run "one_role_per_cluster" {
  command = plan
  variables {
    clusters = ["dev", "prod"]
  }

  assert {
    condition     = aws_iam_role.cluster["prod"].name == "backup-prod" && local.cluster_trust["prod"].Statement[0].Principal.Federated == "arn:aws:iam::111111111111:oidc-provider/oidc.example/prod"
    error_message = "Each cluster gets its own role, trusting only its own identity provider."
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
