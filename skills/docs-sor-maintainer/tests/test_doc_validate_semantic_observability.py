#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import doc_validate  # noqa: E402
import language_profiles as lp  # noqa: E402


class SemanticObservabilityValidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _policy(self, *, fail_on_large_unattempted: bool) -> dict[str, object]:
        policy = lp.build_default_policy(primary_language="zh-CN", profile="zh-CN")
        semantic = policy["semantic_generation"]
        semantic["enabled"] = True
        semantic["mode"] = "hybrid"
        semantic["prefer_agent_semantic_first"] = True
        semantic["require_semantic_attempt"] = True
        semantic["observability"] = {
            "enabled": True,
            "large_unattempted_ratio": 0.5,
            "large_unattempted_count": 2,
            "fail_on_large_unattempted": fail_on_large_unattempted,
        }
        return policy

    def _write_apply_report(self, summary: dict[str, object]) -> Path:
        path = self.root / "docs/.doc-apply-report.json"
        path.write_text(
            json.dumps(
                {
                    "summary": summary,
                    "results": [],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def test_semantic_observability_fails_on_large_unattempted_gap(self) -> None:
        apply_path = self._write_apply_report(
            {
                "semantic_action_count": 4,
                "semantic_attempt_count": 1,
                "semantic_success_count": 1,
                "fallback_count": 0,
                "fallback_reason_breakdown": {},
                "semantic_exempt_count": 0,
                "semantic_unattempted_count": 3,
                "semantic_unattempted_without_exemption": 3,
                "semantic_hit_rate": 1.0,
            }
        )
        errors, warnings, report = doc_validate.check_semantic_observability(
            self.root,
            self._policy(fail_on_large_unattempted=True),
            apply_path,
        )
        self.assertEqual(warnings, [])
        self.assertTrue(any("semantic-first actions missing runtime attempts" in msg for msg in errors))
        self.assertEqual((report.get("gate") or {}).get("status"), "failed")
        self.assertEqual(
            (report.get("metrics") or {}).get("semantic_unattempted_without_exemption"),
            3,
        )

    def test_semantic_observability_warns_when_report_missing_or_fail_disabled(self) -> None:
        missing_report = self.root / "docs/.doc-apply-report.json"
        errors, warnings, report = doc_validate.check_semantic_observability(
            self.root,
            self._policy(fail_on_large_unattempted=True),
            missing_report,
        )
        self.assertEqual(errors, [])
        self.assertTrue(any("apply report missing" in msg for msg in warnings))
        self.assertEqual((report.get("gate") or {}).get("status"), "warn")

        apply_path = self._write_apply_report(
            {
                "semantic_action_count": 4,
                "semantic_attempt_count": 1,
                "semantic_success_count": 1,
                "fallback_count": 1,
                "fallback_reason_breakdown": {"runtime_unavailable": 1},
                "semantic_exempt_count": 0,
                "semantic_unattempted_count": 3,
                "semantic_unattempted_without_exemption": 3,
                "semantic_hit_rate": 1.0,
            }
        )
        errors2, warnings2, report2 = doc_validate.check_semantic_observability(
            self.root,
            self._policy(fail_on_large_unattempted=False),
            apply_path,
        )
        self.assertEqual(errors2, [])
        self.assertTrue(any("semantic-first actions missing runtime attempts" in msg for msg in warnings2))
        self.assertEqual((report2.get("gate") or {}).get("status"), "warn")
        self.assertEqual(
            (report2.get("metrics") or {}).get("fallback_reason_breakdown"),
            {"runtime_unavailable": 1},
        )


if __name__ == "__main__":
    unittest.main()
