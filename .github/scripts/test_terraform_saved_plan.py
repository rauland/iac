"""Offline tests for saved plan transfer through S3, with a fake aws CLI."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("terraform-saved-plan.sh").resolve()

# Stores objects under $FAKE_S3/<bucket>/<key> and honours --if-none-match '*'.
FAKE_AWS = r"""#!/usr/bin/env bash
set -euo pipefail
[ "$1 $2" = "s3api put-object" ] || [ "$1 $2" = "s3api get-object" ] || exit 64
operation=$2; shift 2
while [ $# -gt 0 ]; do
  case "$1" in
    --bucket) bucket=$2; shift 2 ;;
    --key) key=$2; shift 2 ;;
    --body) body=$2; shift 2 ;;
    --if-none-match) none_match=$2; shift 2 ;;
    *) outfile=$1; shift ;;
  esac
done
object="$FAKE_S3/$bucket/$key"
if [ "$operation" = put-object ]; then
  [ "${none_match:-}" = '*' ] || exit 65
  if [ -e "$object" ]; then echo "PreconditionFailed" >&2; exit 254; fi
  mkdir -p "$(dirname "$object")"; cp "$body" "$object"
else
  [ -e "$object" ] || { echo "NoSuchKey" >&2; exit 254; }
  cp "$object" "$outfile"
fi
"""


class SavedPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.bin, self.s3 = base / "bin", base / "s3"
        self.source, self.destination = base / "source", base / "destination"
        for directory in (self.bin, self.s3, self.source, self.destination):
            directory.mkdir()
        (self.bin / "aws").write_text(FAKE_AWS)
        (self.bin / "aws").chmod(0o755)
        (self.source / "tfplan").write_bytes(b"secret plan contents\x00\xff")
        (self.source / ".terraform.lock.hcl").write_text("exact provider selections\n")
        (self.source / ".tf-plan.json").write_text('{"version":2}\n')
        self.result = base / "result.json"
        self.result.write_text('{"changes":true}\n')
        self.object = self.s3 / "state" / "plans" / "dev" / "talos" / "42-2.tar"

    def run_script(self, mode, root, *extra, **overrides):
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", FAKE_S3=str(self.s3),
                   TF_STATE_BUCKET="state", GITHUB_RUN_ID="42", GITHUB_RUN_ATTEMPT="2")
        env.update(overrides)
        return subprocess.run(["bash", str(SCRIPT), mode, str(root), "dev", "talos", *extra],
                              env=env, capture_output=True, text=True)

    def upload(self):
        result = self.run_script("upload", self.source, str(self.result))
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(self.result.read_text())["archive_sha256"]

    def test_round_trip_restores_plan_and_lock(self):
        digest = self.upload()
        self.assertEqual(digest, hashlib.sha256(self.object.read_bytes()).hexdigest())
        self.assertTrue(json.loads(self.result.read_text())["changes"])
        result = self.run_script("download", self.destination, digest)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("tfplan", ".terraform.lock.hcl", ".tf-plan.json"):
            self.assertEqual((self.source / name).read_bytes(),
                             (self.destination / name).read_bytes())

    def test_upload_never_replaces_an_existing_plan(self):
        self.upload()
        result = self.run_script("upload", self.source, str(self.result))
        self.assertNotEqual(result.returncode, 0)

    def test_replaced_object_fails_before_extracting(self):
        digest = self.upload()
        data = bytearray(self.object.read_bytes())
        data[-1] ^= 1
        self.object.write_bytes(data)
        result = self.run_script("download", self.destination, digest)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not the archive this run uploaded", result.stderr)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_download_requires_the_run_digest(self):
        self.upload()
        for digest in ("", "abc", "A" * 64):
            with self.subTest(digest=digest):
                result = self.run_script("download", self.destination, digest)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(list(self.destination.iterdir()), [])

    def test_other_run_attempt_reads_its_own_key(self):
        digest = self.upload()
        result = self.run_script("download", self.destination, digest, GITHUB_RUN_ATTEMPT="3")
        self.assertNotEqual(result.returncode, 0)

    def test_missing_bucket_fails(self):
        result = self.run_script("upload", self.source, str(self.result), TF_STATE_BUCKET="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("TF_STATE_BUCKET", result.stderr)

    def test_missing_lock_or_manifest_fails(self):
        for name in (".terraform.lock.hcl", ".tf-plan.json"):
            with self.subTest(name=name):
                (self.source / name).rename(self.source / f"{name}.moved")
                result = self.run_script("upload", self.source, str(self.result))
                self.assertNotEqual(result.returncode, 0)
                (self.source / f"{name}.moved").rename(self.source / name)
        self.assertFalse(self.object.exists())


if __name__ == "__main__":
    unittest.main()
