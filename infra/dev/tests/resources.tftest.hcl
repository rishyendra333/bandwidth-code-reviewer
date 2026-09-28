mock_provider "aws" {
  mock_resource "aws_apigatewayv2_api" {
    defaults = { execution_arn = "arn:aws:execute-api:us-west-2:516647891652:example" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::516647891652:role/bandwidth-reviewer-dev-ingress" }
  }
  mock_resource "aws_lambda_function" {
    defaults = {
      arn        = "arn:aws:lambda:us-west-2:516647891652:function:bandwidth-reviewer-dev-ingress"
      invoke_arn = "arn:aws:apigateway:us-west-2:lambda:path/2015-03-31/functions/arn:aws:lambda:us-west-2:516647891652:function:bandwidth-reviewer-dev-ingress/invocations"
    }
  }
}

run "week1_resources" {
  command = apply
  variables {
    hosting_account_id = "516647891652"
    teammate_user_arns = ["arn:aws:iam::111122223333:user/teammate"]
  }
  assert {
    condition     = aws_sqs_queue.review.visibility_timeout_seconds == 5400 && aws_sqs_queue.review.message_retention_seconds == 345600
    error_message = "Queue timing must support the planned 15-minute worker."
  }
  assert {
    condition     = jsondecode(aws_sqs_queue.review.redrive_policy).maxReceiveCount == 3 && aws_sqs_queue.dead_letter.message_retention_seconds == 1209600
    error_message = "Retries and DLQ retention must match the runbook."
  }
  assert {
    condition     = aws_dynamodb_table.deliveries.ttl[0].enabled && aws_dynamodb_table.deliveries.ttl[0].attribute_name == "expires_at" && aws_dynamodb_table.runs.range_key == "sk"
    error_message = "Delivery expiry and installation/run history keys are required."
  }
  assert {
    condition     = aws_lambda_function.ingress.runtime == "python3.12" && aws_lambda_function.ingress.memory_size == 512 && aws_lambda_function.ingress.timeout == 5
    error_message = "Ingress must use the agreed short request runtime."
  }
  assert {
    condition     = jsondecode(aws_iam_role.inspect[0].assume_role_policy).Statement[0].Principal.AWS == ["arn:aws:iam::111122223333:user/teammate"]
    error_message = "Inspection must trust only the supplied identity."
  }
  assert {
    condition     = alltrue([for statement in jsondecode(aws_iam_role_policy.inspect[0].policy).Statement : !contains(statement.Action, "secretsmanager:GetSecretValue") && !contains(statement.Action, "s3:GetObject") && !contains(statement.Action, "sqs:ReceiveMessage")])
    error_message = "Inspectors cannot read secrets/state or consume jobs."
  }
}

run "unconfigured_inspection" {
  command = plan
  variables {
    hosting_account_id = "516647891652"
    teammate_user_arns = []
  }
  assert {
    condition     = length(aws_iam_role.inspect) == 0
    error_message = "Missing teammate identities must not create broad trust."
  }
}

run "reject_account_principal" {
  command = plan
  variables {
    hosting_account_id = "516647891652"
    teammate_user_arns = ["arn:aws:iam::111122223333:root"]
  }
  expect_failures = [var.teammate_user_arns]
}

run "reject_invalid_account" {
  command = plan
  variables { hosting_account_id = "not-an-account" }
  expect_failures = [var.hosting_account_id]
}
