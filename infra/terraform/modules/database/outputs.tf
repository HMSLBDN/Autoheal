output "endpoint" {
  value       = aws_db_instance.postgres.endpoint
  description = "Connection endpoint for PostgreSQL primary"
}

output "database_name" {
  value       = aws_db_instance.postgres.db_name
  description = "Database name"
}

output "port" {
  value       = aws_db_instance.postgres.port
  description = "PostgreSQL listening port"
}

output "security_group_id" {
  value       = aws_security_group.db.id
  description = "Security Group ID of the database"
}
