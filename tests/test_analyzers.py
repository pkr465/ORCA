"""Tests for ORCA static analyzers."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import load_sample_good_c, load_sample_bad_c


class TestStyleAnalyzer(unittest.TestCase):
    def setUp(self):
        from agents.analyzers.style_analyzer import StyleAnalyzer
        self.rules = {
            "style": {
                "indentation": "tabs", "tab_width": 8, "line_length": 80,
                "brace_style": "kr",
                "naming": {"functions": "snake_case"},
                "typedef_policy": "discouraged",
                "max_function_lines": 50,
                "comment_style": "c_only",
                "space_after_keywords": True,
                "keywords_requiring_space": ["if", "for", "while", "switch"],
            }
        }
        self.config = {
            "indent_style": "tabs",
            "indent_size": 8,
            "max_line_length": 80,
            "brace_style": "k_and_r",
            "function_naming": "snake_case",
            "disallow_typedef": True,
            "max_function_length": 50,
            "allow_cpp_comments": False,
            "space_after_keyword": True,
        }
        self.analyzer = StyleAnalyzer(self.rules, self.config)
        self.sample_bad_c = load_sample_bad_c()
        self.sample_good_c = load_sample_good_c()

    def test_detects_spaces_instead_of_tabs(self):
        findings = self.analyzer.analyze("test.c", self.sample_bad_c)
        indent_findings = [f for f in findings if "indent" in f.rule_id.lower() or "space" in f.message.lower()]
        self.assertGreater(len(indent_findings), 0, "Should detect spaces instead of tabs")

    def test_detects_long_lines(self):
        findings = self.analyzer.analyze("test.c", self.sample_bad_c)
        length_findings = [f for f in findings if "STYLE-001" in f.rule_id or "exceeds" in f.message.lower()]
        self.assertGreater(len(length_findings), 0, "Should detect lines exceeding 80 chars")

    def test_detects_camelcase(self):
        findings = self.analyzer.analyze("test.c", self.sample_bad_c)
        naming_findings = [f for f in findings if "naming" in f.rule_id.lower() or "camel" in f.message.lower()]
        self.assertGreater(len(naming_findings), 0, "Should detect CamelCase function names")

    def test_detects_typedef(self):
        findings = self.analyzer.analyze("test.c", self.sample_bad_c)
        typedef_findings = [f for f in findings if "STYLE-004" in f.rule_id or "typedef" in f.message.lower()]
        self.assertGreater(len(typedef_findings), 0, "Should detect typedef usage")

    def test_good_file_minimal_findings(self):
        findings = self.analyzer.analyze("test.c", self.sample_good_c)
        # Good file should have very few or no style findings
        high_findings = [f for f in findings if f.severity in ("high", "critical")]
        self.assertEqual(len(high_findings), 0, f"Good file should have no high/critical style issues, got: {[f.message for f in high_findings]}")

    def test_detects_missing_space_after_keyword(self):
        findings = self.analyzer.analyze("test.c", self.sample_bad_c)
        space_findings = [f for f in findings if "STYLE-007" in f.rule_id or ("no space" in f.message.lower() and "keyword" in f.message.lower())]
        self.assertGreater(len(space_findings), 0, "Should detect missing space after if/for/while")


class TestLicenseAnalyzer(unittest.TestCase):
    def setUp(self):
        from agents.analyzers.license_analyzer import LicenseAnalyzer
        self.rules = {
            "license": {
                "required_spdx": True, "default_license": "GPL-2.0-only",
                "allowed_licenses": ["GPL-2.0-only", "MIT", "BSD-2-Clause"],
                "incompatible_licenses": ["GPL-3.0-only", "AGPL-3.0-only"],
                "require_copyright": True,
                "copyright_pattern": "Copyright",
            }
        }
        self.config = {
            "allowed_licenses": ["GPL-2.0-only", "MIT", "BSD-2-Clause"],
            "incompatible_licenses": ["GPL-3.0-only", "AGPL-3.0-only"],
            "require_copyright_header": True,
            "check_reuse_compliance": False,
            "license_header_format": "spdx_only",
        }
        self.analyzer = LicenseAnalyzer(self.rules, self.config)
        self.sample_bad_c = load_sample_bad_c()
        self.sample_good_c = load_sample_good_c()

    def test_detects_missing_spdx(self):
        findings = self.analyzer.analyze("test.c", self.sample_bad_c)
        spdx_findings = [f for f in findings if "LICENSE-001" in f.rule_id or "spdx" in f.message.lower()]
        self.assertGreater(len(spdx_findings), 0, "Should detect missing SPDX header")

    def test_accepts_valid_spdx(self):
        findings = self.analyzer.analyze("test.c", self.sample_good_c)
        spdx_findings = [f for f in findings if "LICENSE-001" in f.rule_id or ("spdx" in f.message.lower() and "missing" in f.message.lower())]
        self.assertEqual(len(spdx_findings), 0, "Should accept valid SPDX header")

    def test_detects_missing_copyright(self):
        findings = self.analyzer.analyze("test.c", self.sample_bad_c)
        cr_findings = [f for f in findings if "LICENSE-003" in f.rule_id or "copyright" in f.message.lower()]
        self.assertGreater(len(cr_findings), 0, "Should detect missing copyright")


class TestWhitespaceAnalyzer(unittest.TestCase):
    def setUp(self):
        from agents.analyzers.whitespace_analyzer import WhitespaceAnalyzer
        self.config = {
            "check_trailing_whitespace": True,
            "check_space_before_tab": True,
            "check_line_endings": True,
            "check_blank_lines_eof": True,
            "max_blank_lines_eof": 1,
            "check_spaces_inside_parens": True,
        }
        self.analyzer = WhitespaceAnalyzer({}, self.config)

    def test_detects_trailing_whitespace(self):
        code = "int x = 1;   \nint y = 2;\n"
        findings = self.analyzer.analyze("test.c", code)
        trailing = [f for f in findings if "WHITESPACE-001" in f.rule_id or "trailing" in f.message.lower()]
        self.assertGreater(len(trailing), 0)

    def test_detects_mixed_line_endings(self):
        code = "line1\r\nline2\nline3\r\n"
        findings = self.analyzer.analyze("test.c", code)
        mixed = [f for f in findings if "WHITESPACE-003" in f.rule_id or ("mixed" in f.message.lower() and "line" in f.message.lower())]
        self.assertGreater(len(mixed), 0)


class TestMacroAnalyzer(unittest.TestCase):
    def setUp(self):
        from agents.analyzers.macro_analyzer import MacroAnalyzer
        self.config = {
            "require_do_while_wrapper": True,
            "require_parenthesized_macro_args": True,
            "check_macro_naming": True,
            "check_macro_line_continuation": True,
        }
        self.analyzer = MacroAnalyzer({}, self.config)
        self.sample_bad_c = load_sample_bad_c()

    def test_detects_unparenthesized_args(self):
        findings = self.analyzer.analyze("test.c", self.sample_bad_c)
        paren_findings = [f for f in findings if "MACRO-002" in f.rule_id or ("parenthesized" in f.message.lower() and "arg" in f.message.lower())]
        self.assertGreater(len(paren_findings), 0, "Should detect macro args without parens")


class TestIncludeAnalyzer(unittest.TestCase):
    def setUp(self):
        from agents.analyzers.include_analyzer import IncludeAnalyzer
        self.rules = {
            "structure": {
                "include_order": ["own", "system", "project"],
            }
        }
        self.config = {
            "check_include_order": True,
            "max_include_depth": 5,
            "max_includes": 20,
            "check_circular_includes": True,
        }
        self.analyzer = IncludeAnalyzer(self.rules, self.config)
        self.sample_bad_c = load_sample_bad_c()

    def test_detects_wrong_include_order(self):
        findings = self.analyzer.analyze("sample_bad.c", self.sample_bad_c)
        order_findings = [f for f in findings if "INCLUDE-001" in f.rule_id or "out of order" in f.message.lower()]
        self.assertGreater(len(order_findings), 0, "Should detect wrong include order")


class TestStructureAnalyzer(unittest.TestCase):
    def setUp(self):
        from agents.analyzers.structure_analyzer import StructureAnalyzer
        self.rules = {
            "structure": {
                "no_extern_in_c": True,
                "file_naming": "snake_case",
            }
        }
        self.config = {
            "check_file_naming": True,
            "file_naming_style": "snake_case",
            "disallow_extern_in_c_files": True,
            "require_header_for_source": False,
            "check_api_declarations": False,
            "check_directory_organization": False,
        }
        self.analyzer = StructureAnalyzer(self.rules, self.config)
        self.sample_bad_c = load_sample_bad_c()

    def test_detects_extern_in_c(self):
        findings = self.analyzer.analyze("sample_bad.c", self.sample_bad_c)
        extern_findings = [f for f in findings if "STRUCT-002" in f.rule_id or "extern" in f.message.lower()]
        self.assertGreater(len(extern_findings), 0, "Should detect extern in .c file")


class TestCommitAnalyzer(unittest.TestCase):
    def setUp(self):
        from agents.analyzers.commit_analyzer import CommitAnalyzer
        self.rules = {
            "patch": {
                "subject_max_length": 72,
                "require_signed_off_by": True,
                "require_blank_after_subject": True,
                "require_imperative_mood": True,
            }
        }
        self.config = {
            "subject_line_max_length": 72,
            "require_signed_off_by": True,
            "require_blank_line_after_subject": True,
            "require_dco": False,
            "required_trailers": [],
            "prohibited_trailers": [],
        }
        self.analyzer = CommitAnalyzer(self.rules, self.config)

    def test_detects_long_subject(self):
        commit = "Added a really long commit message subject line that definitely exceeds the seventy two character limit\n\nBody text.\n\nSigned-off-by: Test <test@example.com>"
        findings = self.analyzer.analyze("COMMIT_MSG", commit)
        subject_findings = [f for f in findings if "COMMIT-002" in f.rule_id or ("subject" in f.message.lower() and "long" in f.message.lower())]
        self.assertGreater(len(subject_findings), 0, "Should detect long subject line")

    def test_detects_past_tense(self):
        commit = "Added new feature\n\nBody text.\n\nSigned-off-by: Test <test@example.com>"
        findings = self.analyzer.analyze("COMMIT_MSG", commit)
        mood_findings = [f for f in findings if "COMMIT-004" in f.rule_id or ("imperative" in f.message.lower() or "mood" in f.message.lower() or "past tense" in f.message.lower())]
        self.assertGreater(len(mood_findings), 0, "Should detect past tense in subject")


if __name__ == "__main__":
    unittest.main()
