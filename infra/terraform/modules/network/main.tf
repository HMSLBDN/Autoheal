# AutoHeal DevOps — Enterprise Network Infrastructure Module
# Configures isolated multi-AZ VPC, public ingress subnets, private compute subnets,
# private data subnets, NAT gateways, and strict security groups.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(var.tags, {
    Name        = "autoheal-vpc-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.main.id

  tags = merge(var.tags, {
    Name        = "autoheal-igw-${var.environment}"
    Environment = var.environment
  })
}

# Public Subnets (ALB & Ingress)
resource "aws_subnet" "public" {
  count                   = length(var.availability_zones)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 4, count.index)
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = merge(var.tags, {
    Name        = "autoheal-subnet-public-${var.availability_zones[count.index]}"
    Tier        = "Public"
    Environment = var.environment
  })
}

# Private Compute Subnets (API, Celery, Infrastructure Agents)
resource "aws_subnet" "private_compute" {
  count             = length(var.availability_zones)
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, count.index + 4)
  availability_zone = var.availability_zones[count.index]

  tags = merge(var.tags, {
    Name        = "autoheal-subnet-compute-${var.availability_zones[count.index]}"
    Tier        = "PrivateCompute"
    Environment = var.environment
  })
}

# Private Data Subnets (PostgreSQL & Redis)
resource "aws_subnet" "private_data" {
  count             = length(var.availability_zones)
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, count.index + 8)
  availability_zone = var.availability_zones[count.index]

  tags = merge(var.tags, {
    Name        = "autoheal-subnet-data-${var.availability_zones[count.index]}"
    Tier        = "PrivateData"
    Environment = var.environment
  })
}

# Elastic IP & NAT Gateway for Outbound Egress from Private Compute Subnets
resource "aws_eip" "nat" {
  domain = "vpc"
  tags = merge(var.tags, {
    Name        = "autoheal-eip-nat-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_nat_gateway" "nat" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = merge(var.tags, {
    Name        = "autoheal-nat-gw-${var.environment}"
    Environment = var.environment
  })
  depends_on = [aws_internet_gateway.gw]
}

# Route Tables
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw.id
  }

  tags = merge(var.tags, {
    Name        = "autoheal-rt-public-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat.id
  }

  tags = merge(var.tags, {
    Name        = "autoheal-rt-private-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private_compute" {
  count          = length(aws_subnet.private_compute)
  subnet_id      = aws_subnet.private_compute[count.index].id
  route_table_id = aws_route_table.private.id
}

# Security Groups
resource "aws_security_group" "alb" {
  name        = "autoheal-sg-alb-${var.environment}"
  description = "Controls ingress traffic to Application Load Balancer"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTPS ingress from internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Egress to private compute services"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }

  tags = merge(var.tags, {
    Name        = "autoheal-sg-alb-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_security_group" "compute" {
  name        = "autoheal-sg-compute-${var.environment}"
  description = "Allows ingress from ALB and egress to NAT & internal DB"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Traffic from ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "All outbound traffic via NAT gateway"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name        = "autoheal-sg-compute-${var.environment}"
    Environment = var.environment
  })
}
