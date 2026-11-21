output "monitoring_security_group_id" {
  value       = aws_security_group.monitoring.id
  description = "Security Group ID of the monitoring tier"
}

output "telemetry_archive_bucket" {
  value       = aws_s3_bucket.telemetry_archive.bucket
  description = "S3 bucket for cold telemetry and trace archives"
}
