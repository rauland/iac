# IaC and pipelines for self-hosted virtualisation.

This project demonstrates reproducible infrastructure by leveraging IaC and automation. It can be dropped into any existing Proxmox environment and customised as required.

To get started, fork this repo. Included are workflows that can bootstrap your state file.

Also included is:
- Ansible roles and playbooks for Configuration Management.
- GitHub Actions workflows for Continuous Integration.
- Terraform modules for Infrastructure Provisioning.

## Overview
<img width="2040" height="1560" alt="fossflow-export-2026-03-22T08_35_25 035Z" src="https://github.com/user-attachments/assets/ddda8bb0-25df-464d-a298-db219ccc5e71" />

### Actions Pipeline
Workflows bootstrap and call Terraform modules with infrastructure being declared in `Environments`.

### Wireguard VPN
Connections to the Proxmox API is done securely over Wireguard. With this solution no runner is required in your environment.

### Ansible Controller
Roles are applied based on tags provided by Terraform. If a node has the `managed` tag, they will automatically be patched.

## Limitations
By the ephemeral nature of deployments, destroys and scaling. The assumption is that your infrastructure supports DHCP and dynamic DNS.

## Current Features
### Configuration Management
- Ansible Playbooks
    - Apply Roles
    - Node Patching
- Dynamic Inventory
    - Tag-based

### Infrastructure Provisioning
- Remote state backend on AWS S3
- State locking
- Modules
    - Cloud-image
        - Ubuntu
        - Debian
    - Cloud-int
    - Nodes
        - Provision
        - Tags

### CI/CD
- AWS S3 Bucket Bootstrap
- Terraform Plan
- Wireguard VPN
- Unlock State

## Planned Features
### Configuration Management
- Ansible Controller (LXC or Pipeline)
- K3s Roles
- SSH Certs
- Secrets Management
    - SOPS or Ansible-Vault

### CI/CD
- Terraform Apply, Destroy

### K8s (May be in private repo)
- GitOps
- Backup persistent container data to cloud
 
## Future Features
- Static IPAM integration
