# vault

Install HashiCorp Vault from its RPM repository on RHEL-family hosts, configure
file storage in `/opt/vault/data`, and enable its systemd service. TLS
certificates are obtained with Certbot using Cloudflare DNS validation and
copied into `/etc/vault.d/ssl`.

The repository provisions AlmaLinux guests. The role requires DNF, availability
of `epel-release`, systemd, privilege escalation, outbound repository and ACME
access, and a Cloudflare-managed DNS zone. It has no role dependencies and uses
Ansible's built-in modules.

`tasks/main.yml` checks the gathered OS family before any changes. Package and
repository tasks live in `tasks/RedHat.yml`; account, storage, TLS, and service
tasks live in `tasks/common.yml`. Other OS families are rejected until their
package setup is implemented.

| Variable | Default | Purpose |
| --- | --- | --- |
| `vault_api_addr` | Required | DNS name used for the TLS certificate and API URL on port 8200. |
| `vault_cluster_addr` | Required | DNS name used for the cluster URL on port 8201. |
| `certbot_email` | Required | ACME account email address. |

The repository supplies these variables in `inventory/group_vars/tag_vault.yml`.
The controller must also supply `CLOUDFLARE_API_TOKEN` with DNS edit access for
the certificate's zone. The token is written to a root-only credentials file;
the task suppresses its output.

Run through the scoped runner:

```sh
bash ansible/run-playbook.sh dev vault --check
bash ansible/run-playbook.sh dev vault
```

Initialization and unsealing are separate operational steps. Certificate
issuance is skipped when a certificate already exists; this role does not
configure renewal deployment hooks to copy renewed certificates or restart
Vault.
