output "hosting_account_id" { value = var.hosting_account_id }
output "region" { value = "us-west-2" }
output "webhook_url" { value = "${aws_apigatewayv2_api.webhook.api_endpoint}/webhook" }
output "queue_url" { value = aws_sqs_queue.review.id }
output "queue_arn" { value = aws_sqs_queue.review.arn }
output "dead_letter_queue_url" { value = aws_sqs_queue.dead_letter.id }
output "deliveries_table" { value = aws_dynamodb_table.deliveries.name }
output "runs_table" { value = aws_dynamodb_table.runs.name }
output "webhook_secret_arn" { value = aws_secretsmanager_secret.webhook.arn }
output "github_private_key_arn" { value = aws_secretsmanager_secret.private_key.arn }
output "inspection_role_arn" { value = try(aws_iam_role.inspect[0].arn, null) }
output "inspection_console_url" {
  value = length(aws_iam_role.inspect) > 0 ? "https://signin.aws.amazon.com/switchrole?account=${var.hosting_account_id}&roleName=${aws_iam_role.inspect[0].name}&displayName=BandwidthDev" : null
}
output "trigger" { value = var.trigger }
output "log_group" { value = aws_cloudwatch_log_group.ingress.name }
