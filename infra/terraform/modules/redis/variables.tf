variable "environment" {
  type        = string
  description = "Target deployment environment"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID where Redis is deployed"
}

variable "subnet_ids" {
  type        = list(string)
  description = "Private data subnet IDs for Redis subnet group"
}

variable "compute_security_group_id" {
  type        = string
  description = "Security Group ID of the compute instances allowed access"
}

variable "node_type" {
  type        = string
  description = "ElastiCache node instance type"
  default     = "cache.m6g.large"
}

variable "num_cache_nodes" {
  type        = number
  description = "Number of cache replica nodes"
  default     = 2
}

variable "tags" {
  type        = map(string)
  description = "Resource tags"
  default     = {}
}
