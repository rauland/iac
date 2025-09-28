```bash
terraform plan -var-file=proxmox.tfvars -out tfplan

terraform plan -target=module.talos -var-file=proxmox.tfvars -out tfplan