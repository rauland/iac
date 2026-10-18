#!/usr/bin/env python3
"""Terraform external data source: build a deterministic, content-addressed NoCloud ISO."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

import pycdlib


def build(files):
    if set(files) != {"user-data", "meta-data", "network-config"} or not all(isinstance(value, str) for value in files.values()):
        raise ValueError("Expected only the three NoCloud configuration documents")
    # ISO directory records and volume descriptors otherwise use the local clock.
    # This runs in its own process; freeze the library's timestamps and timezone.
    os.environ["TZ"] = "UTC"
    time.tzset()
    output = io.BytesIO()
    with patch("time.time", return_value=946684800):
        iso = pycdlib.PyCdlib()
        iso.new(interchange_level=3, vol_ident="CIDATA", joliet=3, rock_ridge="1.09")
        buffers = []
        for index, filename in enumerate(sorted(files)):
            data = files[filename].encode()
            buffers.append(io.BytesIO(data))
            iso.add_fp(buffers[-1], len(data), iso_path=f"/FILE{index}.;1",
                       rr_name=filename, joliet_path="/" + filename)
        iso.write_fp(output)
        iso.close()
    return output.getvalue()


def main():
    data = build(json.load(sys.stdin))
    digest = hashlib.sha256(data).hexdigest()
    directory = Path(".cloud-init")
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / (digest + ".iso")
    # Avoid touching an identical file: provider metadata must stay stable too.
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)
        path.chmod(0o600)
    print(json.dumps({"path": path.as_posix(), "sha256": digest}))


if __name__ == "__main__":
    main()
