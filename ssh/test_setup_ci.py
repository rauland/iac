"""Exercise real SSH-key parsing, environment matching and temporary-file cleanup."""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest


class SshSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ssh = self.root / 'ssh'
        self.ssh.mkdir()
        self.script = self.ssh / 'setup-ci.sh'
        shutil.copy(Path(__file__).with_name('setup-ci.sh'), self.script)
        self.runner = self.root / 'runner'
        self.runner.mkdir()
        self.keys = {}
        for environment in ('dev', 'prod'):
            key = self.root / environment
            subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)],
                           check=True, capture_output=True)
            public = self.ssh / 'public_keys' / environment / 'ansible-ci.pub'
            public.parent.mkdir(parents=True)
            shutil.copy(key.with_suffix('.pub'), public)
            self.keys[environment] = key.read_text()
        self.env_file = self.root / 'environment'
        self.output_file = self.root / 'output'
        self.env = dict(os.environ, RUNNER_TEMP=str(self.runner),
                        GITHUB_ENV=str(self.env_file), GITHUB_OUTPUT=str(self.output_file))

    def run_setup(self, environment, key):
        return subprocess.run(['bash', str(self.script), 'setup', environment],
                              env=dict(self.env, SSH_PRIVATE_KEY_ANSIBLE=key),
                              text=True, capture_output=True)

    def test_matching_keys_are_private_and_cleaned_up(self):
        for environment in ('dev', 'prod'):
            result = self.run_setup(environment, self.keys[environment])
            self.assertEqual(result.returncode, 0, result.stderr)
            directory = Path(self.output_file.read_text().splitlines()[-1].split('=', 1)[1])
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            private = directory / 'id_ed25519'
            self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o600)
            self.assertTrue(private.read_text().strip() == self.keys[environment].strip(),
                            'Temporary key did not preserve credential contents')
            self.assertIn(f'ANSIBLE_PRIVATE_KEY_FILE={private}', self.env_file.read_text())
            self.assertNotIn(self.keys[environment], result.stdout + result.stderr)
            cleanup = subprocess.run(['bash', str(self.script), 'cleanup', str(directory)],
                                     env=self.env, text=True, capture_output=True)
            self.assertEqual(cleanup.returncode, 0, cleanup.stderr)
            self.assertFalse(directory.exists())

    def test_dev_key_cannot_be_used_for_prod(self):
        result = self.run_setup('prod', self.keys['dev'])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('does not match the prod public key', result.stderr)
        self.assertEqual(list(self.runner.iterdir()), [])
        self.assertFalse(self.env_file.exists())

    def test_key_contents_are_not_executed(self):
        marker = self.root / 'executed'
        result = self.run_setup('dev', f'$(touch "{marker}")')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(marker.exists())
        self.assertEqual(list(self.runner.iterdir()), [])

    def test_cleanup_rejects_paths_outside_its_directory(self):
        for directory in (self.root, self.runner / 'ansible-ssh.test' / '..'):
            result = subprocess.run(['bash', str(self.script), 'cleanup', str(directory)],
                                    env=self.env, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(self.root.exists())


if __name__ == '__main__':
    unittest.main()
