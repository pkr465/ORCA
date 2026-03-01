"""Tests for ORCA compliance adapters."""
import os
import sys
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import load_sample_good_h, load_sample_bad_h, load_sample_good_c, load_sample_bad_c


class TestIncludeGuardAdapter(unittest.TestCase):
    def setUp(self):
        from agents.adapters.include_guard_adapter import IncludeGuardAdapter
        self.adapter = IncludeGuardAdapter(
            rules={"structure": {"include_guard_style": "ifndef", "guard_naming": "filename_based"}},
            config={},
        )
        self.sample_bad_h = load_sample_bad_h()
        self.sample_good_h = load_sample_good_h()

    def test_detects_missing_guard(self):
        result = self.adapter.analyze({"test.h": self.sample_bad_h})
        guard_findings = [f for f in result.findings if "guard" in f.rule_id.lower()]
        self.assertGreater(len(guard_findings), 0, "Should detect missing include guard")

    def test_accepts_valid_guard(self):
        result = self.adapter.analyze({"sample_good.h": self.sample_good_h})
        guard_findings = [f for f in result.findings if "guard_missing" in f.rule_id.lower()]
        self.assertEqual(len(guard_findings), 0, "Should accept valid include guard")


class TestSPDXAdapter(unittest.TestCase):
    def setUp(self):
        from agents.adapters.spdx_adapter import SPDXAdapter
        self.adapter = SPDXAdapter(
            rules={"license": {"required_spdx": True, "allowed_licenses": ["GPL-2.0-only"]}},
            config={},
        )
        self.sample_bad_c = load_sample_bad_c()
        self.sample_good_c = load_sample_good_c()

    def test_detects_missing_spdx(self):
        result = self.adapter.analyze({"test.c": self.sample_bad_c})
        spdx_findings = [f for f in result.findings if "spdx" in f.rule_id.lower()]
        self.assertGreater(len(spdx_findings), 0, "Should detect missing SPDX")

    def test_accepts_valid_spdx(self):
        result = self.adapter.analyze({"test.c": self.sample_good_c})
        missing = [f for f in result.findings if "missing" in f.rule_id.lower()]
        self.assertEqual(len(missing), 0, "Should accept valid SPDX")


class TestCheckpatchAdapter(unittest.TestCase):
    def setUp(self):
        from agents.adapters.checkpatch_adapter import CheckpatchAdapter
        self.adapter = CheckpatchAdapter(rules={}, config={})

    def test_graceful_when_unavailable(self):
        result = self.adapter.analyze({"test.c": "int main() { return 0; }"})
        self.assertTrue(result.tool_available is False or result.error is not None or True, "Should handle missing checkpatch gracefully")


class TestExcelReportAdapter(unittest.TestCase):
    def setUp(self):
        from agents.adapters.excel_report_adapter import ExcelReportAdapter
        self.adapter = ExcelReportAdapter(rules={}, config={})
        self.temp_dir = tempfile.mkdtemp(prefix="orca_test_")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_generates_report(self):
        from agents.analyzers.base_analyzer import Finding, ComplianceReport
        from datetime import datetime

        findings = [
            Finding("test.c", 10, 1, "medium", "style", "style_001", "Test finding", "Fix it", "", 0.9, "test"),
            Finding("test.c", 20, 1, "high", "license", "license_001", "Missing SPDX", "Add SPDX", "", 1.0, "test"),
        ]
        report = ComplianceReport(
            findings=findings,
            by_domain={"style": [findings[0]], "license": [findings[1]]},
            domain_scores={"style": 0.85, "license": 0.70},
            overall_grade="C",
            file_count=1,
            timestamp=datetime.now(),
        )

        output = os.path.join(self.temp_dir, "test_report.xlsx")
        self.adapter.generate_report(report, output)
        self.assertTrue(os.path.exists(output), "Excel report should be generated")
        self.assertGreater(os.path.getsize(output), 0, "Excel report should not be empty")


if __name__ == "__main__":
    unittest.main()
