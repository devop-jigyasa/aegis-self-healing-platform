output "vpc_id" {
  description = "The ID of the provisioned AEGIS VPC"
  value       = aws_vpc.aegis_vpc.id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets for external load balancers"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs of the private subnets hosting EKS worker nodes"
  value       = aws_subnet.private[*].id
}

output "eks_cluster_name" {
  description = "The name of the AEGIS EKS cluster"
  value       = aws_eks_cluster.main.name
}

output "eks_cluster_endpoint" {
  description = "Endpoint for EKS control plane API server"
  value       = aws_eks_cluster.main.endpoint
}

output "eks_cluster_arn" {
  description = "The Amazon Resource Name (ARN) of the EKS cluster"
  value       = aws_eks_cluster.main.arn
}

output "oidc_provider_arn" {
  description = "The ARN of the OIDC Provider for IAM Roles for Service Accounts (IRSA)"
  value       = aws_iam_openid_connect_provider.cluster.arn
}

output "controller_irsa_role_arn" {
  description = "The ARN of the controller IRSA IAM Role"
  value       = aws_iam_role.controller_irsa.arn
}

output "cluster_security_group_id" {
  description = "Security group ID attached to the EKS control plane"
  value       = aws_security_group.cluster.id
}

output "node_security_group_id" {
  description = "Security group ID attached to EKS worker nodes"
  value       = aws_security_group.node.id
}
