import re
from typing import List
from agents.analyzers.base_analyzer import BaseAnalyzer, Finding


class StyleAnalyzer(BaseAnalyzer):
    """Analyzes code style compliance."""

    def analyze(self, file_path: str, content: str) -> List[Finding]:
        """
        Analyze file for style violations.

        Args:
            file_path: Path to file being analyzed
            content: Full file content

        Returns:
            List of style findings
        """
        findings = []
        lines = content.split("\n")

        # Run all style checks
        findings.extend(self._check_indentation(file_path, lines))
        findings.extend(self._check_line_length(file_path, lines))
        findings.extend(self._check_braces(file_path, lines))
        findings.extend(self._check_naming(file_path, lines))
        findings.extend(self._check_typedef(file_path, lines))
        findings.extend(self._check_function_length(file_path, lines))
        findings.extend(self._check_comment_style(file_path, lines))
        findings.extend(self._check_space_after_keyword(file_path, lines))

        return findings

    def _check_indentation(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check indentation consistency (tabs vs spaces)."""
        findings = []
        indent_style = self.config.get("indent_style", "spaces")
        indent_size = self.config.get("indent_size", 4)
        allow_tabs = indent_style == "tabs"

        for line_num, line in enumerate(lines, 1):
            if not line or line[0] not in {" ", "\t"}:
                continue

            # Check for tabs
            if "\t" in line and not allow_tabs:
                finding = self._make_finding(
                    file_path,
                    line_num,
                    1,
                    "INDENT-001",
                    "File uses tabs for indentation",
                    f"Replace tabs with {indent_size} spaces",
                    self._read_file_context(lines, line_num, context=1),
                )
                findings.append(finding)

            # Check for mixed indentation
            if line.startswith(" \t") or line.startswith("\t "):
                finding = self._make_finding(
                    file_path,
                    line_num,
                    1,
                    "INDENT-002",
                    "Mixed tabs and spaces on same line",
                    "Use consistent indentation style",
                    self._read_file_context(lines, line_num, context=1),
                )
                findings.append(finding)

        return findings

    def _check_line_length(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check for lines exceeding maximum length."""
        findings = []
        max_length = self.config.get("max_line_length", 100)

        for line_num, line in enumerate(lines, 1):
            # Remove newline for length check
            line_content = line.rstrip("\r\n")
            if len(line_content) > max_length:
                finding = self._make_finding(
                    file_path,
                    line_num,
                    max_length + 1,
                    "STYLE-001",
                    f"Line exceeds {max_length} characters ({len(line_content)} chars)",
                    f"Refactor to fit within {max_length} character limit",
                    self._read_file_context(lines, line_num, context=1),
                )
                findings.append(finding)

        return findings

    def _check_braces(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check for K&R brace style (opening brace alone on line)."""
        findings = []
        brace_style = self.config.get("brace_style", "allman")

        if brace_style != "k_and_r":
            return findings

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped == "{":
                # Check if previous line is a control statement
                if line_num > 1:
                    prev_line = lines[line_num - 2].strip()
                    if any(
                        prev_line.startswith(kw)
                        for kw in ["if", "else", "while", "for", "switch", "do"]
                    ):
                        finding = self._make_finding(
                            file_path,
                            line_num,
                            1,
                            "STYLE-002",
                            "Opening brace on separate line (not K&R style)",
                            "Move opening brace to same line as control statement",
                            self._read_file_context(lines, line_num, context=2),
                        )
                        findings.append(finding)

        return findings

    def _check_naming(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check function naming conventions."""
        findings = []
        func_naming = self.config.get("function_naming", "snake_case")

        # Regex to find function declarations
        func_pattern = r'^\s*(?:static\s+)?(?:inline\s+)?(?:const\s+)?(?:unsigned\s+)?(?:struct\s+)?(?:\w+[\s\*]+)+(\w+)\s*\('

        for line_num, line in enumerate(lines, 1):
            match = re.match(func_pattern, line)
            if match:
                func_name = match.group(1)

                # Check snake_case
                if func_naming == "snake_case":
                    if not self._is_snake_case(func_name):
                        finding = self._make_finding(
                            file_path,
                            line_num,
                            match.start(1) + 1,
                            "STYLE-003",
                            f"Function '{func_name}' not in snake_case",
                            f"Rename to snake_case (e.g., {self._to_snake_case(func_name)})",
                            self._read_file_context(lines, line_num, context=1),
                        )
                        findings.append(finding)

                # Check camelCase
                elif func_naming == "camelCase":
                    if not self._is_camel_case(func_name):
                        finding = self._make_finding(
                            file_path,
                            line_num,
                            match.start(1) + 1,
                            "STYLE-003",
                            f"Function '{func_name}' not in camelCase",
                            f"Rename to camelCase (e.g., {self._to_camel_case(func_name)})",
                            self._read_file_context(lines, line_num, context=1),
                        )
                        findings.append(finding)

        return findings

    def _is_snake_case(self, name: str) -> bool:
        """Check if name is snake_case."""
        return re.match(r'^[a-z][a-z0-9_]*$', name) is not None

    def _is_camel_case(self, name: str) -> bool:
        """Check if name is camelCase."""
        return re.match(r'^[a-z][a-zA-Z0-9]*$', name) is not None

    def _to_snake_case(self, name: str) -> str:
        """Convert to snake_case."""
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    def _to_camel_case(self, name: str) -> str:
        """Convert to camelCase."""
        parts = name.split('_')
        return parts[0] + ''.join(p.capitalize() for p in parts[1:])

    def _check_typedef(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check typedef usage if discouraged by rules."""
        findings = []
        disallow_typedef = self.config.get("disallow_typedef", False)

        if not disallow_typedef:
            return findings

        for line_num, line in enumerate(lines, 1):
            if re.search(r'\btypedef\b', line):
                finding = self._make_finding(
                    file_path,
                    line_num,
                    line.find("typedef") + 1,
                    "STYLE-004",
                    "typedef usage discouraged",
                    "Use struct/union/enum directly instead of typedef",
                    self._read_file_context(lines, line_num, context=1),
                )
                findings.append(finding)

        return findings

    def _check_function_length(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check for overly long functions."""
        findings = []
        max_function_lines = self.config.get("max_function_length", 50)

        in_function = False
        func_start_line = 0
        brace_depth = 0
        func_name = ""

        for line_num, line in enumerate(lines, 1):
            # Detect function start
            func_match = re.match(r'^\s*\w+[\s\*]+(\w+)\s*\([^)]*\)\s*$', line)
            if func_match and line_num < len(lines) and lines[line_num].strip() == "{":
                in_function = True
                func_start_line = line_num
                func_name = func_match.group(1)
                brace_depth = 0

            if in_function:
                brace_depth += line.count("{") - line.count("}")

                if brace_depth == 0 and "{" in line:
                    func_length = line_num - func_start_line
                    if func_length > max_function_lines:
                        finding = self._make_finding(
                            file_path,
                            func_start_line,
                            1,
                            "STYLE-005",
                            f"Function '{func_name}' is {func_length} lines (max {max_function_lines})",
                            "Refactor function to reduce complexity and length",
                            self._read_file_context(lines, func_start_line, context=2),
                        )
                        findings.append(finding)
                    in_function = False

        return findings

    def _check_comment_style(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check comment style (// vs /* */ for C vs C++)."""
        findings = []
        allow_cpp_comments = self.config.get("allow_cpp_comments", True)

        if allow_cpp_comments:
            return findings

        for line_num, line in enumerate(lines, 1):
            # Detect // comments not in strings
            if "//" in line:
                # Simple check: not in quotes
                if not self._is_in_string(line, line.find("//")):
                    finding = self._make_finding(
                        file_path,
                        line_num,
                        line.find("//") + 1,
                        "STYLE-006",
                        "C++ style comment (//) in C code",
                        "Use C style comments (/* */)",
                        self._read_file_context(lines, line_num, context=1),
                    )
                    findings.append(finding)

        return findings

    def _is_in_string(self, line: str, pos: int) -> bool:
        """Check if position is inside a string."""
        in_string = False
        escape_next = False
        quote_char = None

        for i, char in enumerate(line):
            if i >= pos:
                return in_string
            if escape_next:
                escape_next = False
                continue
            if char == "\\":
                escape_next = True
                continue
            if char in {'"', "'"} and not in_string:
                in_string = True
                quote_char = char
            elif char == quote_char and in_string:
                in_string = False
                quote_char = None

        return in_string

    def _check_space_after_keyword(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check for space after control flow keywords."""
        findings = []
        check_space = self.config.get("space_after_keyword", True)

        if not check_space:
            return findings

        keywords = ["if", "while", "for", "switch", "catch"]
        pattern = r'\b(' + "|".join(keywords) + r')\('

        for line_num, line in enumerate(lines, 1):
            if re.search(pattern, line):
                # Find the problematic keyword
                match = re.search(pattern, line)
                if match:
                    finding = self._make_finding(
                        file_path,
                        line_num,
                        match.start() + 1,
                        "STYLE-007",
                        f"No space after '{match.group(1)}' keyword",
                        f"Use '{match.group(1)} (' instead",
                        self._read_file_context(lines, line_num, context=1),
                    )
                    findings.append(finding)

        return findings
