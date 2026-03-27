terraform {
  backend "s3" {
    bucket       = "rauland-iac-homelab"
    key          = "terraform/compute/terraform.tfstate"
    region       = "ap-southeast-2"
    encrypt      = true
    use_lockfile = true
  }
}
