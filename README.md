# IaC for Proxmox Virtual Environment

Infrastructure as Code for a Proxmox homelab or self-hosted virtual environment.

This project demonstrates reproducible infrastructure by leveraging IaC and automation. It can be dropped into any existing Proxmox environment and customised as required.

To get started, fork this repo. Included is workflows that can bootstrap your state file.

Also included is:
- Ansible for Configuration Management
- GitHub Actions for Continuous Integration
- Terraform for Infrastructure Provisioning

## Overview
<img width="2502" height="1545" alt="fossflow-export-2026-03-19T22_14_02 787Z" src="https://github.com/user-attachments/assets/74c1d70a-53e8-4cfb-947d-088b5f4c8fe3" />

### Ansible Roles and Tags
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
