"""Integration tests for ORCA compliance pipeline."""
import os
import sys
import unittest
import tempfile
import shutil
import subprocess
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import (
    load_kernel_rules,
    get_default_config,
    create_temp_dir,
    cleanup_temp_dir,
    create_temp_codebase,
)


class TestFullPipeline(unittest.TestCase):
    def setUp(self):
        self.temp_dir = create_temp_dir()
        self.kernel_rules = load_kernel_rules()
        self.default_config = get_default_config()
        self.temp_codebase = create_temp_codebase(self.temp_dir)

    def tearDown(self):
        cleanup_temp_dir(self.temp_dir)

    def test_static_audit_on_fixtures(self):
        """Run full static audit on test fixtures."""
        from agents.compliance_static_agent import ComplianceStaticAgent

        agent = ComplianceStaticAgent(rules=self.kernel_rules, config=self.default_config)
        report = agent.run_audit(
            codebase_path=self.temp_codebase,
            output_dir=self.temp_dir,
            domains=["style", "license", "structure"],
        )

        # Should find violations in bad files
        self.assertGreater(len(report.findings), 0, "Should find violations in sample_bad.c")

        # Should have domain scores
        self.assertGreater(len(report.domain_scores), 0, "Should compute domain scores")

        # Should have a grade
        self.assertIn(report.overall_grade, ("A", "B", "C", "D", "F"), "Should compute grade")

        # Bad file should have more findings than good file
        bad_findings = [f for f in report.findings if "bad" in f.file_path]
        good_findings = [f for f in report.findings if "good" in f.file_path]
        self.assertGreater(len(bad_findings), len(good_findings), "Bad file should have more violations")

    def test_cli_help(self):
        """Verify CLI loads without errors."""
        result = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py"), "--help"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, f"CLI help should work: {result.stderr}")
        self.assertIn("ORCA", result.stdout, "Help should mention ORCA")

    def test_json_report_generation(self):
        """Test JSON report output."""
        from agents.compliance_static_agent import ComplianceStaticAgent

        agent = ComplianceStaticAgent(rules=self.kernel_rules, config=self.default_config)
        report = agent.run_audit(self.temp_codebase, self.temp_dir, ["style"])

        from agents.parsers.report_parser import JSONReportGenerator
        json_gen = JSONReportGenerator()
        json_path = os.path.join(self.temp_dir, "report.json")
        json_gen.generate(report, json_path)

        self.assertTrue(os.path.exists(json_path), "JSON report should be created")

        with open(json_path) as f:
            data = json.load(f)
        self.assertIn("overall_grade", data, "JSON should contain grade")
        self.assertIn("findings", data, "JSON should contain findings")


if __name__ == "__main__":
    unittest.main()
