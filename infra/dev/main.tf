resource "aws_sqs_queue" "dead_letter" {
  name                      = "${local.prefix}-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "review" {
  name                       = "${local.prefix}-jobs"
  visibility_timeout_seconds = 5400
  message_retention_seconds  = 345600
  sqs_managed_sse_enabled    = true
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.dead_letter.arn, maxReceiveCount = 3 })
}

resource "aws_sqs_queue_redrive_allow_policy" "dead_letter" {
  queue_url            = aws_sqs_queue.dead_letter.id
  redrive_allow_policy = jsonencode({ redrivePermission = "byQueue", sourceQueueArns = [aws_sqs_queue.review.arn] })
}

resource "aws_dynamodb_table" "deliveries" {
  name         = "${local.prefix}-deliveries"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "delivery_id"
  attribute {
    name = "delivery_id"
    type = "S"
  }
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

resource "aws_dynamodb_table" "runs" {
  name         = "${local.prefix}-runs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"
  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }
}

resource "aws_secretsmanager_secret" "webhook" {
  name                    = "${local.prefix}/webhook-secret"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret" "private_key" {
  name                    = "${local.prefix}/github-private-key"
  recovery_window_in_days = 7
}

resource "aws_cloudwatch_log_group" "ingress" {
  name              = "/aws/lambda/${local.prefix}-ingress"
  retention_in_days = 14
}

resource "aws_iam_role" "ingress" {
  name                 = "${local.prefix}-ingress"
  permissions_boundary = var.permissions_boundary_arn
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "ingress" {
  name = "project-runtime"
  role = aws_iam_role.ingress.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = aws_secretsmanager_secret.webhook.arn },
      { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"], Resource = aws_dynamodb_table.deliveries.arn },
      { Effect = "Allow", Action = ["dynamodb:PutItem"], Resource = aws_dynamodb_table.runs.arn },
      { Effect = "Allow", Action = ["sqs:SendMessage"], Resource = aws_sqs_queue.review.arn },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.ingress.arn}:*" }
    ]
  })
}

resource "aws_lambda_function" "ingress" {
  function_name    = "${local.prefix}-ingress"
  role             = aws_iam_role.ingress.arn
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  handler          = "handler.lambda_handler"
  memory_size      = 512
  timeout          = 5
  filename         = "${path.module}/../../.build/ingress.zip"
  source_code_hash = fileexists("${path.module}/../../.build/ingress.zip") ? filebase64sha256("${path.module}/../../.build/ingress.zip") : null
  environment {
    variables = {
      TRIGGER            = var.trigger
      QUEUE_URL          = aws_sqs_queue.review.id
      DELIVERIES_TABLE   = aws_dynamodb_table.deliveries.name
      RUNS_TABLE         = aws_dynamodb_table.runs.name
      WEBHOOK_SECRET_ARN = aws_secretsmanager_secret.webhook.arn
    }
  }
  depends_on = [aws_iam_role_policy.ingress, aws_cloudwatch_log_group.ingress]
}

resource "aws_apigatewayv2_api" "webhook" {
  name          = local.prefix
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "ingress" {
  api_id                 = aws_apigatewayv2_api.webhook.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.ingress.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 6000
}

resource "aws_apigatewayv2_route" "webhook" {
  api_id    = aws_apigatewayv2_api.webhook.id
  route_key = "POST /webhook"
  target    = "integrations/${aws_apigatewayv2_integration.ingress.id}"
}

resource "aws_apigatewayv2_stage" "dev" {
  api_id      = aws_apigatewayv2_api.webhook.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "gateway" {
  statement_id  = "AllowWebhookGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingress.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.webhook.execution_arn}/*/POST/webhook"
}
