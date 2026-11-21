output "execution_role_arn" {
  value       = aws_iam_role.execution.arn
  description = "ECS Task Execution Role ARN"
}

output "task_role_arn" {
  value       = aws_iam_role.task.arn
  description = "ECS Task Runtime Role ARN"
}
