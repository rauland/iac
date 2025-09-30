```bash
terraform plan -var-file=proxmox.tfvars -out tfplan
terraform apply -var-file=proxmox.tfvars
terraform destroy -var-file=proxmox.tfvars

export CONTROL_PLANE_IP="10.0.0.50"
talosctl gen config homelab https://$CONTROL_PLANE_IP:6443 --output-dir _out

talosctl config endpoint $CONTROL_PLANE_IP
talosctl config node $CONTROL_PLANE_IP
export TALOSCONFIG="_out/talosconfig"

talosctl bootstrap

talosctl kubeconfig .

export KUBECONFIG=kubeconfig

kubectl get pods -o wide