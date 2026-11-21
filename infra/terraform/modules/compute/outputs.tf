output "cluster_id" {
  value       = aws_ecs_cluster.main.id
  description = "ECS cluster identifier"
}

output "service_name" {
  value       = aws_ecs_service.api.name
  description = "ECS API service name"
}

output "target_group_arn" {
  value       = aws_lb_target_group.api.arn
  description = "Target group ARN for ALB attachment"
}
