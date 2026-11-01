"""Offline event/diff tests for infrastructure routing."""

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
        for root in ("dev/talos", "dev/flux", "prod/talos"):
            self.write(f"terraform/workloads/{root}/main.tf", "# root\n")
        for root in ("access", "state-access", "backup-storage", "cluster-oidc"):
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
                   DEPLOYMENT_SCOPE="single", SELECTED_ENV="dev", SELECTED_TARGET="talos")
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
        return {(t["environment"], t["target"]) for t in targets}

    def test_infrastructure_change_only_selects_its_root(self):
        self.assertEqual(self.change("terraform/workloads/dev/talos/main.tf"), {("dev", "talos")})

    def test_plan_helpers_select_every_root(self):
        self.assertEqual(len(self.change(".github/scripts/plan_manifest.py",
                                         ".github/scripts/terraform-apply.py")), 3)

    def test_shared_terraform_module_selects_all_enabled_roots(self):
        self.assertEqual(len(self.change("terraform/modules/talos-cluster/main.tf")), 3)

    def test_docs_tests_workflows_and_manifests_do_not_deploy(self):
        # Flux pulls Kubernetes manifests from Git itself; CI never applies them.
        self.assertEqual(self.change(
            "README.md", "terraform/modules/talos-cluster/tests/cluster.tftest.hcl",
            ".github/workflows/terraform.yml", ".github/scripts/test_deployment_targets.py",
            "kubernetes/clusters/dev/kustomization.yaml"), set())

    def test_push_includes_every_commit(self):
        self.write("terraform/workloads/dev/talos/main.tf", "# first\n")
        self.commit()
        self.assertEqual(self.change("terraform/workloads/dev/flux/main.tf"),
                         {("dev", "talos"), ("dev", "flux")})

    def test_pull_request_uses_merge_base(self):
        self.write("terraform/workloads/dev/talos/main.tf", "# feature\n")
        head = self.commit()
        self.git("checkout", "-q", self.base)
        self.write("terraform/workloads/dev/flux/main.tf", "# base\n")
        base = self.commit()
        result, targets = self.discover("pull_request", BASE_SHA=base, HEAD_SHA=head)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([t["target"] for t in targets], ["talos"])

    def test_first_push_includes_enabled_roots(self):
        self.assertEqual(len(self.discover(BASE_SHA="0" * 40)[1]), 3)

    def test_disabled_roots_are_excluded(self):
        self.write("terraform/workloads/prod/talos/.disabled", "disabled\n")
        self.assertEqual(self.change("terraform/modules/talos-cluster/main.tf"),
                         {("dev", "talos"), ("dev", "flux")})

    def test_reenabled_root_is_planned(self):
        self.write("terraform/workloads/prod/talos/.disabled", "disabled\n")
        self.base = self.commit()
        (self.repo / "terraform/workloads/prod/talos/.disabled").unlink()
        self.commit()
        result, targets = self.discover()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([(t["environment"], t["target"]) for t in targets], [("prod", "talos")])

    def test_unknown_and_platform_roots_never_deploy(self):
        self.assertEqual(self.change("terraform/workloads/dev/other/main.tf",
                                     "terraform/platform/access/main.tf",
                                     "terraform/platform/state-access/main.tf",
                                     "terraform/platform/backup-storage/main.tf",
                                     "terraform/platform/cluster-oidc/main.tf"), set())

    def test_manual_modes(self):
        for mode, destroy in (("auto", False), ("destroy", True)):
            with self.subTest(mode=mode):
                result, targets = self.discover("workflow_dispatch", DEPLOYMENT_MODE=mode)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual([(t["target"], t["terraform"], t["destroy"]) for t in targets],
                                 [("talos", True, destroy)])

    def test_manual_all_scope_selects_the_environment(self):
        result, targets = self.discover("workflow_dispatch", DEPLOYMENT_SCOPE="all")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([t["target"] for t in targets], ["flux", "talos"])

    def test_invalid_manual_requests_cannot_deploy(self):
        invalid = [dict(GITHUB_REF="refs/heads/feature"), dict(DEPLOYMENT_MODE="invalid"),
                   dict(DEPLOYMENT_MODE="configuration"), dict(DEPLOYMENT_SCOPE="invalid"),
                   dict(SELECTED_ENV="unknown"), dict(SELECTED_ENV="platform", SELECTED_TARGET="access"),
                   dict(SELECTED_TARGET="sandbox"), dict(SELECTED_ENV="prod", SELECTED_TARGET="flux")]
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                result, _ = self.discover("workflow_dispatch", **overrides)
                self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
