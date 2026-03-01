import re
from typing import List, Set, Dict
from agents.analyzers.base_analyzer import BaseAnalyzer, Finding


class LicenseAnalyzer(BaseAnalyzer):
    """Analyzes license header compliance."""

    # SPDX license identifier pattern
    SPDX_PATTERN = r'SPDX-License-Identifier:\s*(.+)'

    # Common copyright header patterns
    COPYRIGHT_PATTERNS = [
        r'Copyright\s+\(c\)\s+\d{4}.*',
        r'Copyright\s+\d{4}.*',
        r'\(c\)\s+\d{4}.*',
        r'Copyright.*\d{4}',
    ]

    # Comprehensive set of valid SPDX identifiers
    KNOWN_SPDX_IDS = {
        "Apache-2.0", "MIT", "GPL-2.0", "GPL-3.0", "LGPL-2.1", "LGPL-3.0",
        "BSD-2-Clause", "BSD-3-Clause", "ISC", "MPL-2.0", "AGPL-3.0",
        "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later",
        "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later",
        "AGPL-3.0-only", "AGPL-3.0-or-later", "Unlicense", "CC0-1.0",
        "Zlib", "BSL-1.0", "EPL-1.0", "EPL-2.0", "EUPL-1.2",
        "WTFPL", "0BSD", "Artistic-2.0", "Python-2.0", "CPAL-1.0",
    }

    # License compatibility matrix
    LICENSE_COMPATIBILITY = {
        "GPL-2.0": {"LGPL-2.1", "AGPL-3.0"},
        "GPL-3.0": {"LGPL-3.0", "AGPL-3.0"},
        "MIT": {"Apache-2.0", "GPL-2.0", "GPL-3.0", "ISC"},
        "Apache-2.0": {"MIT", "GPL-3.0"},
    }

    def analyze(self, file_path: str, content: str) -> List[Finding]:
        """
        Analyze file for license compliance.

        Args:
            file_path: Path to file being analyzed
            content: Full file content

        Returns:
            List of license findings
        """
        findings = []
        lines = content.split("\n")

        # Only check license headers on source files
        if not (file_path.endswith((".c", ".h", ".cpp", ".hpp"))):
            return findings

        findings.extend(self._check_spdx_header(file_path, lines))
        findings.extend(self._check_copyright_header(file_path, lines))
        findings.extend(self._check_license_compatibility(file_path, lines))
        findings.extend(self._check_reuse_compliance(file_path, lines))
        findings.extend(self._check_license_header_format(file_path, lines))

        return findings

    def _check_spdx_header(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check for SPDX license identifier in first 15 lines."""
        findings = []
        spdx_found = None
        spdx_line = 0

        # Scan first 15 lines
        for line_num, line in enumerate(lines[:15], 1):
            match = re.search(self.SPDX_PATTERN, line)
            if match:
                spdx_found = match.group(1).strip()
                spdx_line = line_num
                break

        if not spdx_found:
            finding = self._make_finding(
                file_path,
                1,
                1,
                "LICENSE-001",
                "Missing SPDX-License-Identifier header",
                "Add SPDX identifier to file header (e.g., // SPDX-License-Identifier: MIT)",
                self._read_file_context(lines, 1, context=3),
            )
            findings.append(finding)
            return findings

        # Validate SPDX ID
        allowed_licenses = self.config.get("allowed_licenses", self.KNOWN_SPDX_IDS)
        if spdx_found not in allowed_licenses:
            finding = self._make_finding(
                file_path,
                spdx_line,
                1,
                "LICENSE-002",
                f"Invalid or disallowed SPDX license ID: {spdx_found}",
                f"Use one of allowed licenses: {', '.join(sorted(allowed_licenses))}",
                self._read_file_context(lines, spdx_line, context=2),
                confidence=0.95,
            )
            findings.append(finding)

        return findings

    def _check_copyright_header(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check for copyright header in first 25 lines."""
        findings = []
        copyright_found = False

        # Scan first 25 lines
        for line_num, line in enumerate(lines[:25], 1):
            for pattern in self.COPYRIGHT_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    copyright_found = True
                    break
            if copyright_found:
                break

        require_copyright = self.config.get("require_copyright_header", True)
        if require_copyright and not copyright_found:
            finding = self._make_finding(
                file_path,
                1,
                1,
                "LICENSE-003",
                "Missing copyright header",
                "Add copyright notice to file header (e.g., // Copyright 2024 Company Name)",
                self._read_file_context(lines, 1, context=5),
            )
            findings.append(finding)

        return findings

    def _check_license_compatibility(
        self, file_path: str, lines: List[str]
    ) -> List[Finding]:
        """Check license compatibility against disallowed combinations."""
        findings = []

        # Extract SPDX ID
        spdx_found = None
        spdx_line = 0
        for line_num, line in enumerate(lines[:15], 1):
            match = re.search(self.SPDX_PATTERN, line)
            if match:
                spdx_found = match.group(1).strip()
                spdx_line = line_num
                break

        if not spdx_found:
            return findings

        # Check compatibility
        incompatible_licenses = self.config.get("incompatible_licenses", [])
        if spdx_found in incompatible_licenses:
            finding = self._make_finding(
                file_path,
                spdx_line,
                1,
                "LICENSE-004",
                f"License {spdx_found} is incompatible with project requirements",
                f"Use a compatible license instead",
                self._read_file_context(lines, spdx_line, context=2),
            )
            findings.append(finding)

        return findings

    def _check_reuse_compliance(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check REUSE compliance (SPDX + Copyright required)."""
        findings = []
        check_reuse = self.config.get("check_reuse_compliance", False)

        if not check_reuse:
            return findings

        # Check for both SPDX and copyright
        spdx_found = False
        copyright_found = False

        for line_num, line in enumerate(lines[:25], 1):
            if re.search(self.SPDX_PATTERN, line):
                spdx_found = True
            for pattern in self.COPYRIGHT_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    copyright_found = True

        if spdx_found and copyright_found:
            return findings

        if not spdx_found or not copyright_found:
            missing = []
            if not spdx_found:
                missing.append("SPDX identifier")
            if not copyright_found:
                missing.append("copyright notice")

            finding = self._make_finding(
                file_path,
                1,
                1,
                "LICENSE-005",
                f"Not REUSE compliant: missing {', '.join(missing)}",
                "Add both SPDX identifier and copyright header for REUSE compliance",
                self._read_file_context(lines, 1, context=5),
            )
            findings.append(finding)

        return findings

    def _check_license_header_format(
        self, file_path: str, lines: List[str]
    ) -> List[Finding]:
        """Check for proper license header formatting."""
        findings = []
        format_style = self.config.get("license_header_format", "spdx_only")

        if format_style == "spdx_only":
            # Headers should be SPDX only, not traditional 50-line headers
            comment_block_size = 0
            in_comment = False

            for line_num, line in enumerate(lines[:30], 1):
                if "/*" in line:
                    in_comment = True
                    comment_block_size = 1
                elif "*/" in line:
                    in_comment = False
                    if comment_block_size > 20:
                        finding = self._make_finding(
                            file_path,
                            line_num - comment_block_size,
                            1,
                            "LICENSE-006",
                            f"Long license comment block ({comment_block_size} lines)",
                            "Use SPDX-License-Identifier instead of traditional license headers",
                            self._read_file_context(lines, line_num - comment_block_size, context=3),
                        )
                        findings.append(finding)
                        break
                elif in_comment:
                    comment_block_size += 1

        return findings
