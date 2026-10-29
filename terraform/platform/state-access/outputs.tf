output "state_role_arns" {
  description = "Role ARN per identity; set each as the AWS_ROLE_ARN variable of its GitHub environments."
  value = {
    for name, identity in local.identities : name => {
      role_arn            = aws_iam_role.state[name].arn
      github_environments = identity.github_environments
    }
  }
}
