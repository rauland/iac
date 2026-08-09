terraform {
  backend "s3" {
    bucket       = "rauland-iac-homelab"
    # key          = "terraform/${var.environment}/${var.component}.tfstate"
    region       = "ap-southeast-2"
    encrypt      = true
    use_lockfile = true
  }
}
