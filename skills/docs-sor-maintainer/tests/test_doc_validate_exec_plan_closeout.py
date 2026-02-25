#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import doc_validate  # noqa: E402


class ExecPlanCloseoutValidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "docs/exec-plans/active").mkdir(parents=True, exist_ok=True)
        (self.root / "docs/exec-plans/completed").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_completed_status_requires_closeout_link(self) -> None:
        active = self.root / "docs/exec-plans/active/phase-x.md"
        active.write_text(
            "\n".join(
                [
                    "# Phase X",
                    "<!-- exec-plan-status: completed -->",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        errors, warnings, metrics = doc_validate.check_exec_plan_closeout(self.root)
        self.assertEqual(warnings, [])
        self.assertTrue(any("missing link marker" in message for message in errors))
        self.assertEqual(metrics.get("completed_declared_files"), 1)
        self.assertEqual(metrics.get("missing_closeout_link_files"), 1)

    def test_completed_status_requires_existing_closeout_target(self) -> None:
        active = self.root / "docs/exec-plans/active/phase-y.md"
        active.write_text(
            "\n".join(
                [
                    "# Phase Y",
                    "<!-- exec-plan-status: completed -->",
                    "<!-- exec-plan-closeout: docs/exec-plans/completed/phase-y-closeout.md -->",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        errors, warnings, metrics = doc_validate.check_exec_plan_closeout(self.root)
        self.assertEqual(warnings, [])
        self.assertTrue(any("target missing" in message for message in errors))
        self.assertEqual(metrics.get("missing_closeout_target_files"), 1)

    def test_completed_status_passes_with_valid_closeout(self) -> None:
        closeout_rel = "docs/exec-plans/completed/phase-z-closeout.md"
        (self.root / closeout_rel).write_text("# closeout\n", encoding="utf-8")
        active = self.root / "docs/exec-plans/active/phase-z.md"
        active.write_text(
            "\n".join(
                [
                    "# Phase Z",
                    "<!-- exec-plan-status: completed -->",
                    f"<!-- exec-plan-closeout: {closeout_rel} -->",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        errors, warnings, metrics = doc_validate.check_exec_plan_closeout(self.root)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(metrics.get("completed_declared_files"), 1)
        self.assertEqual(metrics.get("missing_closeout_link_files"), 0)
        self.assertEqual(metrics.get("missing_closeout_target_files"), 0)


if __name__ == "__main__":
    unittest.main()
