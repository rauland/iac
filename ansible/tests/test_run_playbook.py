"""Offline checks for target isolation and baseline ordering."""
import json
import os
from pathlib import Path
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

    def test_vault_runs_baseline_then_only_vault(self):
        result, calls = self.run_target('dev', 'vault', '--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c['args'] for c in calls], [
            ['./playbooks/managed.yml', '--limit', 'dev:&tag_vault', '--check'],
            ['./playbooks/vault.yml', '--limit', 'dev:&tag_vault', '--check']])
        self.assertTrue(all(c['cwd'] == str(RUNNER.parent) for c in calls))

    def test_sandbox_has_its_own_playbook(self):
        result, calls = self.run_target('dev', 'sandbox')
        self.assertEqual(result.returncode, 0)
        self.assertEqual([c['args'][0] for c in calls],
                         ['./playbooks/managed.yml', './playbooks/sandbox.yml'])
        self.assertTrue(all(c['args'][-1] == 'dev:&tag_sandbox' for c in calls))

    def test_managed_runs_baseline_once(self):
        result, calls = self.run_target('prod', 'managed')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['args'], ['./playbooks/managed.yml', '--limit', 'prod:&tag_managed'])

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


if __name__ == '__main__':
    unittest.main()
