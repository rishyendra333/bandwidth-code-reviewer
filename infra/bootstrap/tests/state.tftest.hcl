mock_provider "aws" {}

run "state_protection" {
  command = apply
  variables { hosting_account_id = "516647891652" }
  assert {
    condition     = aws_s3_bucket.state.bucket == "bandwidth-reviewer-tfstate-516647891652-us-west-2" && !aws_s3_bucket.state.force_destroy
    error_message = "State must be account-specific and protected from forced deletion."
  }
  assert {
    condition     = aws_s3_bucket_versioning.state.versioning_configuration[0].status == "Enabled" && aws_s3_bucket_public_access_block.state.block_public_policy
    error_message = "State recovery and public access protection are required."
  }
  assert {
    condition     = jsondecode(aws_s3_bucket_policy.state.policy).Statement[0].Condition.Bool["aws:SecureTransport"] == "false"
    error_message = "State access must require TLS."
  }
}
