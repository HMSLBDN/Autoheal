variable "environment" {
  type        = string
  description = "Target deployment environment"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID where the service runs"
}

variable "subnet_ids" {
  type        = list(string)
  description = "Private compute subnet IDs"
}

variable "compute_security_group_id" {
  type        = string
  description = "Security group for compute tasks"
}

variable "min_capacity" {
  type        = number
  description = "Minimum auto-scaling replica count"
  default     = 2
}

variable "max_capacity" {
  type        = number
  description = "Maximum auto-scaling replica count"
  default     = 10
}

variable "desired_capacity" {
  type        = number
  description = "Initial desired task count"
  default     = 2
}

variable "container_image" {
  type        = string
  description = "Docker image URI"
  default     = "autoheal/backend:latest"
}

variable "tags" {
  type        = map(string)
  description = "Resource tags"
  default     = {}
}
