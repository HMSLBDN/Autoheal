# AutoHeal DevOps — Infrastructure as Code (IaC) Architecture Guide

## 1. Overview & Architecture

AutoHeal DevOps SaaS Phase 10 provides a production-grade, modular Infrastructure as Code (IaC) framework compatible with both **Terraform (>= 1.5.0)** and **OpenTofu (>= 1.6.0)**. 

The architecture guarantees:
- **Strict Network Segmentation**: Multi-AZ VPC design with isolated public, private application, and isolated database subnets.
- **Enterprise High Availability**: Multi-AZ database clustering, redundant Redis caching nodes, and container autoscaling groups.
- **Zero-Trust IAM Policies**: Explicit least-privilege IAM roles, IRSA (IAM Roles for Service Accounts), and KMS customer-managed keys.
- **Controlled Environment Stratification**: Parameterized configurations for `dev`, `staging`, and `prod` with environment-specific capacity and security policies.

---

## 2. Directory Structure

```
infra/terraform/
├── modules/
│   ├── network/             # VPC, CIDRs, NAT Gateways, Subnets, Flow Logs
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── compute/             # Container clusters (EKS/ECS), Auto-scaling, Task specs
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── database/            # Multi-AZ PostgreSQL, RDS/Aurora, KMS, Parameter Groups
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── redis/               # ElastiCache Redis, Replication Groups, In-transit encryption
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── monitoring/          # OpenTelemetry Collector, Prometheus, Grafana, CloudWatch
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   └── iam/                 # Service roles, OIDC trust relationships, Least-privilege policies
│       ├── main.tf
│       ├── variables.tf
│       └── outputs.tf
└── environments/
    ├── dev/                 # Single-AZ cost-optimized developer sandbox
    │   ├── main.tf
    │   ├── variables.tf
    │   ├── outputs.tf
    │   └── terraform.tfvars.example
    ├── staging/             # Multi-AZ pre-production parity environment
    │   ├── main.tf
    │   ├── variables.tf
    │   ├── outputs.tf
    │   └── terraform.tfvars.example
    └── prod/                # High-availability, multi-AZ, compliance-hardened production
        ├── main.tf
        ├── variables.tf
        ├── outputs.tf
        └── terraform.tfvars.example
```

---

## 3. Terraform Module Breakdown

### 3.1 Network Module (`modules/network`)
- Provisions 3-tier VPC architecture across 3 Availability Zones:
  - **Public Subnets**: Internet-facing Application Load Balancers (ALBs) and NAT Gateways.
  - **Private Application Subnets**: Container workloads (AutoHeal backend API, worker daemons). No public IPv4/IPv6 assignment.
  - **Isolated Database Subnets**: PostgreSQL and Redis instances. Completely detached from internet routing tables; accessible exclusively via private security group ingress from application subnets.
- Enables VPC Flow Logs with CloudWatch logging and KMS encryption.

### 3.2 Compute Module (`modules/compute`)
- Provisions scalable container clusters with horizontal pod/task autoscaling based on CPU, memory, and custom request latency metrics.
- Enforces strict container security contexts: read-only root filesystems, non-root user execution (`uid: 10001`), and dropped Linux capabilities (`ALL` dropped, no privilege escalation).

### 3.3 Database Module (`modules/database`)
- Provisions PostgreSQL 16+ engine with Multi-AZ automated failover.
- Enforces storage encryption with AWS KMS Customer Master Keys (CMKs).
- Configures automated daily snapshots with 30-day retention and Point-In-Time-Recovery (PITR) with transaction log archiving.
- Enforces SSL/TLS connections (`sslmode=verify-full`).

### 3.4 Redis Module (`modules/redis`)
- Deploys highly available Redis replication groups with in-transit TLS encryption and authentication tokens.
- Automatic failover across availability zones with memory eviction policies optimized for session and cache workloads (`volatile-lru`).

### 3.5 Monitoring & Observability Module (`modules/monitoring`)
- OpenTelemetry Collector sidecars and daemonsets.
- Managed Prometheus scraper endpoints and alertmanager integration.
- IAM permissions for exporting distributed traces to AWS X-Ray, Grafana Tempo, or Jaeger.

### 3.6 IAM Module (`modules/iam`)
- Granular IAM policies preventing wildcard `*` permissions.
- Scoped access keys and IRSA roles for backend pods to access KMS, Secrets Manager, and S3 backup buckets.

---

## 4. Environment Comparison Matrix

| Configuration Parameter | `dev` | `staging` | `prod` |
|:---|:---|:---|:---|
| **Multi-AZ Deployment** | False (Single AZ) | True (2 AZs) | True (3 AZs) |
| **NAT Gateways** | 1 (Shared) | 2 (Redundant) | 3 (1 per AZ) |
| **DB Instance Class** | `db.t4g.medium` | `db.r6g.large` | `db.r6g.2xlarge` |
| **Multi-AZ RDS** | Disabled | Enabled | Enabled |
| **Backup Retention** | 7 Days | 14 Days | 35 Days (PITR) |
| **KMS CMK Rotation** | Annual | Annual | Annual (Enforced) |
| **Compute Autoscaling** | 1 - 2 nodes | 2 - 6 nodes | 4 - 30 nodes |
| **Deletion Protection** | Disabled | Enabled | Enabled |

---

## 5. Execution & Validation Workflow

```bash
# 1. Navigate to target environment
cd infra/terraform/environments/staging

# 2. Initialize provider plugins and remote state backend
terraform init

# 3. Validate syntax and configuration integrity
terraform validate

# 4. Generate speculative execution plan
terraform plan -out=staging.tfplan

# 5. Apply changes (enforcing controlled deployment review)
terraform apply staging.tfplan
```

> [!NOTE]
> In accordance with strict development guardrails, all cloud infrastructure provisioning is managed in dry-run/simulation mode. No live billable cloud infrastructure is provisioned during automated verification runs.
