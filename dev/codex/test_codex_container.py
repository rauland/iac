"""Exercise lifecycle and mount boundaries without a container daemon."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


HELPER = Path(__file__).with_name('codex-container')


class ContainerCommands(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.calls = self.root / 'calls.jsonl'
        engine = self.root / 'docker'
        engine.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['CALLS'], 'a') as output:
    output.write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[1] == 'inspect':
    print(os.environ.get('MANAGED', 'true'))
''')
        engine.chmod(0o755)
        self.env = dict(os.environ, CONTAINER_ENGINE='docker', CALLS=str(self.calls))
        self.env['PATH'] = f"{self.root}:{os.environ['PATH']}"
        self.env.pop('CODEX_CONTAINER_IMAGE', None)
        self.env.pop('CODEX_CONTAINER_VERSION', None)

    def run_helper(self, *args):
        return subprocess.run([str(HELPER), *args], env=self.env,
                              capture_output=True, text=True)

    def recorded_calls(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def test_project_with_spaces_is_the_only_mount(self):
        project = self.root / 'my project'
        project.mkdir()
        result = self.run_helper('start', 'feature', str(project))
        self.assertEqual(result.returncode, 0, result.stderr)
        run = self.recorded_calls()[-1]
        self.assertEqual(run.count('--mount'), 1)
        self.assertEqual(run[run.index('--mount') + 1],
                         f'type=bind,src={project},dst=/workspace')
        self.assertIn('--rm', run)
        self.assertIn('--detach', run)
        self.assertIn('--cap-drop=ALL', run)
        self.assertIn('--security-opt=no-new-privileges', run)
        self.assertNotIn('--privileged', run)
        self.assertEqual(run[run.index('--user') + 1], f'{os.getuid()}:{os.getgid()}')

    def test_stop_refuses_unmanaged_container(self):
        self.env['MANAGED'] = 'false'
        result = self.run_helper('stop', 'unrelated')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not managed', result.stderr)
        self.assertEqual([call[0] for call in self.recorded_calls()], ['inspect'])

    def test_stop_targets_only_named_managed_container(self):
        result = self.run_helper('stop', 'feature')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.recorded_calls()[-1], ['stop', 'codex-feature'])

    def test_attach_reuses_tmux_session(self):
        result = self.run_helper('attach', 'feature')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.recorded_calls()[-1][-8:],
                         ['codex-feature', 'tmux', 'new-session', '-A', '-s',
                          'codex', '-c', '/workspace'])

    def test_exec_preserves_literal_command_arguments(self):
        command = ['printf', '%s', 'a b;$(touch should-not-exist)']
        result = self.run_helper('exec', 'feature', *command)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.recorded_calls()[-1],
                         ['exec', '--interactive', 'codex-feature', *command])

    def test_refuses_broad_mounts_and_option_like_names(self):
        for args in [('start', 'feature', '/'),
                     ('start', 'feature', str(Path.home())),
                     ('stop', '--all')]:
            with self.subTest(args=args):
                result = self.run_helper(*args)
                self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_build_does_not_take_codex_session_version_as_image_version(self):
        self.env['CODEX_VERSION'] = '0.0.0-session'
        result = self.run_helper('build')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('CODEX_VERSION=0.162.1', self.recorded_calls()[-1])

    def test_installed_symlink_resolves_image_sources(self):
        installed = self.root / 'codex-container'
        installed.symlink_to(HELPER)
        result = subprocess.run([str(installed), 'build'], env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.recorded_calls()[-1][-1], str(HELPER.parent.resolve()))

    def test_private_environment_file_is_passed_without_executing_or_printing_values(self):
        project = self.root / 'project'
        project.mkdir()
        credentials = self.root / 'dev.env'
        credentials.write_text('DEV_TOKEN=$(touch sentinel);example-value\n')
        credentials.chmod(0o600)
        result = self.run_helper('start', 'feature', str(project), '--env-file', str(credentials))
        self.assertEqual(result.returncode, 0, result.stderr)
        run = self.recorded_calls()[-1]
        self.assertEqual(run[run.index('--env-file') + 1], str(credentials))
        self.assertNotIn('example-value', result.stdout + result.stderr + json.dumps(run))
        self.assertFalse((Path.cwd() / 'sentinel').exists())

    def test_credential_directory_is_mounted_read_only(self):
        project = self.root / 'project'
        project.mkdir()
        credentials = self.root / 'credentials with spaces'
        credentials.mkdir(mode=0o700)
        result = self.run_helper('start', 'feature', '--credentials-dir', str(credentials), str(project))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'type=bind,src={credentials},dst=/run/credentials,readonly',
                      self.recorded_calls()[-1])

    def test_credential_inputs_are_rejected_before_calling_engine(self):
        project = self.root / 'project'
        project.mkdir()
        exposed_file = self.root / 'exposed.env'
        exposed_file.write_text('DEV_TOKEN=example-value\n')
        exposed_file.chmod(0o644)
        in_project = project / 'private.env'
        in_project.write_text('DEV_TOKEN=example-value\n')
        in_project.chmod(0o600)
        exposed_directory = self.root / 'exposed-directory'
        exposed_directory.mkdir(mode=0o755)
        in_project_directory = project / 'credentials'
        in_project_directory.mkdir(mode=0o700)
        for options in [
            ['--env-file', str(exposed_file)],
            ['--env-file', str(in_project)],
            ['--env-file', str(self.root / 'missing.env')],
            ['--env-file'],
            ['--credentials-dir', str(exposed_directory)],
            ['--credentials-dir', str(in_project_directory)],
            ['--credentials-dir', str(Path.home())],
        ]:
            with self.subTest(options=options):
                result = self.run_helper('start', 'feature', str(project), *options)
                self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_build_does_not_receive_session_credentials(self):
        result = self.run_helper('build', '--env-file', 'dev.env')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls.exists())


if __name__ == '__main__':
    unittest.main()
