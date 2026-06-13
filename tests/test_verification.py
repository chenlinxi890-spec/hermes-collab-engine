"""Tests for release verification reporting."""
from __future__ import annotations

import json
import os
import subprocess
import unittest

from src.hermes_collab_engine.verification import verify_v45_capabilities


class VerificationReportTests(unittest.TestCase):
    def test_verify_v45_capabilities_reports_passed_checks_and_skips(self):
        report = verify_v45_capabilities()
        self.assertEqual(report.status, "ok")
        names = {check.name for check in report.checks}
        self.assertIn("skill registry builtins", names)
        self.assertIn("tool profile builtins", names)
        self.assertIn("dashboard API payloads", names)
        self.assertTrue(all(check.status == "passed" for check in report.checks))
        self.assertTrue(report.skipped)

    def test_verify_v45_cli_outputs_json_report(self):
        data = self._run_verification_cli("verify-v45")
        self.assertEqual(data["status"], "ok")
        self.assertGreaterEqual(len(data["checks"]), 5)
        self.assertTrue(data["skipped"])

    def test_verify_release_cli_alias_outputs_json_report(self):
        data = self._run_verification_cli("verify-release")
        self.assertEqual(data["status"], "ok")
        self.assertGreaterEqual(len(data["checks"]), 5)
        self.assertTrue(data["skipped"])

    def _run_verification_cli(self, command):
        proc = subprocess.run(
            ["python3", "-m", "hermes_collab_engine.cli", command, "--json"],
            capture_output=True,
            text=True,
            cwd="/root/hermes-collab-engine/src",
            env={**os.environ, "PYTHONPATH": "/root/hermes-collab-engine/src"},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)


if __name__ == "__main__":
    unittest.main()
