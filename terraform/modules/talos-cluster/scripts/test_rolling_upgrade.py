"""Verify rolling upgrade ordering, resume and version checks without a cluster."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("rolling-upgrade.py").resolve()
INVENTORY = {
    "talos_version": "v1.14.3",
    "installer_image": "factory.example/metal-installer-secureboot/abc:v1.14.3",
    "control_planes": ["192.0.2.10"],
    "workers": ["192.0.2.11", "192.0.2.12"],
}
# Fake talosctl: reports VERSIONS[node] and records every call. A successful
# upgrade changes the node's reported version, as a real reboot would.
STUB = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
state_path = os.environ['TEST_STATE']
state = json.load(open(state_path))
state['calls'].append(args)
node = args[args.index('--nodes') + 1] if '--nodes' in args else ''
code = 1 if os.environ['FAIL'] and os.environ['FAIL'] in (' '.join(args)) else 0
if 'version' in args:
    print('Client:\\n\\tTag:         v9.9.9\\nServer:\\n\\tNODE:        %s\\n\\tTag:         %s' % (node, state['versions'][node]))
elif 'upgrade' in args and not code:
    state['versions'][node] = args[args.index('--image') + 1].rsplit(':', 1)[1]
json.dump(state, open(state_path, 'w'))
sys.exit(code)
"""


class RollingUpgradeTests(unittest.TestCase):
    def run_upgrade(self, versions, target, component="talos", fail=""):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "talosctl").write_text(STUB)
            (root / "talosctl").chmod(0o755)
            (root / "inventory.json").write_text(json.dumps(INVENTORY))
            state = root / "state.json"
            state.write_text(json.dumps({"calls": [], "versions": versions}))
            env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}",
                       TALOSCONFIG=str(root / "talosconfig"), TEST_STATE=str(state), FAIL=fail)
            result = subprocess.run(
                ["python3", str(SCRIPT), "--component", component, "--version", target,
                 "--inventory", str(root / "inventory.json")],
                env=env, capture_output=True, text=True)
            return result, json.loads(state.read_text())

    @staticmethod
    def upgraded(state):
        return [call[call.index("--nodes") + 1] for call in state["calls"] if "upgrade" in call]

    def all_at(self, version):
        return {node: version for node in INVENTORY["control_planes"] + INVENTORY["workers"]}

    def test_control_planes_first_then_each_worker(self):
        result, state = self.run_upgrade(self.all_at("v1.14.3"), "v1.15.0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.upgraded(state), ["192.0.2.10", "192.0.2.11", "192.0.2.12"])
        images = {call[call.index("--image") + 1] for call in state["calls"] if "upgrade" in call}
        self.assertEqual(images, {"factory.example/metal-installer-secureboot/abc:v1.15.0"})

    def test_rerun_skips_nodes_already_upgraded(self):
        versions = self.all_at("v1.14.3") | {"192.0.2.10": "v1.15.0"}
        result, state = self.run_upgrade(versions, "v1.15.0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.upgraded(state), ["192.0.2.11", "192.0.2.12"])

    def test_failure_stops_before_later_nodes(self):
        result, state = self.run_upgrade(self.all_at("v1.14.3"), "v1.15.0",
                                         fail="--nodes 192.0.2.11 upgrade")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.upgraded(state), ["192.0.2.10", "192.0.2.11"])
        self.assertEqual(state["versions"]["192.0.2.12"], "v1.14.3")

    def test_skipped_minor_or_downgrade_changes_nothing(self):
        for versions, target in ((self.all_at("v1.14.3"), "v1.16.0"),
                                 (self.all_at("v1.14.3") | {"192.0.2.12": "v1.13.4"}, "v1.15.0"),
                                 (self.all_at("v1.14.3"), "v1.14.1")):
            result, state = self.run_upgrade(versions, target)
            self.assertNotEqual(result.returncode, 0, target)
            self.assertEqual(self.upgraded(state), [], target)

    def test_unpinned_version_is_rejected(self):
        result, state = self.run_upgrade(self.all_at("v1.14.3"), "latest")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(state["calls"], [])

    def test_kubernetes_between_health_checks(self):
        result, state = self.run_upgrade(self.all_at("v1.14.3"), "v1.38.0", component="kubernetes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        steps = [next(arg for arg in call if arg in {"health", "upgrade-k8s"}) for call in state["calls"]]
        self.assertEqual(steps, ["health", "upgrade-k8s", "health"])
        self.assertIn("v1.38.0", state["calls"][1])

    def test_unhealthy_cluster_blocks_kubernetes_upgrade(self):
        result, state = self.run_upgrade(self.all_at("v1.14.3"), "v1.38.0",
                                         component="kubernetes", fail="health")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(state["calls"]), 1)


if __name__ == "__main__":
    unittest.main()
