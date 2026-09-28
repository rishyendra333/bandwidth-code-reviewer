resource "aws_iam_role" "inspect" {
  count                = length(var.teammate_user_arns) > 0 ? 1 : 0
  name                 = "${local.prefix}-inspect"
  permissions_boundary = var.permissions_boundary_arn
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { AWS = sort(tolist(var.teammate_user_arns)) }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "inspect" {
  count = length(aws_iam_role.inspect)
  name  = "project-inspection"
  role  = aws_iam_role.inspect[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["logs:DescribeLogStreams", "logs:GetLogEvents", "logs:FilterLogEvents", "logs:StartQuery"], Resource = "${aws_cloudwatch_log_group.ingress.arn}:*" },
      { Effect = "Allow", Action = ["logs:DescribeLogGroups", "logs:GetQueryResults", "logs:StopQuery", "cloudwatch:GetMetricData", "cloudwatch:GetMetricStatistics", "cloudwatch:ListMetrics"], Resource = "*" },
      { Effect = "Allow", Action = ["dynamodb:DescribeTable", "dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:Query", "dynamodb:Scan"], Resource = [aws_dynamodb_table.deliveries.arn, aws_dynamodb_table.runs.arn] },
      { Effect = "Allow", Action = ["sqs:GetQueueAttributes", "sqs:GetQueueUrl", "sqs:ListQueueTags"], Resource = [aws_sqs_queue.review.arn, aws_sqs_queue.dead_letter.arn] },
      { Effect = "Allow", Action = ["lambda:GetFunctionConfiguration", "lambda:GetPolicy", "lambda:ListTags"], Resource = aws_lambda_function.ingress.arn },
      { Effect = "Allow", Action = ["apigateway:GET"], Resource = ["arn:aws:apigateway:us-west-2::/apis/${aws_apigatewayv2_api.webhook.id}", "arn:aws:apigateway:us-west-2::/apis/${aws_apigatewayv2_api.webhook.id}/*"] }
    ]
  })
}
