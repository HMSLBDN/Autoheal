variable "environment" {
  type        = string
  description = "Target deployment environment"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID where the database is deployed"
}

variable "subnet_ids" {
  type        = list(string)
  description = "Private data subnet IDs for database subnet group"
}

variable "compute_security_group_id" {
  type        = string
  description = "Security Group ID of the compute layer allowed to connect"
}

variable "instance_class" {
  type        = string
  description = "Database instance compute class"
  default     = "db.r6g.large"
}

variable "allocated_storage" {
  type        = number
  description = "Allocated storage size in GiB"
  default     = 100
}

variable "max_allocated_storage" {
  type        = number
  description = "Maximum storage auto-scaling threshold in GiB"
  default     = 500
}

variable "multi_az" {
  type        = bool
  description = "Enable Multi-AZ high availability standby replication"
  default     = true
}

variable "backup_retention_days" {
  type        = number
  description = "Days of automated point-in-time recovery backup retention"
  default     = 30
}

variable "database_name" {
  type        = string
  description = "Name of the default PostgreSQL database"
  default     = "autoheal_production"
}

variable "tags" {
  type        = map(string)
  description = "Resource tags"
  default     = {}
}
