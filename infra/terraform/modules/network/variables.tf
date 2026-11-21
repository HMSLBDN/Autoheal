variable "environment" {
  type        = string
  description = "Target deployment environment (dev, staging, prod)"
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR block for the VPC"
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  type        = list(string)
  description = "List of availability zones for multi-AZ redundancy"
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "tags" {
  type        = map(string)
  description = "Resource tags applied to all network infrastructure"
  default     = {}
}
