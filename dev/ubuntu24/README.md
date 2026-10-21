# Ubuntu 24.04 installation ISO

Build on a Linux workstation with sufficient space for two server ISOs, not on
the nearly-full old development server. This installs the guest agent before
the installed system first boots, then the [host bootstrap](../README.md)
prepares rootless Podman and the developer account.

Ubuntu 24.04 supports an `autoinstall.yaml` file at the installation medium's
root. See [Canonical's installation-media instructions](https://canonical-subiquity.readthedocs-hosted.com/en/latest/tutorial/providing-autoinstall.html#autoinstall-on-the-installation-media)
and [configuration reference](https://canonical-subiquity.readthedocs-hosted.com/en/latest/reference/autoinstall-reference.html).

## Prepare the configuration

Download an Ubuntu **24.04 live-server amd64** ISO from
[Ubuntu releases](https://releases.ubuntu.com/24.04/) and verify its published
SHA256 checksum and signature using [Ubuntu's verification guide](https://ubuntu.com/tutorials/how-to-verify-ubuntu).
Install `xorriso`, `openssl`, and Python 3 on the build machine.

```sh
mkdir -m 700 ubuntu-agent-iso
cp dev/ubuntu24/autoinstall.example.yaml ubuntu-agent-iso/autoinstall.yaml
openssl passwd -6
```

Edit the copied file: paste the generated password hash and your actual public
SSH key into their respective fields. This password is for the initial
administrator's console and sudo access; SSH password login is disabled. Set a
unique hostname and adapt networking if the VM will not use DHCP. Reserve its
DHCP address so the initial SSH bootstrap has a known destination.

The example's `direct` storage layout **erases the installation target disk**.
Use it only on a new VM with its intended empty disk attached. The installer
needs outbound package access to install the guest agent. A failed package
installation must be resolved before using the resulting server.

## Remaster the ISO

From the directory containing the downloaded ISO and `ubuntu-agent-iso`:

```sh
source_iso="$PWD/ubuntu-24.04-live-server-amd64.iso" # Set the actual downloaded filename.
build_directory="$PWD/ubuntu-agent-iso"
output_iso="$PWD/ubuntu-agent-host.iso"

xorriso -osirrox on -indev "$source_iso" \
  -extract /boot/grub/grub.cfg "$build_directory/grub.cfg"
xorriso -osirrox on -indev "$source_iso" \
  -extract /md5sum.txt "$build_directory/md5sum.txt"
chmod u+w "$build_directory/grub.cfg"
sed -i -E '/^[[:space:]]*linux[[:space:]].*\/casper\/vmlinuz/ s/ ---/ autoinstall ---/' \
  "$build_directory/grub.cfg"
# Check that the install entry now contains the autoinstall kernel argument.
grep 'linux.*autoinstall' "$build_directory/grub.cfg"

# Update the installer's media-integrity manifest for the modified/new files.
python3 - "$build_directory" <<'PY'
import hashlib
from pathlib import Path
import sys

directory = Path(sys.argv[1])
manifest = directory / 'md5sum.txt'
updated = {'boot/grub/grub.cfg': directory / 'grub.cfg',
           'autoinstall.yaml': directory / 'autoinstall.yaml'}
lines = []
for line in manifest.read_text().splitlines():
    fields = line.split(maxsplit=1)
    path = fields[1].lstrip('*').removeprefix('./').lstrip('/') if len(fields) == 2 else ''
    if path not in updated:
        lines.append(line)
for path, source in updated.items():
    lines.append(f'{hashlib.md5(source.read_bytes()).hexdigest()}  ./{path}')
manifest.chmod(0o600)
manifest.write_text('\n'.join(lines) + '\n')
PY

xorriso -indev "$source_iso" -outdev "$output_iso" \
  -map "$build_directory/autoinstall.yaml" /autoinstall.yaml \
  -map "$build_directory/grub.cfg" /boot/grub/grub.cfg \
  -map "$build_directory/md5sum.txt" /md5sum.txt \
  -boot_image any replay
```

The output path must differ from the source and should not already exist.
`replay` preserves the source ISO's recognized boot configuration; see the
[xorriso manual](https://www.gnu.org/software/xorriso/man_1_xorriso.html).
Record the source and output checksums. The resulting ISO contains your public
key and administrator password hash; keep it in your private image storage.

## Install and validate on Proxmox

1. Create a new VM named `agent-host` with Ubuntu 24.04 as the target OS, 4 vCPUs,
   8 GB RAM, and a 60 GB disk as a starting allocation. Attach the ISO to its
   CD-ROM and a VirtIO network interface to the intended bridge.
2. Enable the **QEMU Guest Agent** option before installation so the VM exposes
   its virtio guest-agent channel. Start the VM and select the normal installer
   entry. Installation powers off when finished.
3. Detach the installer ISO and boot from the installed disk. Confirm
   `systemctl is-active qemu-guest-agent` in the guest. On the Proxmox host,
   `qm agent VMID ping` and `qm agent VMID network-get-interfaces` must succeed.
4. Verify the SSH host-key fingerprint through the Proxmox console before
   accepting it over SSH. Run the [Ansible bootstrap](../README.md#bootstrap-a-fresh-server)
   against the new address with `-u ubuntu --ask-become-pass`.
5. Verify a disposable Codex session before moving projects or retiring the old
   development server.

These are installation instructions, not a published or boot-tested ISO.
This route uses console-verified SSH access. It does not depend on the current
AlmaLinux-only Terraform seed or automatic host-key enrollment implementation.
