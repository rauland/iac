terraform {
  backend "s3" {
    bucket       = "rauland-iac-homelab"
    region       = "ap-southeast-2"
    encrypt      = true
    use_lockfile = true
  }
}
