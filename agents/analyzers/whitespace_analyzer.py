import re
from typing import List
from agents.analyzers.base_analyzer import BaseAnalyzer, Finding


class WhitespaceAnalyzer(BaseAnalyzer):
    """Analyzes whitespace and formatting compliance."""

    def analyze(self, file_path: str, content: str) -> List[Finding]:
        """
        Analyze file for whitespace violations.

        Args:
            file_path: Path to file being analyzed
            content: Full file content

        Returns:
            List of whitespace findings
        """
        findings = []
        lines = content.split("\n")

        findings.extend(self._check_trailing_whitespace(file_path, lines))
        findings.extend(self._check_space_before_tab(file_path, lines))
        findings.extend(self._check_mixed_line_endings(file_path, content))
        findings.extend(self._check_blank_lines_at_eof(file_path, lines))
        findings.extend(self._check_spaces_inside_parens(file_path, lines))

        return findings

    def _check_trailing_whitespace(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check for trailing whitespace at end of lines."""
        findings = []
        check_trailing = self.config.get("check_trailing_whitespace", True)

        if not check_trailing:
            return findings

        for line_num, line in enumerate(lines, 1):
            # Check if line has trailing whitespace
            if line != line.rstrip():
                finding = self._make_finding(
                    file_path,
                    line_num,
                    len(line.rstrip()) + 1,
                    "WHITESPACE-001",
                    "Trailing whitespace at end of line",
                    "Remove trailing whitespace",
                    self._read_file_context(lines, line_num, context=1),
                )
                findings.append(finding)

        return findings

    def _check_space_before_tab(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check for space before tab character."""
        findings = []
        check_space_before_tab = self.config.get("check_space_before_tab", True)

        if not check_space_before_tab:
            return findings

        pattern = r' \t'

        for line_num, line in enumerate(lines, 1):
            match = re.search(pattern, line)
            if match:
                finding = self._make_finding(
                    file_path,
                    line_num,
                    match.start() + 1,
                    "WHITESPACE-002",
                    "Space before tab character",
                    "Use consistent indentation (no space before tab)",
                    self._read_file_context(lines, line_num, context=1),
                )
                findings.append(finding)

        return findings

    def _check_mixed_line_endings(self, file_path: str, content: str) -> List[Finding]:
        """Check for mixed line endings (CRLF and LF)."""
        findings = []
        check_line_endings = self.config.get("check_line_endings", True)

        if not check_line_endings:
            return findings

        has_crlf = "\r\n" in content
        has_lf = "\n" in content.replace("\r\n", "")

        if has_crlf and has_lf:
            finding = self._make_finding(
                file_path,
                1,
                1,
                "WHITESPACE-003",
                "Mixed line endings (CRLF and LF)",
                "Use consistent line endings (Unix: LF or Windows: CRLF)",
                content[:200],
            )
            findings.append(finding)

        return findings

    def _check_blank_lines_at_eof(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check for multiple blank lines at end of file."""
        findings = []
        check_eof_blank = self.config.get("check_blank_lines_eof", True)
        max_blank_lines_eof = self.config.get("max_blank_lines_eof", 1)

        if not check_eof_blank or not lines:
            return findings

        # Count trailing blank lines
        trailing_blanks = 0
        for line in reversed(lines):
            if not line.strip():
                trailing_blanks += 1
            else:
                break

        if trailing_blanks > max_blank_lines_eof:
            line_num = len(lines) - trailing_blanks + max_blank_lines_eof + 1
            finding = self._make_finding(
                file_path,
                line_num,
                1,
                "WHITESPACE-004",
                f"Too many blank lines at EOF ({trailing_blanks}, max {max_blank_lines_eof})",
                f"Remove excess blank lines at end of file",
                self._read_file_context(lines, line_num, context=3),
            )
            findings.append(finding)

        return findings

    def _check_spaces_inside_parens(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check for spaces inside parentheses."""
        findings = []
        check_paren_spaces = self.config.get("check_spaces_inside_parens", True)

        if not check_paren_spaces:
            return findings

        # Pattern: ( followed by space or space followed by )
        open_paren_pattern = r'\(\s'
        close_paren_pattern = r'\s\)'

        for line_num, line in enumerate(lines, 1):
            # Skip strings
            if self._is_in_string_context(line):
                continue

            # Check for ( followed by space
            match = re.search(open_paren_pattern, line)
            if match:
                finding = self._make_finding(
                    file_path,
                    line_num,
                    match.start() + 1,
                    "WHITESPACE-005",
                    "Space after opening parenthesis",
                    "Remove space after opening parenthesis: '(' instead of '( '",
                    self._read_file_context(lines, line_num, context=1),
                )
                findings.append(finding)

            # Check for space followed by )
            match = re.search(close_paren_pattern, line)
            if match:
                finding = self._make_finding(
                    file_path,
                    line_num,
                    match.start() + 1,
                    "WHITESPACE-006",
                    "Space before closing parenthesis",
                    "Remove space before closing parenthesis: ')' instead of ' )'",
                    self._read_file_context(lines, line_num, context=1),
                )
                findings.append(finding)

        return findings

    def _is_in_string_context(self, line: str) -> bool:
        """Simple check if entire line is in a string (crude but effective)."""
        # If line has printf or contains quotes, assume it might have string content
        return '"' in line or "'" in line
