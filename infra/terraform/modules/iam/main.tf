# AutoHeal DevOps — Enterprise IAM & Least Privilege Access Module
# Configures ECS Task Execution Roles, Secrets Manager access, and KMS decryption.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "autoheal-ecs-execution-role-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "execution_standard" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "task" {
  name               = "autoheal-ecs-task-role-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "task_permissions" {
  statement {
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey"
    ]
    resources = ["*"]
  }

  statement {
    actions = [
      "secretsmanager:GetSecretValue"
    ]
    resources = ["arn:aws:secretsmanager:*:*:secret:autoheal-*"]
  }
}

resource "aws_iam_policy" "task_custom" {
  name   = "autoheal-task-policy-${var.environment}"
  policy = data.aws_iam_policy_document.task_permissions.json
  tags   = var.tags
}

resource "aws_iam_role_policy_attachment" "task_custom_attach" {
  role       = aws_iam_role.task.name
  policy_arn = aws_iam_policy.task_custom.arn
}
