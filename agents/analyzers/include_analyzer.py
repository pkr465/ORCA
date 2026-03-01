import re
from typing import List, Dict, Set, Tuple
from agents.analyzers.base_analyzer import BaseAnalyzer, Finding


class IncludeAnalyzer(BaseAnalyzer):
    """Analyzes include directive compliance."""

    def analyze(self, file_path: str, content: str) -> List[Finding]:
        """
        Analyze file for include directive violations.

        Args:
            file_path: Path to file being analyzed
            content: Full file content

        Returns:
            List of include findings
        """
        findings = []
        lines = content.split("\n")

        findings.extend(self._check_include_order(file_path, lines))
        findings.extend(self._check_include_depth(file_path, lines))
        findings.extend(self._check_circular_includes(file_path, lines, content))

        return findings

    def _check_include_order(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check that includes are in proper order: own, system, project."""
        findings = []
        check_order = self.config.get("check_include_order", True)

        if not check_order:
            return findings

        # Parse includes
        includes = []
        for line_num, line in enumerate(lines, 1):
            match = re.match(r'#include\s+[<"]([^>"]+)[>"]', line)
            if match:
                header = match.group(1)
                bracket_type = "system" if "<" in line else "project"
                includes.append((line_num, header, bracket_type))

        # Classify includes
        own_header = self._get_own_header(file_path)
        classified = []

        for line_num, header, bracket_type in includes:
            if header == own_header:
                category = "own"
            elif bracket_type == "system":
                category = "system"
            else:
                category = "project"
            classified.append((line_num, header, category))

        # Expected order: own, system, project
        expected_order = ["own", "system", "project"]
        last_category_index = -1

        for line_num, header, category in classified:
            category_index = expected_order.index(category) if category in expected_order else -1

            if category_index < last_category_index:
                finding = self._make_finding(
                    file_path,
                    line_num,
                    1,
                    "INCLUDE-001",
                    f"Include out of order: {category} after {expected_order[last_category_index]}",
                    f"Reorder includes: own headers first, then system, then project",
                    self._read_file_context(lines, line_num, context=2),
                )
                findings.append(finding)
            elif category_index > last_category_index:
                last_category_index = category_index

        return findings

    def _check_include_depth(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check for excessive include nesting depth."""
        findings = []
        max_depth = self.config.get("max_include_depth", 5)

        # Simple heuristic: count how many includes appear in the file
        # and estimate depth based on header files
        include_count = 0
        for line in lines:
            if re.match(r'#include\s+', line):
                include_count += 1

        # If too many includes, likely deep nesting
        max_includes = self.config.get("max_includes", 20)
        if include_count > max_includes:
            finding = self._make_finding(
                file_path,
                1,
                1,
                "INCLUDE-002",
                f"Excessive includes ({include_count}, max {max_includes})",
                "Reduce include dependencies or consolidate headers",
                self._read_file_context(lines, 1, context=10),
                confidence=0.7,
            )
            findings.append(finding)

        return findings

    def _check_circular_includes(
        self, file_path: str, lines: List[str], content: str
    ) -> List[Finding]:
        """Detect potential circular include dependencies."""
        findings = []
        check_circular = self.config.get("check_circular_includes", True)

        if not check_circular:
            return findings

        # Extract includes from this file
        includes = []
        for line_num, line in enumerate(lines, 1):
            match = re.match(r'#include\s+[<"]([^>"]+)[>"]', line)
            if match:
                includes.append((line_num, match.group(1)))

        # Check for self-includes (crude circular detection)
        own_header = self._get_own_header(file_path)
        for line_num, header in includes:
            if header == own_header:
                finding = self._make_finding(
                    file_path,
                    line_num,
                    1,
                    "INCLUDE-003",
                    f"File includes itself ({own_header})",
                    "Remove self-include directive",
                    self._read_file_context(lines, line_num, context=1),
                )
                findings.append(finding)

        return findings

    def _get_own_header(self, file_path: str) -> str:
        """Get the corresponding header filename for a .c file."""
        import os
        basename = os.path.basename(file_path)
        name, ext = os.path.splitext(basename)

        # For .c files, expect .h
        if ext == ".c":
            return f"{name}.h"
        # For .cpp, expect .hpp
        elif ext == ".cpp":
            return f"{name}.hpp"
        # Otherwise return same name with .h
        return f"{name}.h"
