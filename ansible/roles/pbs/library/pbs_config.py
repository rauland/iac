#!/usr/bin/python
"""Create or update one Proxmox Backup Server configuration entry."""

import json

DOCUMENTATION = r"""
module: pbs_config
short_description: Manage a proxmox-backup-manager configuration entry
description:
  - Lists a configuration section with C(proxmox-backup-manager), then creates
    the entry if it is missing or updates only the options that differ.
  - Entries are never removed.
options:
  section:
    description: Command words for the section, such as C([sync-job]) or C([s3, endpoint]).
    type: list
    elements: str
    required: true
  id:
    description: Entry name.
    type: str
    required: true
  id_key:
    description: Field that holds the entry name in the list output.
    type: str
    default: id
  positional:
    description: Arguments placed after the name on creation, such as a datastore path.
    type: list
    elements: str
    default: []
  options:
    description: Options to set on creation and keep in step afterwards.
    type: dict
    default: {}
  create_only:
    description: Options passed only on creation, such as a datastore backend.
    type: dict
    default: {}
  write_only:
    description: Secret options that the list output does not show. Required on creation.
    type: dict
    default: {}
  update_write_only:
    description: Send the write-only options to an existing entry, for example to rotate a key.
    type: bool
    default: false
"""

COMMAND = "proxmox-backup-manager"


def value_text(value):
    """Render a value the way proxmox-backup-manager accepts and lists it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return ",".join(f"{key}={value_text(value[key])}" for key in sorted(value))
    return str(value)


def property_dict(value):
    if isinstance(value, dict):
        return {key: value_text(item) for key, item in value.items()}
    if not isinstance(value, str):
        return None
    pairs = [part.split("=", 1) for part in value.split(",") if part]
    if not all(len(pair) == 2 for pair in pairs):
        return None
    return {key: item for key, item in pairs}


def matches(desired, current):
    if current is None:
        return False
    if isinstance(desired, dict):
        return property_dict(desired) == property_dict(current)
    if isinstance(desired, list):
        current = current if isinstance(current, list) else [current]
        return [value_text(item) for item in desired] == [value_text(item) for item in current]
    if isinstance(desired, bool) and not isinstance(current, bool):
        current = str(current).lower() in {"1", "true", "yes", "on"}
    return value_text(desired) == value_text(current)


def option_args(options):
    args = []
    for key in sorted(options):
        values = options[key] if isinstance(options[key], list) else [options[key]]
        for value in values:
            args += [f"--{key}", value_text(value)]
    return args


def plan(entries, params):
    """Return (action, command, changed option names) for one entry."""
    section = params["section"]
    current = next((entry for entry in entries if entry.get(params["id_key"]) == params["id"]), None)
    if current is None:
        missing = sorted(key for key, value in params["write_only"].items() if value in (None, ""))
        if missing:
            raise ValueError(f"{params['id']} does not exist; creating it needs {', '.join(missing)}")
        options = {**params["options"], **params["create_only"], **params["write_only"]}
        command = [COMMAND, *section, "create", params["id"], *params["positional"], *option_args(options)]
        return "create", command, sorted(params["options"])
    changed = sorted(key for key, value in params["options"].items() if not matches(value, current.get(key)))
    options = {key: params["options"][key] for key in changed}
    if params["update_write_only"]:
        options.update(params["write_only"])
        changed += sorted(params["write_only"])
    if not options:
        return "none", None, []
    return "update", [COMMAND, *section, "update", params["id"], *option_args(options)], changed


def main():
    from ansible.module_utils.basic import AnsibleModule

    module = AnsibleModule(
        argument_spec={
            "section": {"type": "list", "elements": "str", "required": True},
            "id": {"type": "str", "required": True},
            "id_key": {"type": "str", "default": "id"},
            "positional": {"type": "list", "elements": "str", "default": []},
            "options": {"type": "dict", "default": {}},
            "create_only": {"type": "dict", "default": {}},
            "write_only": {"type": "dict", "default": {}, "no_log": True},
            "update_write_only": {"type": "bool", "default": False},
        },
        supports_check_mode=True,
    )
    params = module.params
    _, output, _ = module.run_command(
        [COMMAND, *params["section"], "list", "--output-format", "json"], check_rc=True)
    try:
        action, command, changed = plan(json.loads(output or "[]"), params)
    except ValueError as error:
        module.fail_json(msg=str(error))
    if command and not module.check_mode:
        module.run_command(command, check_rc=True)
    module.exit_json(changed=command is not None, action=action, changed_options=changed)


if __name__ == "__main__":
    main()
