"""Offline event/diff tests for independent infrastructure and configuration routing."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("deployment-targets.py").resolve()


class DeploymentTargetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        for root in ("dev/sandbox", "dev/vault", "dev/talos", "prod/vault"):
            self.write(f"terraform/workloads/{root}/main.tf", "# root\n")
        for root in ("images", "access", "state-access"):
            self.write(f"terraform/platform/{root}/main.tf", "# platform\n")
        self.base = self.commit()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True).strip()

    def write(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    def discover(self, event="push", **overrides):
        output = self.repo / "outputs"
        env = dict(os.environ, EVENT_NAME=event, BASE_SHA=self.base,
                   HEAD_SHA=self.git("rev-parse", "HEAD"), GITHUB_OUTPUT=str(output),
                   GITHUB_REF="refs/heads/main", DEPLOYMENT_MODE="auto",
                   DEPLOYMENT_SCOPE="single", SELECTED_ENV="dev", SELECTED_TARGET="vault")
        env.update(overrides)
        result = subprocess.run(["python3", str(SCRIPT)], cwd=self.repo,
                                env=env, text=True, capture_output=True)
        if result.returncode:
            return result, []
        values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        targets = json.loads(values["matrix"])
        self.assertEqual(json.loads(values["plan-matrix"]), [t for t in targets if t["terraform"]])
        self.assertEqual(values["has-targets"], str(bool(targets)).lower())
        return result, targets

    def change(self, *paths):
        for path in paths:
            self.write(path, "# changed\n")
        self.commit()
        result, targets = self.discover()
        self.assertEqual(result.returncode, 0, result.stderr)
        return {(t["environment"], t["target"]): (t["terraform"], t["ansible"])
                for t in targets}

    def test_infrastructure_change_only_selects_its_root(self):
        self.assertEqual(self.change("terraform/workloads/dev/vault/main.tf"),
                         {("dev", "vault"): (True, False)})

    def test_service_role_change_needs_no_terraform(self):
        self.assertEqual(self.change("ansible/roles/vault/tasks/common.yml"),
                         {("dev", "vault"): (False, True), ("prod", "vault"): (False, True)})

    def test_shared_baseline_change_selects_only_vm_targets(self):
        self.assertEqual(self.change("ansible/roles/automation_user/tasks/main.yml"),
                         {("dev", "sandbox"): (False, True), ("dev", "vault"): (False, True),
                          ("prod", "vault"): (False, True)})

    def test_service_inventory_variables_are_scoped(self):
        self.assertEqual(self.change("ansible/inventory/group_vars/tag_sandbox.yml"),
                         {("dev", "sandbox"): (False, True)})

    def test_shared_terraform_module_selects_all_enabled_roots(self):
        targets = self.change("terraform/modules/virtual-machine/main.tf")
        self.assertEqual(len(targets), 5)
        self.assertTrue(all(value == (True, False) for value in targets.values()))

    def test_key_changes_select_both_tools_in_the_correct_environment(self):
        self.assertEqual(self.change("ssh/public_keys/dev/ansible-ci.pub"),
                         {("dev", "sandbox"): (True, True), ("dev", "vault"): (True, True),
                          ("dev", "talos"): (True, False)})

    def test_host_enrollment_needs_only_configuration(self):
        self.assertEqual(self.change("ssh/known_hosts/prod"),
                         {("prod", "vault"): (False, True)})

    def test_docs_lint_tests_and_workflow_changes_do_not_deploy(self):
        self.assertEqual(self.change(
            "README.md", "ansible/roles/vault/README.md", "ansible/tests/test_new.py",
            "ansible/roles/vault/tests/test.yml", "ansible/.ansible-lint",
            "ansible/.yamllint", "ansible/requirements-lint.txt",
            ".github/actions/ansible-lint/action.yml", ".github/workflows/terraform.yml",
            ".github/scripts/test_deployment_targets.py"), {})

    def test_mixed_changes_select_both_tools(self):
        self.assertEqual(self.change("terraform/workloads/dev/vault/main.tf",
                                     "ansible/playbooks/vault.yml"),
                         {("dev", "vault"): (True, True), ("prod", "vault"): (False, True)})

    def test_push_includes_every_commit(self):
        self.write("terraform/workloads/dev/vault/main.tf", "# first\n")
        self.commit()
        self.assertEqual(len(self.change("ansible/playbooks/sandbox.yml")), 2)

    def test_pull_request_uses_merge_base(self):
        self.write("terraform/workloads/dev/vault/main.tf", "# feature\n")
        head = self.commit()
        self.git("checkout", "-q", self.base)
        self.write("terraform/workloads/dev/sandbox/main.tf", "# base\n")
        base = self.commit()
        result, targets = self.discover("pull_request", BASE_SHA=base, HEAD_SHA=head)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([t["target"] for t in targets], ["vault"])

    def test_first_push_includes_enabled_roots(self):
        self.assertEqual(len(self.discover(BASE_SHA="0" * 40)[1]), 5)

    def test_disabled_roots_are_excluded_from_automatic_configuration(self):
        self.write("terraform/workloads/dev/sandbox/.disabled", "disabled\n")
        targets = self.change("ansible/playbooks/common.yml")
        self.assertNotIn(("dev", "sandbox"), targets)

    def test_privileged_platform_roots_do_not_deploy(self):
        self.assertEqual(self.change("terraform/platform/access/main.tf",
                                     "terraform/platform/state-access/main.tf"), {})

    def test_manual_configuration_does_not_need_a_terraform_root(self):
        result, targets = self.discover("workflow_dispatch", DEPLOYMENT_MODE="configuration",
                                         SELECTED_ENV="prod", SELECTED_TARGET="common")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([(t["target"], t["terraform"], t["ansible"]) for t in targets],
                         [("common", False, True)])

    def test_manual_modes_have_independent_signals(self):
        for mode, expected in (("auto", (True, True, False)),
                               ("infrastructure", (True, False, False)),
                               ("configuration", (False, True, False)),
                               ("destroy", (True, False, True))):
            with self.subTest(mode=mode):
                result, targets = self.discover("workflow_dispatch", DEPLOYMENT_MODE=mode)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(tuple(targets[0][key] for key in ("terraform", "ansible", "destroy")),
                                 expected)

    def test_manual_all_configuration_skips_talos_and_disabled_roots(self):
        self.write("terraform/workloads/dev/sandbox/.disabled", "disabled\n")
        result, targets = self.discover("workflow_dispatch", DEPLOYMENT_MODE="configuration",
                                         DEPLOYMENT_SCOPE="all")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([t["target"] for t in targets], ["vault"])

    def test_invalid_manual_requests_cannot_deploy(self):
        invalid = [dict(GITHUB_REF="refs/heads/feature"), dict(DEPLOYMENT_MODE="invalid"),
                   dict(DEPLOYMENT_SCOPE="invalid"), dict(SELECTED_ENV="unknown"),
                   dict(SELECTED_ENV="platform", SELECTED_TARGET="access"),
                   dict(SELECTED_ENV="prod", SELECTED_TARGET="images"),
                   dict(DEPLOYMENT_MODE="configuration", SELECTED_TARGET="talos")]
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                result, _ = self.discover("workflow_dispatch", **overrides)
                self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
