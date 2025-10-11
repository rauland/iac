output "talos_controlpane_configuration" {
  value = data.talos_machine_configuration.controlplane.machine_configuration
}

output "talos_worker_configuration" {
  value = data.talos_machine_configuration.worker.machine_configuration
}

output "talos_client_configuration" {
  value = data.talos_client_configuration.this.talos_config 
}

output "talos_machine_secrets" {
  value = talos_machine_secrets.this.client_configuration
}
