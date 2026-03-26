data "terraform_remote_state" "images" {
  backend = "s3"
  config = {
    bucket = "rauland-iac-homelab"
    key    = "terraform/images/terraform.tfstate"
    region = "ap-southeast-2"
  }
}

# data.terraform_remote_state.images.module.cloud_images.ids

