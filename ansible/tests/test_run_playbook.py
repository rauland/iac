"""Offline checks for target isolation and optional managed baseline."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

RUNNER = Path(__file__).resolve().parents[1] / "run-playbook.sh"


class PlaybookSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = self.root / "calls.jsonl"
        fake = self.root / "ansible-playbook"
        fake.write_text("""#!/usr/bin/env python3
import json, os, sys
with open(os.environ['CALL_LOG'], 'a') as log:
    log.write(json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd()}) + '\\n')
if os.environ.get('FAIL_BASELINE') and sys.argv[1].endswith('/managed.yml'):
    sys.exit(7)
""")
        fake.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{self.root}:{os.environ['PATH']}",
                        CALL_LOG=str(self.log))

    def run_target(self, *args):
        result = subprocess.run(['bash', str(RUNNER), *args], cwd=self.root,
                                env=self.env, capture_output=True, text=True)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return result, calls

    def test_vault_selects_managed_and_vault_playbooks(self):
        result, calls = self.run_target('dev', 'vault', '--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c['args'] for c in calls], [
            ['./playbooks/managed.yml', '--limit', 'proxmox_pool_dev:&tag_vault', '--check'],
            ['./playbooks/vault.yml', '--limit', 'proxmox_pool_dev:&tag_vault', '--check']])
        self.assertTrue(all(c['cwd'] == str(RUNNER.parent) for c in calls))

    def test_sandbox_has_its_own_playbook(self):
        result, calls = self.run_target('dev', 'sandbox')
        self.assertEqual(result.returncode, 0)
        self.assertEqual([c['args'][0] for c in calls],
                         ['./playbooks/managed.yml', './playbooks/sandbox.yml'])
        self.assertTrue(all(c['args'][-1] == 'proxmox_pool_dev:&tag_sandbox' for c in calls))

    def test_managed_runs_baseline_once(self):
        result, calls = self.run_target('prod', 'managed')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['args'], ['./playbooks/managed.yml', '--limit', 'proxmox_pool_prod:&tag_managed'])

    def test_baseline_failure_stops_service_apply(self):
        self.env['FAIL_BASELINE'] = '1'
        result, calls = self.run_target('dev', 'vault')
        self.assertEqual(result.returncode, 7)
        self.assertEqual(len(calls), 1)

    def test_invalid_scope_cannot_apply(self):
        for args in [('dev', 'all'), ('all', 'vault'), ('dev',)]:
            result, calls = self.run_target(*args)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(calls, [])


@unittest.skipUnless(shutil.which('ansible-playbook'), 'Ansible is not installed')
class HostSelectionTests(unittest.TestCase):
    def list_hosts(self, target, environment='dev'):
        with tempfile.TemporaryDirectory() as local_temp:
            env = dict(os.environ, ANSIBLE_LOCAL_TEMP=local_temp)
            command = ['bash', str(RUNNER), environment, target]
            result = subprocess.run(
                command + ['-i', 'tests/inventory.yml', '--list-hosts'],
                cwd=RUNNER.parent, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        # Retain each play's host set to check baseline and service selection.
        return [set(re.findall(r'^      (\S+)$', block, re.MULTILINE))
                for block in result.stdout.split('  play #')[1:]]

    def test_vault_target_runs_service_for_managed_and_unmanaged_hosts(self):
        self.assertEqual(self.list_hosts('vault'), [
            {'dev-vault'}, {'dev-vault', 'dev-unmanaged-vault'}])

    def test_sandbox_target_runs_service_for_managed_and_unmanaged_hosts(self):
        self.assertEqual(self.list_hosts('sandbox'), [
            {'dev-sandbox'}, {'dev-sandbox', 'dev-unmanaged-sandbox'}])

    def test_managed_target_selects_only_managed_hosts(self):
        self.assertEqual(self.list_hosts('managed'), [
            {'dev-vault', 'dev-sandbox'}])

    def test_prod_pool_overrides_stale_environment_groups_and_excludes_unpooled_hosts(self):
        self.assertEqual(self.list_hosts('vault', 'prod'), [
            {'prod-vault'}, {'prod-vault'}])


if __name__ == '__main__':
    unittest.main()
