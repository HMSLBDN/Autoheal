output "vpc_id" {
  value       = aws_vpc.main.id
  description = "The ID of the VPC"
}

output "public_subnet_ids" {
  value       = aws_subnet.public[*].id
  description = "IDs of the public ingress subnets"
}

output "private_compute_subnet_ids" {
  value       = aws_subnet.private_compute[*].id
  description = "IDs of the private compute subnets"
}

output "private_data_subnet_ids" {
  value       = aws_subnet.private_data[*].id
  description = "IDs of the private data subnets"
}

output "alb_security_group_id" {
  value       = aws_security_group.alb.id
  description = "Security Group ID of the Application Load Balancer"
}

output "compute_security_group_id" {
  value       = aws_security_group.compute.id
  description = "Security Group ID of the compute instances/tasks"
}
