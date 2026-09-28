terraform {
  backend "s3" {}
  required_version = ">= 1.10, < 2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region              = "us-west-2"
  allowed_account_ids = [var.hosting_account_id]
  default_tags {
    tags = { Project = "bandwidth-reviewer", Environment = "dev", Owner = "deployment-owner" }
  }
}

variable "hosting_account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.hosting_account_id))
    error_message = "Supply the 12-digit hosting account ID."
  }
}
