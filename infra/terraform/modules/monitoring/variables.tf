variable "environment" {
  type        = string
  description = "Target deployment environment"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID where monitoring is deployed"
}

variable "subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs"
}

variable "compute_security_group_id" {
  type        = string
  description = "Compute tier security group ID"
}

variable "tags" {
  type        = map(string)
  description = "Resource tags"
  default     = {}
}
