#!/usr/bin/env python3
"""Apply the saved plan after checking it is the one reviewed for this target and run."""

import argparse
import os
import subprocess

from plan_manifest import check_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--destroy", choices=("true", "false"), default="false")
    args = parser.parse_args()
    check_manifest(args.directory, os.environ, args.environment, args.target, args.destroy == "true")
    subprocess.run(["terraform", "apply", "-input=false", "tfplan"], cwd=args.directory, check=True)


if __name__ == "__main__":
    main()
