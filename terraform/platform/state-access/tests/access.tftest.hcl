mock_provider "aws" {}

run "state_scope_boundaries" {
  command = plan

  assert {
    condition = alltrue([
      for name, identity in local.identities : identity.scope == "platform" ?
      identity.state_key == "terraform/platform/images.tfstate" :
      identity.state_key == "terraform/${identity.scope}/*.tfstate"
    ])
    error_message = "State access must be limited to the matching workload prefix or shared image state."
  }
  assert {
    condition = alltrue([
      for name, policy in local.policies : alltrue([
        for statement in policy.Statement : alltrue([
          for action in statement.Action : contains(["s3:ListBucket", "s3:GetBucketLocation", "s3:GetObject"], action)
        ]) if statement.Effect == "Allow"
      ]) if local.identities[name].operation == "plan"
    ])
    error_message = "Plan credentials cannot write state or acquire locks."
  }
  assert {
    condition = alltrue([
      for name, policy in local.policies : alltrue([
        for statement in policy.Statement : alltrue([
          for resource in try(statement.Resource, []) : endswith(resource, ".tflock")
        ]) if statement.Effect == "Allow" && contains(statement.Action, "s3:DeleteObject")
      ])
    ])
    error_message = "Apply credentials may delete lock files, never state files."
  }
}
