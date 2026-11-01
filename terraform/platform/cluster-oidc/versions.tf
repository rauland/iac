terraform {
  required_version = ">= 1.10.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.69.1"
    }
    http = {
      source  = "hashicorp/http"
      version = "3.5.0"
    }
  }
}
