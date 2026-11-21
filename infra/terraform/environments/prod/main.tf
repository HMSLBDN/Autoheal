terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Production remote state backend with encryption and distributed locking:
  # backend "s3" {
  #   bucket         = "autoheal-terraform-state-prod"
  #   key            = "prod/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "autoheal-terraform-locks-prod"
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
    Compliance  = "SOC2-HIPAA"
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
  instance_class            = "db.r6g.2xlarge"
  allocated_storage         = 200
  max_allocated_storage     = 1000
  multi_az                  = true
  backup_retention_days     = 30
  database_name             = "autoheal_production"
  tags                      = locals.tags
}

module "redis" {
  source                    = "../../modules/redis"
  environment               = var.environment
  vpc_id                    = module.network.vpc_id
  subnet_ids                = module.network.private_data_subnet_ids
  compute_security_group_id = module.network.compute_security_group_id
  node_type                 = "cache.r6g.xlarge"
  num_cache_nodes           = 3
  tags                      = locals.tags
}

module "compute" {
  source                    = "../../modules/compute"
  environment               = var.environment
  vpc_id                    = module.network.vpc_id
  subnet_ids                = module.network.private_compute_subnet_ids
  compute_security_group_id = module.network.compute_security_group_id
  min_capacity              = 4
  max_capacity              = 20
  desired_capacity          = 4
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
