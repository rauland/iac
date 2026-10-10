# Platform Automation
This Infrastructure as Code project builds an automation layer on top of Proxmox and is effectively the definition of the desired platform.

It provides the underlying services and automation capabilities required to bootstrap, automate the platform and operate workloads running on it.

## Overview
```mermaid
---
config:
  layout: elk
  flowchart:
    curve: basis
    htmlLabels: true
---
graph TD
    repo("<b>IaC Repository")
    actions("GitHub Actions<br/>CI/CD Automation")
    tf("Terraform<br/>Infrastructure Provisioning")
    s3[("AWS S3")]
    pve("Proxmox VE<br/>Virtualisation Platform")
    ansible("Ansible<br/>Configuration Management")
    vms("Virtual Machines")

    repo --> actions
    actions --> tf
    actions --> ansible
    s3 -->|Remote State Backend| tf
    tf -->|Plan / Apply| pve
    pve --> vms
    pve -->|Inventory| ansible
    ansible -->|Apply Roles| vms

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

### Continuous Integration and Delivery
**GitHub Actions**<br>
It's used to gate and automate infrastructure changes. It's source is driven from the repository. 

The CI/CD invokes Terraform to provision infrastructure which is declared in `Environments`.

If required, Ansible is then called to manage the configuration of the infrastructure.

Additionally workflows provided
- Bootstrap AWS S3 storage
- Unlock Terraform State in S3

### Infrastructure Provisioning
**Terraform**<br>
Terraform plan safetly maps what's it's going to create, modify or destroy, in CI/CD this stage has read only access. 

Once the plan has been approved, the Terraform apply/destroy stage is provided write access.

For the backend, object storage such as AWS S3 is recommended. It has state locking support.

Modules
  - cloud-image
  - virtual-machine

### Virtualisation Platform
**Proxmox VE**<br>
This hypervisor provides APIs which are consumed by Terraform and Ansible to create and run Virtual Machines.

### Configuration Management 
**Ansible**<br>
Inventory is dynamically pulled from the Proxmox API. Roles are applied based on tags. If a node has the `managed` tag, they will have the managed ansible roles applied.

Ansible remotes to Virtual Machines with SSHs keys.

### Virtual Machines 
The virtual machines will host services and workloads, any flavour of Linux could work but currently AlmaLinux10 and Ubuntu configuration is supported.

- Services
    - vault
- Workloads
    - k3s

### VPN
**Wireguard**<br>
Connections to the Proxmox API is done securely over Wireguard. With this solution no runner is required in your environment.

## Environment Example
[./terraform/environments/dev/k3s/terraform.auto.tfvars](https://github.com/rauland/iac/blob/main/terraform/environments/dev/k3s/terraform.auto.tfvars)
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
By the ephemeral nature of deployments, destroys and scaling. The assumption is that your infrastructure supports DHCP and dynamic DNS or that you're able to set static IPs.

## Planned Features
### Configuration Management
- K3s Roles
- SSH Certs
- Secrets Management
    - SOPS or Ansible-Vault

### CI/CD
- Linting
    - Terraform fmt

### K8s
- GitOps
- Backup persistent container data to cloud
 
## Future Features
- Static IPAM integration
