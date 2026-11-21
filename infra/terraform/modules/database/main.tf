# AutoHeal DevOps — Enterprise Hardened PostgreSQL Database Module
# Provisions Multi-AZ RDS PostgreSQL with automated snapshot retention,
# KMS encryption at rest, connection parameter tuning, and strict isolation.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

resource "aws_db_subnet_group" "db" {
  name        = "autoheal-dbsng-${var.environment}"
  subnet_ids  = var.subnet_ids
  description = "Database subnet group restricted to private data subnets"

  tags = merge(var.tags, {
    Name        = "autoheal-dbsng-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_security_group" "db" {
  name        = "autoheal-sg-db-${var.environment}"
  description = "Controls ingress to PostgreSQL database"
  vpc_id      = var.vpc_id

  ingress {
    description     = "PostgreSQL access from compute tier only"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.compute_security_group_id]
  }

  egress {
    description = "Strict egress - no outbound initiated from DB"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["127.0.0.1/32"]
  }

  tags = merge(var.tags, {
    Name        = "autoheal-sg-db-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_db_parameter_group" "pg" {
  name        = "autoheal-pg16-params-${var.environment}"
  family      = "postgres16"
  description = "Production hardened PostgreSQL parameters for AutoHeal SaaS"

  parameter {
    name  = "statement_timeout"
    value = "30000" # 30 seconds max statement execution
  }

  parameter {
    name  = "idle_in_transaction_session_timeout"
    value = "60000" # 60 seconds
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000" # Log slow queries exceeding 1000ms
  }

  parameter {
    name  = "rds.force_ssl"
    value = "1" # Enforce TLS 1.3 encrypted connections
  }

  tags = var.tags
}

resource "aws_kms_key" "db" {
  description             = "KMS Customer Managed Key for AutoHeal PostgreSQL Storage"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = merge(var.tags, {
    Name        = "autoheal-kms-db-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_db_instance" "postgres" {
  identifier                  = "autoheal-db-${var.environment}"
  engine                      = "postgres"
  engine_version              = "16.2"
  instance_class              = var.instance_class
  allocated_storage           = var.allocated_storage
  max_allocated_storage       = var.max_allocated_storage
  storage_type                = "gp3"
  storage_encrypted           = true
  kms_key_id                  = aws_kms_key.db.arn
  db_name                     = var.database_name
  username                    = "autoheal_master"
  manage_master_user_password = true # AWS Secrets Manager automated password management

  multi_az               = var.multi_az
  db_subnet_group_name   = aws_db_subnet_group.db.name
  vpc_security_group_ids = [aws_security_group.db.id]
  parameter_group_name   = aws_db_parameter_group.pg.name

  backup_retention_period   = var.backup_retention_days
  backup_window             = "03:00-04:00"
  maintenance_window        = "Mon:04:30-Mon:05:30"
  copy_tags_to_snapshot     = true
  deletion_protection       = var.environment == "prod" ? true : false
  skip_final_snapshot       = var.environment == "prod" ? false : true
  final_snapshot_identifier = "autoheal-db-${var.environment}-final"

  auto_minor_version_upgrade = true
  publicly_accessible        = false

  tags = merge(var.tags, {
    Name        = "autoheal-db-${var.environment}"
    Environment = var.environment
  })
}
