"""Approval routing, no-op handling, and plan artifact identity checks."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "prepare_deployments", Path(__file__).with_name("prepare-deployments.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PrepareDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.context = dict(GITHUB_SHA="abc123", GITHUB_RUN_ID="42", GITHUB_RUN_ATTEMPT="2",
                            GITHUB_EVENT_NAME="push", GITHUB_REF="refs/heads/main")

    def target(self, environment="dev", name="vault", terraform=True, ansible=False, destroy=False):
        return dict(environment=environment, target=name,
                    directory=(f"terraform/platform/{name}" if environment == "platform"
                               else f"terraform/workloads/{environment}/{name}"),
                    terraform=terraform, ansible=ansible, destroy=destroy)

    def result(self, entry, changes=True, **overrides):
        result = dict(environment=entry["environment"], target=entry["target"],
                      changes=changes, destroy=entry["destroy"], sha=self.context["GITHUB_SHA"],
                      run_id=self.context["GITHUB_RUN_ID"], run_attempt=self.context["GITHUB_RUN_ATTEMPT"])
        result.update(overrides)
        (self.directory / f"{entry['environment']}--{entry['target']}.json").write_text(json.dumps(result))

    def prepare(self, *targets):
        return MODULE.prepare(list(targets), self.directory, self.context)[0]

    def test_noop_plan_does_not_create_an_approval_job(self):
        target = self.target()
        self.result(target, changes=False)
        self.assertEqual(self.prepare(target), [])

    def test_noop_terraform_does_not_suppress_requested_ansible(self):
        target = self.target(ansible=True)
        self.result(target, changes=False)
        deploy = self.prepare(target)[0]
        self.assertFalse(deploy["terraform"])
        self.assertTrue(deploy["ansible"])

    def test_configuration_only_needs_no_plan_file(self):
        deploy = self.prepare(self.target(terraform=False, ansible=True))[0]
        self.assertEqual(deploy["approval_environment"], "proxmox-dev-auto-apply")

    def test_infrastructure_changes_configure_vm_after_apply(self):
        target = self.target()
        self.result(target)
        deploy = self.prepare(target)[0]
        self.assertTrue(deploy["terraform"])
        self.assertTrue(deploy["ansible"])

    def test_talos_and_images_never_run_ansible(self):
        for target in (self.target(name="talos"), self.target(environment="platform", name="images")):
            self.result(target)
            self.assertFalse(self.prepare(target)[0]["ansible"])

    def test_every_production_deployment_uses_approved_environment(self):
        for terraform, ansible in ((True, False), (False, True), (True, True)):
            with self.subTest(terraform=terraform, ansible=ansible):
                target = self.target(environment="prod", terraform=terraform, ansible=ansible)
                if terraform:
                    self.result(target)
                self.assertEqual(self.prepare(target)[0]["approval_environment"], "proxmox-prod-apply")

    def test_manual_dev_configuration_keeps_existing_approval(self):
        self.context["GITHUB_EVENT_NAME"] = "workflow_dispatch"
        target = self.target(terraform=False, ansible=True)
        self.assertEqual(self.prepare(target)[0]["approval_environment"], "proxmox-dev-apply")

    def test_destroy_requires_manual_main_request_and_never_runs_ansible(self):
        target = self.target(destroy=True, ansible=True)
        self.result(target)
        with self.assertRaises(ValueError):
            self.prepare(target)
        self.context.update(GITHUB_EVENT_NAME="workflow_dispatch", DEPLOYMENT_MODE="destroy")
        deploy = self.prepare(target)[0]
        self.assertFalse(deploy["ansible"])
        self.assertEqual(deploy["approval_environment"], "proxmox-dev-apply")

    def test_missing_plan_result_fails_closed(self):
        with self.assertRaises(FileNotFoundError):
            self.prepare(self.target())

    def test_wrong_commit_run_attempt_target_or_mode_is_rejected(self):
        target = self.target()
        for overrides in (dict(sha="other"), dict(run_id="41"), dict(run_attempt="1"),
                          dict(environment="prod"), dict(target="sandbox"), dict(destroy=True),
                          dict(changes="false")):
            with self.subTest(overrides=overrides):
                self.result(target, **overrides)
                with self.assertRaises(ValueError):
                    self.prepare(target)

    def test_no_cross_target_matrix_output_overwrite(self):
        dev, prod = self.target(), self.target(environment="prod", ansible=True)
        self.result(dev, changes=False)
        self.result(prod, changes=True)
        deployments = self.prepare(dev, prod)
        self.assertEqual([(d["environment"], d["terraform"]) for d in deployments], [("prod", True)])

    def test_invalid_or_duplicate_targets_are_rejected(self):
        for target in (self.target(environment="platform", name="access"),
                       self.target(environment="unknown"),
                       self.target(name="talos", terraform=False, ansible=True),
                       dict(self.target(), directory="terraform/platform/access")):
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.prepare(target)
        target = self.target(terraform=False, ansible=True)
        with self.assertRaises(ValueError):
            self.prepare(target, target)


if __name__ == "__main__":
    unittest.main()
