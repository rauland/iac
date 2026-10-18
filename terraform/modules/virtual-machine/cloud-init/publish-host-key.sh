#!/bin/sh
set -eu
# Export only the public key; original SSH key labels and SELinux enforcement stay intact.
install -m 0644 /etc/ssh/ssh_host_ed25519_key.pub /run/ci-ssh-host-key.pub
chcon -t virt_qemu_ga_var_run_t /run/ci-ssh-host-key.pub
