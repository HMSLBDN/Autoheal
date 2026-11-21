output "primary_endpoint_address" {
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
  description = "Redis cluster primary write endpoint"
}

output "reader_endpoint_address" {
  value       = aws_elasticache_replication_group.redis.reader_endpoint_address
  description = "Redis cluster reader endpoint"
}

output "port" {
  value       = aws_elasticache_replication_group.redis.port
  description = "Redis listening port"
}

output "security_group_id" {
  value       = aws_security_group.redis.id
  description = "Security Group ID of Redis"
}
