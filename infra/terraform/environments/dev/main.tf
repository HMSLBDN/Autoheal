terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # In production, configure S3 backend with DynamoDB state locking:
  # backend "s3" {
  #   bucket         = "autoheal-terraform-state-dev"
  #   key            = "dev/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "autoheal-terraform-locks-dev"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region
}

locals {
  tags = {
    Project     = "AutoHeal DevOps"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

module "network" {
  source      = "../../modules/network"
  environment = var.environment
  vpc_cidr    = var.vpc_cidr
  tags        = locals.tags
}

module "iam" {
  source      = "../../modules/iam"
  environment = var.environment
  tags        = locals.tags
}

module "database" {
  source                    = "../../modules/database"
  environment               = var.environment
  vpc_id                    = module.network.vpc_id
  subnet_ids                = module.network.private_data_subnet_ids
  compute_security_group_id = module.network.compute_security_group_id
  instance_class            = "db.t4g.medium"
  allocated_storage         = 20
  multi_az                  = false
  backup_retention_days     = 7
  database_name             = "autoheal_dev"
  tags                      = locals.tags
}

module "redis" {
  source                    = "../../modules/redis"
  environment               = var.environment
  vpc_id                    = module.network.vpc_id
  subnet_ids                = module.network.private_data_subnet_ids
  compute_security_group_id = module.network.compute_security_group_id
  node_type                 = "cache.t4g.medium"
  num_cache_nodes           = 1
  tags                      = locals.tags
}

module "compute" {
  source                    = "../../modules/compute"
  environment               = var.environment
  vpc_id                    = module.network.vpc_id
  subnet_ids                = module.network.private_compute_subnet_ids
  compute_security_group_id = module.network.compute_security_group_id
  min_capacity              = 1
  max_capacity              = 3
  desired_capacity          = 1
  tags                      = locals.tags
}

module "monitoring" {
  source                    = "../../modules/monitoring"
  environment               = var.environment
  vpc_id                    = module.network.vpc_id
  subnet_ids                = module.network.private_compute_subnet_ids
  compute_security_group_id = module.network.compute_security_group_id
  tags                      = locals.tags
}
