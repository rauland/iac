#!/usr/bin/python3
"""Allow host-key reads while preserving the AlmaLinux agent RPC restrictions."""
from pathlib import Path
import re
import shlex


def configure(path):
    text = path.read_text()
    matches = list(re.finditer(r"(?m)^FILTER_RPC_ARGS=(.*)$", text))
    if len(matches) != 1:
        raise ValueError("Expected one explicit guest-agent RPC policy")
    value = shlex.split(matches[0].group(1))
    arguments = shlex.split(value[0]) if len(value) == 1 else []
    if len(arguments) != 1 or "=" not in arguments[0]:
        raise ValueError("Unsupported guest-agent RPC policy")
    kind, commands = arguments[0].split("=", 1)
    commands = set(commands.split(","))
    required = {"guest-file-open", "guest-file-read", "guest-file-close"}
    forbidden = {"guest-file-write", "guest-exec", "guest-exec-status"}
    if kind == "--allow-rpcs" and not commands & forbidden:
        commands |= required
    elif kind == "--block-rpcs" and forbidden <= commands:
        commands -= required
    else:
        raise ValueError("Refusing to weaken an unknown guest-agent RPC policy")
    replacement = 'FILTER_RPC_ARGS="' + kind + "=" + ",".join(sorted(commands)) + '"'
    path.write_text(text[:matches[0].start()] + replacement + text[matches[0].end():])


if __name__ == "__main__":
    configure(Path("/etc/sysconfig/qemu-ga"))
