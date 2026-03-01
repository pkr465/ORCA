import re
from typing import List
from agents.analyzers.base_analyzer import BaseAnalyzer, Finding


class MacroAnalyzer(BaseAnalyzer):
    """Analyzes macro definition compliance."""

    def analyze(self, file_path: str, content: str) -> List[Finding]:
        """
        Analyze file for macro violations.

        Args:
            file_path: Path to file being analyzed
            content: Full file content

        Returns:
            List of macro findings
        """
        findings = []
        lines = content.split("\n")

        findings.extend(self._check_do_while_wrapper(file_path, lines))
        findings.extend(self._check_parenthesized_args(file_path, lines))
        findings.extend(self._check_macro_naming(file_path, lines))
        findings.extend(self._check_multiline_safety(file_path, lines))

        return findings

    def _check_do_while_wrapper(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check that multi-line macros use do{}while(0) wrapper."""
        findings = []
        check_do_while = self.config.get("require_do_while_wrapper", True)

        if not check_do_while:
            return findings

        in_macro = False
        macro_start_line = 0
        macro_name = ""

        for line_num, line in enumerate(lines, 1):
            # Detect macro definition (handle indentation)
            if re.search(r'#define\s+\w+\(', line):
                in_macro = True
                macro_start_line = line_num
                match = re.search(r'#define\s+(\w+)', line)
                macro_name = match.group(1) if match else "unknown"

            if in_macro:
                # Check if line ends with backslash (continuation)
                if line.rstrip().endswith("\\"):
                    continue

                # End of macro definition
                in_macro = False

                # Check if this multi-line macro has do{}while(0)
                macro_lines = lines[macro_start_line - 1 : line_num]
                macro_text = "\n".join(macro_lines)

                # Only check if it's multi-line
                if len(macro_lines) > 1:
                    if "do {" not in macro_text or "} while(0)" not in macro_text:
                        finding = self._make_finding(
                            file_path,
                            macro_start_line,
                            1,
                            "MACRO-001",
                            f"Multi-line macro '{macro_name}' lacks do{{}}while(0) wrapper",
                            "Wrap macro body in do { ... } while(0) for safety",
                            self._read_file_context(lines, macro_start_line, context=3),
                        )
                        findings.append(finding)

        return findings

    def _check_parenthesized_args(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check that macro arguments are parenthesized in expansion."""
        findings = []
        check_parens = self.config.get("require_parenthesized_macro_args", True)

        if not check_parens:
            return findings

        for line_num, line in enumerate(lines, 1):
            # Match function-like macro definitions (handle indentation)
            match = re.search(r'#define\s+(\w+)\(([^)]*)\)\s*(.+)', line)
            if not match:
                continue

            macro_name = match.group(1)
            args_str = match.group(2)
            body = match.group(3)

            # Parse arguments
            args = [arg.strip() for arg in args_str.split(",") if arg.strip()]

            # Check each argument is parenthesized in body
            for arg in args:
                # Look for bare argument (not in parens)
                pattern = r'(?<!\()\b' + re.escape(arg) + r'\b(?!\))'
                if re.search(pattern, body):
                    finding = self._make_finding(
                        file_path,
                        line_num,
                        1,
                        "MACRO-002",
                        f"Macro argument '{arg}' not parenthesized in expansion",
                        f"Wrap all uses of '{arg}' in parentheses: ({arg})",
                        self._read_file_context(lines, line_num, context=2),
                        confidence=0.8,
                    )
                    findings.append(finding)

        return findings

    def _check_macro_naming(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check that function-like macros use UPPER_SNAKE_CASE."""
        findings = []
        check_naming = self.config.get("check_macro_naming", True)

        if not check_naming:
            return findings

        for line_num, line in enumerate(lines, 1):
            # Match function-like macro definitions (handle indentation)
            match = re.search(r'#define\s+(\w+)\(', line)
            if not match:
                continue

            macro_name = match.group(1)

            # Check if UPPER_SNAKE_CASE
            if not re.match(r'^[A-Z][A-Z0-9_]*$', macro_name):
                finding = self._make_finding(
                    file_path,
                    line_num,
                    8,
                    "MACRO-003",
                    f"Macro '{macro_name}' not in UPPER_SNAKE_CASE",
                    f"Rename to {macro_name.upper()} following UPPER_SNAKE_CASE convention",
                    self._read_file_context(lines, line_num, context=1),
                )
                findings.append(finding)

        return findings

    def _check_multiline_safety(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check multi-line macro backslash alignment."""
        findings = []
        check_alignment = self.config.get("check_macro_line_continuation", True)

        if not check_alignment:
            return findings

        for line_num, line in enumerate(lines, 1):
            if "#define" not in line and not line.rstrip().endswith("\\"):
                continue

            # Check for backslash-newline
            if line.rstrip().endswith("\\"):
                # Check if there's extra whitespace after backslash
                if re.search(r'\\\s+$', line):
                    finding = self._make_finding(
                        file_path,
                        line_num,
                        len(line.rstrip()),
                        "MACRO-004",
                        "Whitespace after line continuation backslash",
                        "Remove trailing whitespace after backslash",
                        self._read_file_context(lines, line_num, context=1),
                    )
                    findings.append(finding)

        return findings
