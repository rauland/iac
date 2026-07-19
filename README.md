# IaC and pipelines for self-hosted virtualisation.
Infrastructure as Code setup used to manage my Proxmox Virtual Environment. It is composed of:
- Ansible roles and playbooks for configuration management.
- GitHub Actions workflows for continuous integration and deployment.
- Terraform modules for infrastructure provisioning.

It is designed to be dropped into any existing Proxmox environment and customised as required.

If you want to use this as a starting point for your own IaC project, fork this repo. Included are bootstrap workflows.

## Overview
<img width="2040" height="1560" alt="fossflow-export-2026-03-22T08_35_25 035Z" src="https://github.com/user-attachments/assets/ddda8bb0-25df-464d-a298-db219ccc5e71" />

### Ansible Controller
Roles are applied based on tags provided by Terraform. If a node has the `managed` tag, they have the managed ansible roles applied.

### Actions Pipeline
Workflows bootstrap and call Terraform modules with infrastructure being declared in `Environments`.

Terraform plan has read only access. Terraform apply and destroy require pipeline approval for write access.

### Wireguard VPN
Connections to the Proxmox API is done securely over Wireguard. With this solution no runner is required in your environment.

## Environment Example
[./terraform/environments/compute/homelab.tfvars](https://github.com/rauland/iac/blob/main/terraform/environments/compute/homelab.tfvars)
```
vms = {                              # 1 or more VMs can be defined
  k3s-01 = {                         # name of guest
    node_name = "pve"                # name of pve node
    tags      = ["managed", "k3s"]   # managed for ansible configuration
    cpu       = 2
    memory    = 4096
  }
  k3s-02 = {
    node_name = "pve"
    tags      = ["managed", "k3s"]
    cpu       = 2
    memory    = 4096
  }
}

cloud_images = {
  "resolute-raccoon" = {            # default OS image
    url = "https://cloud-images.ubuntu.com/resolute/current/resolute-server-cloudimg-amd64.img"
  }
}
```

## Limitations
By the ephemeral nature of deployments, destroys and scaling. The assumption is that your infrastructure supports DHCP and dynamic DNS.

## Current Features
### Configuration Management
- Ansible Playbooks
    - Apply managed baseline
- Dynamic Inventory
    - Tag-based

### Infrastructure Provisioning
- Remote state backend on AWS S3
- State locking
- Modules
    - Cloud-image
        - Ubuntu
    - Cloud-int
    - Nodes
        - Provision
        - Tags

### CI/CD
- Ansible Controller
- Terraform Plan, Apply, Destroy
- Plan on PR
- Wireguard VPN
- AWS S3 Bucket Bootstrap
- Unlock State

## Planned Features
### Configuration Management
- K3s Roles
- SSH Certs
- Secrets Management
    - SOPS or Ansible-Vault

### CI/CD
- Linting
    - Terraform fmt

### K8s (May be in private repo)
- GitOps
- Backup persistent container data to cloud
 
## Future Features
- Static IPAM integration
