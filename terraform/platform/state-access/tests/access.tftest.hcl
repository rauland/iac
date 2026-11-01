mock_provider "aws" {}

run "state_scope_boundaries" {
  command = plan

  assert {
    condition = alltrue([
      for name, identity in local.identities :
      identity.state_key == "terraform/${identity.scope}/*.tfstate"
    ]) && toset(keys(local.identities)) == toset(["tf-dev-plan", "tf-dev-apply", "tf-prod-plan", "tf-prod-apply"])
    error_message = "Only dev and prod roles exist, each limited to its workload state prefix."
  }
  assert {
    condition = alltrue([
      for name, policy in local.policies : alltrue([
        for statement in policy.Statement : alltrue([
          for action in statement.Action : contains(["s3:ListBucket", "s3:GetBucketLocation", "s3:GetObject", "ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"], action)
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

run "oidc_trust_boundaries" {
  command = plan

  assert {
    condition = alltrue([
      for name, policy in local.trust_policies : alltrue([
        for statement in policy.Statement :
        statement.Action == "sts:AssumeRoleWithWebIdentity" &&
        statement.Condition.StringEquals["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
      ])
    ])
    error_message = "Roles may only be assumed through GitHub OIDC tokens issued for AWS STS."
  }
  assert {
    condition = alltrue([
      for name, policy in local.trust_policies : alltrue([
        for statement in policy.Statement : alltrue([
          for subject in statement.Condition.StringEquals["token.actions.githubusercontent.com:sub"] :
          startswith(subject, "repo:rauland/iac:environment:proxmox-${local.identities[name].scope}-")
        ])
      ])
    ])
    error_message = "Each role must trust only protected environments of its own scope, never branches or pull requests."
  }
  assert {
    condition = alltrue([
      for name, identity in local.identities : alltrue([
        for environment in identity.github_environments : endswith(environment, "-plan")
      ]) if identity.operation == "plan"
    ])
    error_message = "Plan roles must not trust apply environments."
  }
  assert {
    condition = (
      local.identities["tf-dev-apply"].github_environments == ["proxmox-dev-apply", "proxmox-dev-auto-apply"] &&
      local.identities["tf-prod-apply"].github_environments == ["proxmox-prod-apply"]
    )
    error_message = "Only dev apply may be assumed from the automatic deployment environment."
  }
  assert {
    condition = alltrue([
      for name, role in aws_iam_role.state : role.max_session_duration == 3600
    ])
    error_message = "Role sessions must stay short-lived."
  }
}

run "parameter_read_boundaries" {
  command = plan

  assert {
    condition = alltrue([
      for name, policy in local.policies : alltrue([
        for statement in policy.Statement : alltrue([
          for action in statement.Action : startswith(action, "ssm:Get")
        ]) if anytrue([for action in statement.Action : startswith(action, "ssm:")])
      ])
    ])
    error_message = "CI roles may only read parameters, never write or delete them."
  }
  assert {
    condition = alltrue([
      for name, identity in local.identities : alltrue([
        for path in identity.parameter_paths :
        startswith(path, "shared/") || startswith(path, "${identity.scope}/")
      ])
    ])
    error_message = "A role may read only shared parameters and its own scope, never another environment's."
  }
  assert {
    condition = alltrue([
      for name, identity in local.identities : alltrue([
        for path in identity.parameter_paths :
        !contains(["shared/apply", "${identity.scope}/apply", "${identity.scope}/flux"], path)
      ]) if identity.operation == "plan"
    ])
    error_message = "Plan roles must not read apply secrets (plan key, apply tokens, or the SOPS key)."
  }
  assert {
    condition = (
      local.identities["tf-prod-apply"].parameter_paths == ["shared/proxmox", "shared/wireguard", "prod/apply", "shared/apply", "prod/flux"] &&
      contains(local.identities["tf-dev-apply"].parameter_paths, "dev/flux") &&
      local.identities["tf-dev-plan"].parameter_paths == ["shared/proxmox", "shared/wireguard", "dev/plan"]
    )
    error_message = "Unexpected parameter paths for the sample roles."
  }
  assert {
    condition = alltrue([
      for name, policy in local.policies : alltrue([
        for statement in policy.Statement : alltrue([
          for resource in statement.Resource : startswith(resource, "arn:aws:ssm:ap-southeast-2:*:parameter/iac/")
        ]) if statement.Sid == "ReadOwnParameters"
      ])
    ])
    error_message = "Parameter access must stay under /iac in the state region."
  }
}
