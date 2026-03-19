# IaC for Proxmox Virtual Environment

Infrastructure as Code for Proxmox homelab/self hosted virtual environment.

This project demonstrates end-to-end automation with Ansible Configuration Management, Terraform Infrastructure Provisioning and GitHub Actions CI/CD.

## Overview
```
GitHub Actions
      │
      ▼
Terraform → Proxmox API → Node creation
      │
      ▼
Ansible → Configure Nodes
      │
      ▼
Node / Kubernetes cluster
```
Roles are applied based on tags provided by Terraform. If a node has the `managed` tag, they will automatically be patched.

## Limitations
By the empherical nature of deployments, destroys and scaling. Your infrastructure must support DHCP and Auto DNS registration.

## Current Features
- Configuration Management
    - Ansible Playbooks
        - Patching
        - Apply Roles
    - Dynamic Inventory
- Infrastructure Provisioning
    - Remote State Backend on AWS S3\
    - Compute Node Deployments
        - Ubuntu
        - Debian
    - Talos K8s POC
- CI/CD
    - Wireguard Runner POC
    - AWS S3 State Bootstrap

## Planned Features
- Configuration Management
    - Ansible Controller (LXC or Pipeline)
    - Ubuntu k3s/k8s Nodes
    - SSH Certs
- CI/CD
    - Secrets Management
- K8s (May be in private repo)
    - GitOps
    - Backup container persistent data to AWS s3/glacier
