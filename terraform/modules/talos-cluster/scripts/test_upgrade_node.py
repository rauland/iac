"""Verify upgrade ordering and failure handling without contacting a cluster."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("upgrade-node.sh").resolve()


class UpgradeTests(unittest.TestCase):
    def run_upgrade(self, fail_command="", node="192.0.2.10"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "commands"
            stub = root / "talosctl"
            stub.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "with open(os.environ['TEST_LOG'], 'a') as log:\n"
                "    log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                "sys.exit(1 if os.environ['FAIL_COMMAND'] in sys.argv[1:] else 0)\n"
            )
            stub.chmod(0o755)
            env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}",
                       TALOSCONFIG=str(root / "talosconfig"), TEST_LOG=str(log),
                       FAIL_COMMAND=fail_command)
            result = subprocess.run(
                ["bash", str(SCRIPT), node, "factory.example/installer/test:v1.11.3",
                 "192.0.2.10", "192.0.2.11"],
                env=env, capture_output=True, text=True,
            )
            commands = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            return result, commands

    def test_one_node_between_two_health_checks(self):
        result, commands = self.run_upgrade()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(commands), 3)
        self.assertIn("health", commands[0])
        self.assertIn("upgrade", commands[1])
        self.assertIn("--wait", commands[1])
        self.assertEqual(commands[0], commands[2])
        self.assertEqual(commands[1][commands[1].index("--nodes") + 1], "192.0.2.10")

    def test_unhealthy_cluster_is_not_upgraded(self):
        result, commands = self.run_upgrade(fail_command="health")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(commands), 1)

    def test_failed_upgrade_stops(self):
        result, commands = self.run_upgrade(fail_command="upgrade")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(commands), 2)

    def test_multiple_or_unknown_nodes_are_rejected(self):
        for node in ("192.0.2.10,192.0.2.11", "192.0.2.99"):
            result, commands = self.run_upgrade(node=node)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(commands, [])


if __name__ == "__main__":
    unittest.main()
