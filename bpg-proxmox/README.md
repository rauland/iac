```bash
terraform plan -var-file=proxmox.tfvars -out tfplan

terraform plan -target=talos -var-file=proxmox.tfvars -out tfplan