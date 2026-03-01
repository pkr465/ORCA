import re
import os
from typing import List, Set
from agents.analyzers.base_analyzer import BaseAnalyzer, Finding


class StructureAnalyzer(BaseAnalyzer):
    """Analyzes code structure and organization compliance."""

    def analyze(self, file_path: str, content: str) -> List[Finding]:
        """
        Analyze file for structural violations.

        Args:
            file_path: Path to file being analyzed
            content: Full file content

        Returns:
            List of structure findings
        """
        findings = []
        lines = content.split("\n")

        findings.extend(self._check_file_naming(file_path))
        findings.extend(self._check_extern_in_c(file_path, lines))
        findings.extend(self._check_header_source_match(file_path))
        findings.extend(self._check_api_surface(file_path, lines))
        findings.extend(self._check_file_organization(file_path))

        return findings

    def _check_file_naming(self, file_path: str) -> List[Finding]:
        """Check file naming conventions."""
        findings = []
        check_naming = self.config.get("check_file_naming", True)

        if not check_naming:
            return findings

        basename = os.path.basename(file_path)
        name, ext = os.path.splitext(basename)

        naming_style = self.config.get("file_naming_style", "snake_case")

        # Check for snake_case
        if naming_style == "snake_case":
            if not re.match(r'^[a-z][a-z0-9_]*$', name):
                finding = self._make_finding(
                    file_path,
                    1,
                    1,
                    "STRUCT-001",
                    f"File '{basename}' not in snake_case",
                    f"Rename to snake_case (e.g., {self._to_snake_case(name)}{ext})",
                    basename,
                )
                findings.append(finding)

        # Check for CamelCase
        elif naming_style == "CamelCase":
            if not re.match(r'^[A-Z][a-zA-Z0-9]*$', name):
                finding = self._make_finding(
                    file_path,
                    1,
                    1,
                    "STRUCT-001",
                    f"File '{basename}' not in CamelCase",
                    f"Rename to CamelCase (e.g., {self._to_camel_case(name)}{ext})",
                    basename,
                )
                findings.append(finding)

        return findings

    def _to_snake_case(self, name: str) -> str:
        """Convert to snake_case."""
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    def _to_camel_case(self, name: str) -> str:
        """Convert to camelCase."""
        parts = name.split('_')
        return parts[0] + ''.join(p.capitalize() for p in parts[1:])

    def _check_extern_in_c(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check that .c files don't use extern keyword."""
        findings = []
        check_extern = self.config.get("disallow_extern_in_c_files", True)

        if not check_extern or not file_path.endswith(".c"):
            return findings

        for line_num, line in enumerate(lines, 1):
            if re.search(r'\bextern\b', line):
                finding = self._make_finding(
                    file_path,
                    line_num,
                    line.find("extern") + 1,
                    "STRUCT-002",
                    "extern keyword in .c file",
                    "Move extern declarations to .h header file",
                    self._read_file_context(lines, line_num, context=2),
                )
                findings.append(finding)

        return findings

    def _check_header_source_match(self, file_path: str) -> List[Finding]:
        """Check that .c files have corresponding .h."""
        findings = []
        check_match = self.config.get("require_header_for_source", True)

        if not check_match or not file_path.endswith(".c"):
            return findings

        # Get expected header path
        base_dir = os.path.dirname(file_path)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        header_path = os.path.join(base_dir, f"{base_name}.h")

        if not os.path.exists(header_path):
            finding = self._make_finding(
                file_path,
                1,
                1,
                "STRUCT-003",
                f"No corresponding header file ({base_name}.h)",
                f"Create {base_name}.h or update file location",
                os.path.basename(file_path),
            )
            findings.append(finding)

        return findings

    def _check_api_surface(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check that public functions are declared in headers."""
        findings = []
        check_api = self.config.get("check_api_declarations", False)

        if not check_api or not file_path.endswith(".c"):
            return findings

        # Find non-static functions
        func_pattern = r'^\s*(?!static\s)\w+[\s\*]+(\w+)\s*\([^)]*\)\s*$'

        public_functions = []
        for line_num, line in enumerate(lines, 1):
            match = re.match(func_pattern, line)
            if match:
                public_functions.append((line_num, match.group(1)))

        # Check if corresponding .h file has declarations
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        base_dir = os.path.dirname(file_path)
        header_path = os.path.join(base_dir, f"{base_name}.h")

        if os.path.exists(header_path):
            try:
                with open(header_path, 'r', encoding='utf-8', errors='ignore') as f:
                    header_content = f.read()

                for line_num, func_name in public_functions:
                    if func_name not in header_content:
                        finding = self._make_finding(
                            file_path,
                            line_num,
                            1,
                            "STRUCT-004",
                            f"Public function '{func_name}' not declared in header",
                            f"Add declaration to {base_name}.h",
                            self._read_file_context(lines, line_num, context=1),
                        )
                        findings.append(finding)
            except (OSError, IOError):
                pass

        return findings

    def _check_file_organization(self, file_path: str) -> List[Finding]:
        """Check file organization (headers in include/, sources in src/)."""
        findings = []
        check_org = self.config.get("check_directory_organization", True)

        if not check_org:
            return findings

        relative_path = file_path
        is_header = file_path.endswith((".h", ".hpp", ".hxx"))
        is_source = file_path.endswith((".c", ".cpp", ".cc"))

        # Check header location
        if is_header and "/src/" in relative_path and "/include/" not in relative_path:
            finding = self._make_finding(
                file_path,
                1,
                1,
                "STRUCT-005",
                "Header file in src/ directory instead of include/",
                "Move header to include/ directory",
                os.path.basename(file_path),
            )
            findings.append(finding)

        # Check source location
        if is_source and "/include/" in relative_path and "/src/" not in relative_path:
            finding = self._make_finding(
                file_path,
                1,
                1,
                "STRUCT-006",
                "Source file in include/ directory instead of src/",
                "Move source to src/ directory",
                os.path.basename(file_path),
            )
            findings.append(finding)

        return findings
