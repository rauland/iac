resource "talos_machine_bootstrap" "this" {
  node                 = "10.0.0.50"
  client_configuration = var.talos_machine_secrets
}