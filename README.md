# IaC and pipelines adapted for self-hosted virtualisation.

This project demonstrates reproducible infrastructure by leveraging IaC and automation. It can be dropped into any existing Proxmox environment and customised as required.

To get started, fork this repo. Included are workflows that can bootstrap your state file.

Also included is:
- Ansible for Configuration Management
- GitHub Actions for Continuous Integration
- Terraform for Infrastructure Provisioning

## Overview
<img width="2502" height="1545" alt="fossflow-export-2026-03-19T22_14_02 787Z" src="https://github.com/user-attachments/assets/74c1d70a-53e8-4cfb-947d-088b5f4c8fe3" />

### Ansible Roles and Tags
Roles are applied based on tags provided by Terraform. If a node has the `managed` tag, they will automatically be patched.

## Limitations
By the ephemeral nature of deployments, destroys and scaling. The assumption is that your infrastructure supports DHCP and dynamic DNS.

## Current Features
- Configuration Management
    - Ansible Playbooks
        - Apply Roles
        - Node Patching
    - Dynamic Inventory
        - Tag-based
- Infrastructure Provisioning
    - Remote state locking backend on AWS S3
    - Compute Nodes
        - Ubuntu
        - Debian
- CI/CD
    - AWS S3 Bucket Bootstrap
    - Terraform Apply
    - Wireguard VPN

## Planned Features
- Configuration Management
    - Ansible Controller (LXC or Pipeline)
    - K3s Roles
    - SSH Certs
- CI/CD
    - Secrets Management
        - SOPS or Ansible-Vault
- K8s (May be in private repo)
    - GitOps
    - Backup persistent container data to cloud
 
## Future Features
- Static IPAM integration
