# podman

Install Podman on RHEL-family guests and serve a static Nginx site over HTTP.
The sandbox playbook applies this role only to guests also tagged `podman`.

The official Nginx stable Alpine image is pinned by digest. A root-owned
[Quadlet](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html)
at `/etc/containers/systemd/podman-nginx.container` defines the container,
publishes the HTTP port, and mounts the site read-only with a private SELinux
label. `podman-nginx.service` starts on boot and restarts after a failure.
Quadlet's `WantedBy` handles boot activation; do not enable the generated
service with `systemctl enable`.

Ansible updates the site, restarts the service when its container definition
changes, opens the selected TCP port if firewalld is running, and checks that
the expected page is served locally. SELinux stays enabled. Check mode skips
service starts and HTTP probes.

| Variable | Default | Purpose |
| --- | --- | --- |
| `podman_nginx_image` | Official Nginx image pinned in defaults | Fully qualified container image; update the digest to upgrade. |
| `podman_nginx_port` | `80` | VM HTTP port mapped to container port 80. |
| `podman_nginx_site_directory` | `/srv/podman/nginx/html` | Host directory containing the managed site. |
| `podman_nginx_site_title` | `Nginx on Podman` | Site title and heading. |

Use `inventory/group_vars/tag_podman.yml` or host variables to override these
inputs. Edit `templates/index.html.j2` to change the page. Access the deployed
site at `http://VM_ADDRESS/` when using the default port; this internal sandbox
does not configure DNS or TLS.

Inspect the running workload inside the guest:

```sh
sudo systemctl status podman-nginx.service
sudo journalctl -u podman-nginx.service
sudo podman ps
curl --fail http://127.0.0.1/
```

The Terraform sandbox replaces the old Cockpit VM with a new Podman VM. Its new
SSH host key must be verified and enrolled as described in
[SSH access](../../../ssh/README.md) before Ansible can configure it. After
enrollment, use the workflow's `configuration` mode for `dev/sandbox` to finish
configuration without recreating the VM.
