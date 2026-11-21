# AutoHeal DevOps — Enterprise Hardened Redis Cache & Broker Module
# Multi-node replication group, in-transit encryption (TLS), at-rest encryption, and automated failover.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

resource "aws_elasticache_subnet_group" "redis" {
  name        = "autoheal-redis-sng-${var.environment}"
  subnet_ids  = var.subnet_ids
  description = "Subnet group for Redis clusters"

  tags = merge(var.tags, {
    Name        = "autoheal-redis-sng-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_security_group" "redis" {
  name        = "autoheal-sg-redis-${var.environment}"
  description = "Controls ingress to Redis cache and task broker"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Redis access from compute tier only"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [var.compute_security_group_id]
  }

  egress {
    description = "No outbound initiated from Redis"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["127.0.0.1/32"]
  }

  tags = merge(var.tags, {
    Name        = "autoheal-sg-redis-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "autoheal-redis-${var.environment}"
  description                = "AutoHeal Celery & caching replication group"
  node_type                  = var.node_type
  num_cache_clusters         = var.num_cache_nodes
  parameter_group_name       = "default.redis7"
  port                       = 6379
  subnet_group_name          = aws_elasticache_subnet_group.redis.name
  security_group_ids         = [aws_security_group.redis.id]
  automatic_failover_enabled = true
  multi_az_enabled           = true

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  snapshot_retention_limit = 7
  snapshot_window          = "02:00-03:00"
  maintenance_window       = "Sun:03:30-Sun:04:30"

  auto_minor_version_upgrade = true

  tags = merge(var.tags, {
    Name        = "autoheal-redis-${var.environment}"
    Environment = var.environment
  })
}
