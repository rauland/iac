"""Run the installed inventory plugin against a pool-scoped fake Proxmox API."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from urllib.parse import urlsplit


ANSIBLE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('ansible-inventory'), 'Ansible is not installed')
class ScopedInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.requests = []
        self.deny_inventory = False
        owner = self

        class ProxmoxHandler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                path = urlsplit(self.path).path.removeprefix('/api2/json')
                owner.requests.append(path)
                auth = self.headers.get('Authorization', '')
                environment = next((scope for scope in ('dev', 'prod')
                                    if auth == f'PVEAPIToken=ansible-{scope}@pve!ci=placeholder'), None)
                if not environment or owner.deny_inventory or path == '/cluster/status':
                    self.send_error(403, 'Global Sys.Audit is not granted')
                    return
                vmid = 103 if environment == 'dev' else 203
                guest = dict(vmid=vmid, name=f'{environment}-vault', status='running',
                             type='qemu', node='pve', tags='common;vault')
                responses = {
                    '/nodes': [dict(node='pve', type='node', status='online')],
                    '/nodes/pve/lxc': [],
                    '/nodes/pve/qemu': [guest],
                    '/cluster/resources': [guest],
                    '/pools': [dict(poolid=environment)],
                    f'/pools/{environment}': dict(members=[guest]),
                    f'/nodes/pve/qemu/{vmid}/status/current': dict(status='running', qmpstatus='running'),
                    f'/nodes/pve/qemu/{vmid}/config': dict(tags='common;vault', ipconfig0=f'ip=10.0.0.{vmid}/24'),
                    f'/nodes/pve/qemu/{vmid}/snapshot': [],
                }
                if path not in responses:
                    self.send_error(403, 'Resource outside inventory scope')
                    return
                payload = json.dumps(dict(data=responses[path])).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), ProxmoxHandler)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever,
                         kwargs=dict(poll_interval=0.05), daemon=True).start()

    def environment(self, scope):
        env = os.environ.copy()
        env.pop('PROXMOX_PASSWORD', None)
        env.update(ANSIBLE_CONFIG=str(ANSIBLE / 'ansible.cfg'),
                   ANSIBLE_LOCAL_TEMP=self.temp.name,
                   PROXMOX_URL=f'http://127.0.0.1:{self.server.server_port}',
                   PROXMOX_USER=f'ansible-{scope}@pve', PROXMOX_TOKEN_ID='ci',
                   PROXMOX_TOKEN_SECRET='placeholder')
        return env

    def inventory(self, scope):
        result = subprocess.run(['ansible-inventory', '--list'], cwd=ANSIBLE,
                                env=self.environment(scope), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('/cluster/status', self.requests)
        self.assertIn('/nodes', self.requests)
        return json.loads(result.stdout)

    def test_dev_inventory_works_without_global_cluster_audit(self):
        inventory = self.inventory('dev')
        self.assertEqual(inventory['proxmox_pool_dev']['hosts'], ['dev-vault'])
        self.assertEqual(inventory['tag_common']['hosts'], ['dev-vault'])
        self.assertEqual(inventory['_meta']['hostvars']['dev-vault']['system_packages_base'],
                         ['qemu-guest-agent'])
        # Newer Ansible preserves the untrusted-string tag in inventory JSON.
        self.assertIn(inventory['_meta']['hostvars']['dev-vault']['ansible_host'],
                      ('10.0.0.103', {'__ansible_unsafe': '10.0.0.103'}))
        self.assertNotIn('prod-vault', inventory['_meta']['hostvars'])

    def test_prod_inventory_works_without_global_cluster_audit(self):
        inventory = self.inventory('prod')
        self.assertEqual(inventory['proxmox_pool_prod']['hosts'], ['prod-vault'])
        self.assertEqual(inventory['tag_common']['hosts'], ['prod-vault'])
        self.assertEqual(inventory['_meta']['hostvars']['prod-vault']['system_packages_base'],
                         ['qemu-guest-agent'])
        self.assertNotIn('dev-vault', inventory['_meta']['hostvars'])

    def test_permission_failure_stops_playbooks_instead_of_skipping_hosts(self):
        self.deny_inventory = True
        result = subprocess.run(['bash', 'run-playbook.sh', 'dev', 'vault', '--list-hosts'],
                                cwd=ANSIBLE, env=self.environment('dev'), text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('403', result.stderr)
        self.assertNotIn('play #', result.stdout)


if __name__ == '__main__':
    unittest.main()
