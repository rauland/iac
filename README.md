# IaC for Proxmox Virtual Environment

Infrastructure as Code for Proxmox homelab/self hosted virtual environment.

This project demonstrates automation with Ansible Configuration Management, Terraform Infrastructure Provisioning and GitHub Actions CI/CD.

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
Roles are applied based on tags provided in Terraform, if a node has the `managed` tag, they will automatically be patched.

## Current Features
- Configuration Management
    - Ansible Playbooks
        - Patching
        - Apply Roles
    - Dynamic Inventory
- Infrastructure Provisioning
    - VM Node Deployments
        - Ubuntu
        - Debian
    - Talos K8s POC
- CI/CD
    - Wireguard Runner POC

## Planned Features
- Configuration Management
    - Ansible Controller (LXC or Pipeline)
    - Ubuntu k3s/k8s Nodes
- CI/CD
    - Secrets Management
    - TF Remote Backend on AWS
- Backup container persistent data to AWS glacier