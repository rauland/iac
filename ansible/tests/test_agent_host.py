"""Reject unsuitable hosts or SSH inputs before changing a machine."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ANSIBLE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('ansible-playbook'), 'Ansible is not installed')
class AgentHostGuardTests(unittest.TestCase):
    def test_invalid_bootstrap_inputs_fail_before_packages_or_accounts(self):
        valid = {
            'ansible_facts': {'distribution': 'Ubuntu', 'distribution_version': '24.04'},
            'agent_host_user': 'developer',
            'agent_host_authorized_keys': ['ssh-ed25519 AAAA test'],
        }
        cases = [
            {'ansible_facts': {'distribution': 'Ubuntu', 'distribution_version': '22.04'}},
            {'agent_host_user': 'root'},
            {'agent_host_authorized_keys': []},
            {'agent_host_authorized_keys': 'ssh-ed25519 AAAA test'},
            {'agent_host_authorized_keys': ['invalid']},
        ]
        with tempfile.TemporaryDirectory() as directory:
            playbook = Path(directory) / 'guards.yml'
            playbook.write_text('''---
- name: Validate bootstrap guards
  hosts: localhost
  connection: local
  gather_facts: false
  roles:
    - agent_host
''')
            env = dict(os.environ, ANSIBLE_LOCAL_TEMP=directory,
                       ANSIBLE_ROLES_PATH=str(ANSIBLE / 'roles'))
            for overrides in cases:
                with self.subTest(overrides=overrides):
                    result = subprocess.run(
                        ['ansible-playbook', str(playbook), '-i', 'localhost,',
                         '--check', '-e', json.dumps(dict(valid, **overrides))],
                        cwd=ANSIBLE, env=env, capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0, result.stderr)
                    self.assertIn('Use Ubuntu 24.04', result.stdout, result.stderr)
                    self.assertRegex(result.stdout, r'localhost\s+:.*changed=0.*failed=1')
                    self.assertNotIn('TASK [agent_host : Install rootless', result.stdout)
