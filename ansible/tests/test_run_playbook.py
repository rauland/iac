"""Offline checks for target isolation and optional common baseline."""
import json
import os
from pathlib import Path
import re
import shlex
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
    log.write(json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd(),
                         'environment': os.environ.get('ANSIBLE_ENVIRONMENT'),
                         'private_key_file': os.environ.get('ANSIBLE_PRIVATE_KEY_FILE'),
                         'host_key_checking': os.environ.get('ANSIBLE_HOST_KEY_CHECKING'),
                         'ssh_args': os.environ.get('ANSIBLE_SSH_COMMON_ARGS')}) + '\\n')
if os.environ.get('FAIL_BASELINE') and sys.argv[1].endswith('/common.yml'):
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

    def test_sandbox_selects_common_and_sandbox_playbooks(self):
        result, calls = self.run_target('dev', 'sandbox', '--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c['args'] for c in calls], [
            ['./playbooks/common.yml', '--limit', 'proxmox_pool_dev:&tag_sandbox', '--check'],
            ['./playbooks/sandbox.yml', '--limit', 'proxmox_pool_dev:&tag_sandbox', '--check']])
        self.assertTrue(all(c['cwd'] == str(RUNNER.parent) for c in calls))

    def test_common_runs_baseline_once(self):
        result, calls = self.run_target('prod', 'common')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['args'], ['./playbooks/common.yml', '--limit', 'proxmox_pool_prod:&tag_common'])

    def test_baseline_failure_stops_service_apply(self):
        self.env['FAIL_BASELINE'] = '1'
        result, calls = self.run_target('dev', 'sandbox')
        self.assertEqual(result.returncode, 7)
        self.assertEqual(len(calls), 1)

    def test_invalid_scope_cannot_apply(self):
        for args in [('dev', 'all'), ('all', 'sandbox'), ('dev', 'managed'), ('dev', 'vault'), ('dev',)]:
            result, calls = self.run_target(*args)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(calls, [])

    def test_ssh_identity_and_trust_follow_environment(self):
        self.env.pop('ANSIBLE_PRIVATE_KEY_FILE', None)
        for environment in ('dev', 'prod'):
            self.log.unlink(missing_ok=True)
            result, calls = self.run_target(environment, 'common')
            self.assertEqual(result.returncode, 0, result.stderr)
            call = calls[0]
            self.assertEqual(call['environment'], environment)
            self.assertTrue(call['private_key_file'].endswith(f'/ssh/.credentials/{environment}/ansible-ci'))
            self.assertEqual(call['host_key_checking'], 'True')
            self.assertIn('StrictHostKeyChecking=yes', call['ssh_args'])
            self.assertIn('IdentitiesOnly=yes', call['ssh_args'])
            self.assertIn('IdentityAgent=none', call['ssh_args'])
            self.assertIn('GlobalKnownHostsFile=/dev/null', call['ssh_args'])
            self.assertIn('UpdateHostKeys=no', call['ssh_args'])
            self.assertIn(f'/ssh/known_hosts/{environment}', call['ssh_args'])

    def test_runtime_host_trust_file_preserves_strict_verification(self):
        trust = self.root / 'runtime known_hosts'
        trust.write_text('# Host keys verified during provisioning\n')
        self.env['ANSIBLE_KNOWN_HOSTS_FILE'] = str(trust)
        result, calls = self.run_target('dev', 'sandbox')
        self.assertEqual(result.returncode, 0, result.stderr)
        for call in calls:
            self.assertIn(f'UserKnownHostsFile="{trust}"', call['ssh_args'])
            # SSH must receive quotes as part of its -o value, after Ansible splits arguments.
            self.assertIn(f'UserKnownHostsFile="{trust}"', shlex.split(call['ssh_args']))
            self.assertIn('StrictHostKeyChecking=yes', call['ssh_args'])
            self.assertIn('GlobalKnownHostsFile=/dev/null', call['ssh_args'])
            self.assertEqual(call['host_key_checking'], 'True')

    def test_missing_runtime_host_trust_file_fails_before_playbooks(self):
        self.env['ANSIBLE_KNOWN_HOSTS_FILE'] = str(self.root / 'missing')
        result, calls = self.run_target('dev', 'sandbox')
        self.assertEqual(result.returncode, 2)
        self.assertIn('must exist and be readable', result.stderr)
        self.assertEqual(calls, [])

    def test_unsupported_trust_paths_fail_before_playbooks(self):
        for character in ("'", '"', '\\', '%', '$', '\n', '\r'):
            with self.subTest(character=character):
                trust = self.root / f'trust{character}file'
                trust.touch()
                self.env['ANSIBLE_KNOWN_HOSTS_FILE'] = str(trust)
                result, calls = self.run_target('dev', 'common')
                self.assertEqual(result.returncode, 2)
                self.assertIn('Unsupported characters', result.stderr)
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

    def test_sandbox_target_runs_service_with_and_without_common_baseline(self):
        self.assertEqual(self.list_hosts('sandbox'), [
            {'dev-sandbox'}, {'dev-sandbox', 'dev-service-only-sandbox'}])

    def test_common_target_selects_only_common_hosts(self):
        self.assertEqual(self.list_hosts('common'), [
            {'dev-sandbox'}])

    def test_prod_pool_overrides_stale_environment_groups_and_excludes_unpooled_hosts(self):
        self.assertEqual(self.list_hosts('sandbox', 'prod'), [
            {'prod-sandbox'}, {'prod-sandbox'}])


@unittest.skipUnless(shutil.which('ansible-playbook'), 'Ansible is not installed')
class PodmanScopeTests(unittest.TestCase):
    def test_only_tagged_sandbox_hosts_run_podman_and_unsupported_os_fails_before_packages(self):
        with tempfile.TemporaryDirectory() as local_temp:
            inventory = Path(local_temp) / 'inventory.yml'
            inventory.write_text('''---
all:
  vars:
    ansible_connection: local
  children:
    tag_sandbox:
      hosts:
        podman-host:
        generic-sandbox:
    tag_podman:
      hosts:
        podman-host:
''')
            env = dict(os.environ, ANSIBLE_LOCAL_TEMP=local_temp,
                       ANSIBLE_ROLES_PATH=str(RUNNER.parent / 'roles'))
            result = subprocess.run(
                ['ansible-playbook', str(RUNNER.parent / 'playbooks/sandbox.yml'),
                 '-i', str(inventory), '--check',
                 '-e', json.dumps({'ansible_facts': {'os_family': 'Unsupported'}})],
                cwd=RUNNER.parent, env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, result.stderr)
            self.assertIn('The Podman role requires a RHEL-family host', result.stdout)
            self.assertRegex(result.stdout, r'podman-host\s+:.*changed=0.*failed=1')
            self.assertRegex(result.stdout, r'generic-sandbox\s+:.*changed=0.*failed=0')


if __name__ == '__main__':
    unittest.main()
