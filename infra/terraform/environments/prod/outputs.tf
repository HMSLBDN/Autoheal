output "vpc_id" {
  value = module.network.vpc_id
}

output "database_endpoint" {
  value = module.database.endpoint
}

output "redis_endpoint" {
  value = module.redis.primary_endpoint_address
}

output "ecs_cluster_id" {
  value = module.compute.cluster_id
}
