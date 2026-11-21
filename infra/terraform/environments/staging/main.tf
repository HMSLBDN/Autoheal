terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # In staging, remote state locking backend:
  # backend "s3" {
  #   bucket         = "autoheal-terraform-state-staging"
  #   key            = "staging/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "autoheal-terraform-locks-staging"
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
  instance_class            = "db.r6g.large"
  allocated_storage         = 50
  multi_az                  = true
  backup_retention_days     = 14
  database_name             = "autoheal_staging"
  tags                      = locals.tags
}

module "redis" {
  source                    = "../../modules/redis"
  environment               = var.environment
  vpc_id                    = module.network.vpc_id
  subnet_ids                = module.network.private_data_subnet_ids
  compute_security_group_id = module.network.compute_security_group_id
  node_type                 = "cache.m6g.large"
  num_cache_nodes           = 2
  tags                      = locals.tags
}

module "compute" {
  source                    = "../../modules/compute"
  environment               = var.environment
  vpc_id                    = module.network.vpc_id
  subnet_ids                = module.network.private_compute_subnet_ids
  compute_security_group_id = module.network.compute_security_group_id
  min_capacity              = 2
  max_capacity              = 6
  desired_capacity          = 2
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
