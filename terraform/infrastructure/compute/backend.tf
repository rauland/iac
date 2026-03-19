terraform {
  backend "s3" {
    bucket         = "s3-iac-rauland"   
    key            = "terraform/compute/terraform.tfstate"  
    region         = "ap-southeast-2"        
    encrypt        = true                     
    # dynamodb_table = "terraform-locks"       # optional: for state locking
  }
}
