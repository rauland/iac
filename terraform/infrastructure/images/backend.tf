terraform {
  backend "s3" {
    bucket         = "rauland-iac-homelab"   
    key            = "terraform/images/terraform.tfstate"  
    region         = "ap-southeast-2"        
    encrypt        = true                     
    use_lockfile   = true
  }
}
