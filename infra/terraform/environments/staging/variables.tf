variable "aws_region" {
  type        = string
  description = "AWS deployment region"
  default     = "us-east-1"
}

variable "environment" {
  type        = string
  description = "Deployment environment"
  default     = "staging"
}

variable "vpc_cidr" {
  type        = string
  default     = "10.20.0.0/16"
}
