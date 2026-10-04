# Self-hosted Platform
This Infrastructure as Code project defines and automates the infrastructure and services that make up a self-hosted platform running on Proxmox. It provides the underlying compute, shared services and automation capabilities required to operate the platform and support workloads running on it.

### Technologies used
- Ansible roles and playbooks for configuration management of platform components.
- GitHub Actions workflows for continuous integration and deployment.
- Terraform modules for infrastructure provisioning of platform components.

## Overview
```mermaid
---
config:
  layout: elk
  theme: classic
  themeVariables:
    background: #0B1120
    fontFamily: Inter, Arial, sans-serif
    fontSize: 14px
    lineColor: #64748B
    textColor: #E2E8F0
    clusterBkg: #111827
    clusterBorder: #334155
  look: Neo
  flowchart:
    curve: basis
    htmlLabels: true
---
graph TD
    repo("<b>IaC Repository")
    actions("GitHub Actions<br/>CI/CD Automation")
    tf("Terraform<br/>Plan / Apply")
    s3[("AWS S3")]
    pve("Proxmox VE<br/>Virtualisation Platform")
    ansible("Ansible<br/>Apply Roles")
    vms("Virtual Machines")

    repo --> actions
    actions --> tf
    actions --> ansible
    s3 -->|Remote State Backend| tf
    tf -->|Infrastructure Provisioning| pve
    pve --> vms
    pve -->|Inventory| ansible
    ansible -->|Configuration Management| vms

    classDef cloud fill:#1E293B,stroke:#94A3B8,color:#F8FAFC,stroke-width:2px
    classDef cicd fill:#172554,stroke:#60A5FA,color:#DBEAFE,stroke-width:2px
    classDef terraform fill:#3B1D66,stroke:#A78BFA,color:#F3E8FF,stroke-width:2px
    classDef ansible fill:#5F1212,stroke:#EF4444,color:#FEE2E2,stroke-width:2px
    classDef infra fill:#5C2E0B,stroke:#F97316,color:#FFEDD5,stroke-width:2px

    class repo cloud
    class actions cicd
    class tf terraform
    class ansible ansible
    class pve infra
    class s3 cloud
    class vms infra

    linkStyle 0 stroke:#60A5FA,stroke-width:2px,stroke-dasharray:5 5
    linkStyle 1 stroke:#60A5FA,stroke-width:2.5px
    linkStyle 2 stroke:#60A5FA,stroke-width:2.5px
    linkStyle 3 stroke:#A78BFA,stroke-width:2px,stroke-dasharray:5 5
    linkStyle 4 stroke:#A78BFA,stroke-width:2.5px
    linkStyle 5 stroke:#F97316,stroke-width:2.5px
    linkStyle 6 stroke:#EF4444,stroke-width:2px,stroke-dasharray:5 5
    linkStyle 7 stroke:#EF4444,stroke-width:2.5px

```

### Ansible Controller
Roles are applied based on tags provided by Terraform. If a node has the `managed` tag, they have the managed ansible roles applied.

### Actions Pipeline
Workflows bootstrap and call Terraform modules with infrastructure being declared in `Environments`.

Terraform plan has read only access. Terraform apply and destroy require pipeline approval for write access.

### Wireguard VPN
Connections to the Proxmox API is done securely over Wireguard. With this solution no runner is required in your environment.

## Environment Example
[./terraform/environments/dev/k3s.tfvars](https://github.com/rauland/iac/blob/main/terraform/environments/dev/k3s.tfvars)
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
- Remote state locking backend on AWS S3
- Modules
  - cloud-image
  - virtual-machine
- Platform
  - vault
  - k3s

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
