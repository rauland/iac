```bash
terraform plan -var-file=proxmox.tfvars -out tfplan
terraform apply -var-file=proxmox.tfvars
terraform destroy -var-file=proxmox.tfvars
terraform state mv 'module.vpc' 'module.network'

export CONTROL_PLANE_IP="10.0.0.50"
talosctl gen config homelab https://$CONTROL_PLANE_IP:6443 --output-dir _out --install-image factory.talos.dev/nocloud-installer/d3dc673627e9b94c6cd4122289aa52c2484cddb31017ae21b75309846e257d30:v1.11.2

export TALOSCONFIG="talosconfig"
talosctl config endpoint $CONTROL_PLANE_IP
talosctl config node $CONTROL_PLANE_IP

talosctl bootstrap

talosctl kubeconfig .

export KUBECONFIG=kubeconfig

kubectl get pods -o wide

kubectl apply -f https://k8s.io/examples/application/deployment.yaml
kubectl describe deployment nginx-deployment
