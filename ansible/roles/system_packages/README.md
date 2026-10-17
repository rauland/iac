# system_packages

Ensure baseline and host-specific packages are installed using the host's native
package manager through `ansible.builtin.package`. Existing packages are kept at
their installed version rather than upgraded to the latest version.

Requires privilege escalation and a supported package manager on the target.
Package names must match the target distribution and its configured repositories.
There are no role or collection dependencies beyond Ansible's built-in modules.

| Variable | Default | Purpose |
| --- | --- | --- |
| `system_packages_base` | `[]` | Shared baseline packages. |
| `system_packages_extra` | `[]` | Additional packages for a group or host. |
| `system_packages_list` | `system_packages_base + system_packages_extra` | Derived list; configure the two input lists. |

The repository sets `system_packages_base` to `[qemu-guest-agent]` for `tag_common`.
For example, host variables can add packages:

```yaml
system_packages_extra:
  - curl
  - vim
```
