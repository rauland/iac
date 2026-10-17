"""Offline event/diff tests for Terraform root discovery."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("terraform-roots.py").resolve()


class RootDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        self.roots = ["dev/sandbox", "dev/vault", "platform/images"]
        for root in self.roots:
            directory = f"terraform/{root}" if root.startswith("platform/") else f"terraform/workloads/{root}"
            self.write(f"{directory}/main.tf", "# root\n")
        self.write("terraform/platform/access/main.tf", "# privileged root\n")
        self.write("terraform/platform/state-access/main.tf", "# IAM administration\n")
        self.base = self.commit()

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True).strip()

    def write(self, name, content):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    def discover(self, event="push", **overrides):
        import json

        output = self.repo / "outputs"
        env = dict(os.environ, EVENT_NAME=event, BASE_SHA=self.base,
                   HEAD_SHA=self.git("rev-parse", "HEAD"), GITHUB_OUTPUT=str(output))
        env.update(overrides)
        result = subprocess.run(["python3", str(SCRIPT)], cwd=self.repo,
                                env=env, text=True, capture_output=True)
        if result.returncode:
            return result, None
        values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        matrix = json.loads(values["matrix"])
        roots = [f"{r['environment']}/{r['target']}" for r in matrix]
        for root in matrix:
            expected = (f"terraform/platform/{root['target']}" if root['environment'] == 'platform'
                        else f"terraform/workloads/{root['environment']}/{root['target']}")
            self.assertEqual(root['directory'], expected)
        if len(matrix) == 1:
            self.assertEqual(values['directory'], matrix[0]['directory'])
        self.assertEqual(values["has-changes"], str(bool(roots)).lower())
        return result, roots

    def test_push_covers_every_commit_in_push(self):
        for root in self.roots[:2]:
            self.write(f"terraform/workloads/{root}/main.tf", "# changed\n")
            self.commit()
        self.assertEqual(self.discover()[1], self.roots[:2])

    def test_pr_excludes_changes_only_on_base_branch(self):
        self.write("terraform/workloads/dev/sandbox/main.tf", "# feature\n")
        head = self.commit()
        self.git("checkout", "-q", self.base)
        self.write("terraform/workloads/dev/vault/main.tf", "# base update\n")
        base = self.commit()
        self.assertEqual(self.discover("pull_request", BASE_SHA=base, HEAD_SHA=head)[1],
                         ["dev/sandbox"])

    def test_shared_module_or_automation_change_selects_all(self):
        for name in ("terraform/modules/example/main.tf", ".github/scripts/helper.py",
                     ".github/workflows/terraform.yml", "ssh/public_keys/dev/ansible-ci.pub",
                     "ssh/known_hosts/dev", "ansible/roles/automation_user/tasks/main.yml",
                     ".github/actions/ssh/action.yml"):
            with self.subTest(path=name):
                base = self.git("rev-parse", "HEAD")
                self.write(name, "# changed\n")
                self.commit()
                self.assertEqual(self.discover(BASE_SHA=base)[1], self.roots)

    def test_unrelated_change_has_empty_matrix(self):
        self.write("README.md", "documentation\n")
        self.commit()
        self.assertEqual(self.discover()[1], [])

    def test_first_push_selects_all(self):
        self.assertEqual(self.discover(BASE_SHA="0" * 40)[1], self.roots)

    def test_disabled_root_cannot_be_deployed(self):
        self.write("terraform/workloads/dev/sandbox/.disabled", "disabled\n")
        self.commit()
        self.assertEqual(self.discover()[1], [])
        self.assertEqual(self.discover(BASE_SHA="0" * 40)[1], self.roots[1:])
        result, _ = self.discover("workflow_dispatch", SELECTED_ENV="dev",
                                  SELECTED_TARGET="sandbox")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("disabled", result.stderr)

    def test_manual_selection_and_invalid_combination(self):
        self.assertEqual(self.discover("workflow_dispatch", SELECTED_ENV="platform",
                                       SELECTED_TARGET="images")[1], ["platform/images"])
        result, _ = self.discover("workflow_dispatch", SELECTED_ENV="prod",
                                  SELECTED_TARGET="sandbox")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No Terraform root", result.stderr)

    def test_manual_all_selects_only_chosen_environment_and_ignores_target(self):
        for environment, expected in [('dev', self.roots[:2]),
                                      ('platform', ['platform/images'])]:
            with self.subTest(environment=environment):
                self.assertEqual(self.discover(
                    'workflow_dispatch', DEPLOYMENT_MODE='all',
                    SELECTED_ENV=environment, SELECTED_TARGET='ignored')[1], expected)

    def test_manual_all_excludes_disabled_roots(self):
        self.write('terraform/workloads/dev/sandbox/.disabled', 'disabled\n')
        self.assertEqual(self.discover(
            'workflow_dispatch', DEPLOYMENT_MODE='all', SELECTED_ENV='dev')[1],
            ['dev/vault'])

    def test_manual_all_rejects_environment_without_enabled_roots(self):
        result, _ = self.discover('workflow_dispatch', DEPLOYMENT_MODE='all',
                                  SELECTED_ENV='missing')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('No enabled Terraform roots', result.stderr)

    def test_manual_rejects_unknown_mode(self):
        result, _ = self.discover('workflow_dispatch', DEPLOYMENT_MODE='unknown',
                                  SELECTED_ENV='dev', SELECTED_TARGET='sandbox')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Unsupported deployment mode', result.stderr)

    def test_platform_image_change_selects_only_images(self):
        self.write('terraform/platform/images/main.tf', '# changed\n')
        self.commit()
        self.assertEqual(self.discover()[1], ['platform/images'])

    def test_platform_access_is_never_a_deployment_target(self):
        for target in ['access', 'state-access']:
            with self.subTest(target=target):
                self.write(f'terraform/platform/{target}/main.tf', '# changed access\n')
                self.commit()
                self.assertEqual(self.discover()[1], [])
                result, _ = self.discover('workflow_dispatch', SELECTED_ENV='platform',
                                          SELECTED_TARGET=target)
                self.assertNotEqual(result.returncode, 0)

    def test_legacy_prod_images_selection_is_rejected(self):
        result, _ = self.discover('workflow_dispatch', SELECTED_ENV='prod',
                                  SELECTED_TARGET='images')
        self.assertNotEqual(result.returncode, 0)

    def test_platform_images_can_be_disabled(self):
        self.write('terraform/platform/images/.disabled', 'disabled\n')
        self.commit()
        self.assertEqual(self.discover(BASE_SHA='0' * 40)[1], self.roots[:2])
        result, _ = self.discover('workflow_dispatch', SELECTED_ENV='platform',
                                  SELECTED_TARGET='images')
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
