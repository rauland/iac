# system_timezone

Set the host's system timezone. The role defaults to `UTC`; repository inventory
overrides it with `Australia/Melbourne` in `inventory/group_vars/all.yml`.

Requires privilege escalation, installed timezone data, and the
`community.general` collection providing the `timezone` module. There are no
role dependencies.

| Variable | Default | Purpose |
| --- | --- | --- |
| `system_timezone_name` | `UTC` | Timezone database name, such as `Australia/Melbourne`. |

Override the timezone in group or host variables:

```yaml
system_timezone_name: Australia/Melbourne
```
