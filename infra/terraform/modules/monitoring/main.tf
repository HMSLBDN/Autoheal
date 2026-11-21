# AutoHeal DevOps — Enterprise Monitoring & Observability Module
# OpenTelemetry Collector and Prometheus monitoring infrastructure resources.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

resource "aws_security_group" "monitoring" {
  name        = "autoheal-sg-monitoring-${var.environment}"
  description = "Allows OTLP ingress from compute tier"
  vpc_id      = var.vpc_id

  ingress {
    description     = "OTLP gRPC from compute"
    from_port       = 4317
    to_port         = 4317
    protocol        = "tcp"
    security_groups = [var.compute_security_group_id]
  }

  ingress {
    description     = "OTLP HTTP from compute"
    from_port       = 4318
    to_port         = 4318
    protocol        = "tcp"
    security_groups = [var.compute_security_group_id]
  }

  egress {
    description = "Outbound to internet via NAT"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name        = "autoheal-sg-monitoring-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_s3_bucket" "telemetry_archive" {
  bucket        = "autoheal-telemetry-archive-${var.environment}"
  force_destroy = var.environment == "prod" ? false : true

  tags = merge(var.tags, {
    Name        = "autoheal-telemetry-archive-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_s3_bucket_lifecycle_configuration" "archive_lifecycle" {
  bucket = aws_s3_bucket.telemetry_archive.id

  rule {
    id     = "expire-traces-after-90-days"
    status = "Enabled"

    expiration {
      days = 90
    }
  }
}
