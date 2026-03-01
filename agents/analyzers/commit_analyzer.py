import re
from typing import List
from agents.analyzers.base_analyzer import BaseAnalyzer, Finding


class CommitAnalyzer(BaseAnalyzer):
    """Analyzes commit message compliance."""

    def analyze(self, file_path: str, content: str) -> List[Finding]:
        """
        Analyze commit message for compliance.

        Args:
            file_path: Path to commit message file or metadata
            content: Commit message content

        Returns:
            List of commit message findings
        """
        findings = []
        lines = content.split("\n")

        findings.extend(self._check_subject_line(file_path, lines))
        findings.extend(self._check_imperative_mood(file_path, lines))
        findings.extend(self._check_blank_after_subject(file_path, lines))
        findings.extend(self._check_signed_off_by(file_path, lines))
        findings.extend(self._check_dco(file_path, lines))
        findings.extend(self._check_trailers(file_path, lines))

        return findings

    def _check_subject_line(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check subject line length and format."""
        findings = []

        if not lines or not lines[0]:
            finding = self._make_finding(
                file_path,
                1,
                1,
                "COMMIT-001",
                "Missing commit subject line",
                "Add a descriptive subject line",
                "Empty",
            )
            findings.append(finding)
            return findings

        subject = lines[0]
        max_length = self.config.get("subject_line_max_length", 72)

        # Check length
        if len(subject) > max_length:
            finding = self._make_finding(
                file_path,
                1,
                max_length + 1,
                "COMMIT-002",
                f"Subject line too long ({len(subject)} chars, max {max_length})",
                f"Keep subject line under {max_length} characters",
                subject,
            )
            findings.append(finding)

        # Check trailing period
        if subject.rstrip().endswith("."):
            finding = self._make_finding(
                file_path,
                1,
                len(subject),
                "COMMIT-003",
                "Subject line has trailing period",
                "Remove trailing period from subject line",
                subject,
            )
            findings.append(finding)

        return findings

    def _check_imperative_mood(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check that subject line is in imperative mood."""
        findings = []

        if not lines or not lines[0]:
            return findings

        subject = lines[0]
        first_word = subject.split()[0] if subject.split() else ""

        # Common past-tense patterns
        past_tense_patterns = [
            r"^Added",
            r"^Fixed",
            r"^Changed",
            r"^Updated",
            r"^Removed",
            r"^Refactored",
            r"^Improved",
            r"^Created",
            r"^Deleted",
        ]

        for pattern in past_tense_patterns:
            if re.match(pattern, first_word):
                imperative = first_word[:-2] if first_word.endswith("ed") else first_word
                finding = self._make_finding(
                    file_path,
                    1,
                    1,
                    "COMMIT-004",
                    f"Subject line not in imperative mood ('{first_word}' is past tense)",
                    f"Use imperative: '{imperative}' instead of '{first_word}'",
                    subject,
                )
                findings.append(finding)
                break

        return findings

    def _check_blank_after_subject(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check that second line is blank."""
        findings = []
        check_blank = self.config.get("require_blank_line_after_subject", True)

        if not check_blank or len(lines) < 2:
            return findings

        if len(lines) > 1 and lines[1].strip():
            finding = self._make_finding(
                file_path,
                2,
                1,
                "COMMIT-005",
                "No blank line between subject and body",
                "Add blank line after subject line",
                "\n".join(lines[:3]),
            )
            findings.append(finding)

        return findings

    def _check_signed_off_by(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check for Signed-off-by trailer."""
        findings = []
        require_signoff = self.config.get("require_signed_off_by", False)

        if not require_signoff:
            return findings

        signoff_found = False
        signoff_pattern = r'^Signed-off-by:\s+.+\s+<.+@.+>'

        for line in lines:
            if re.match(signoff_pattern, line):
                signoff_found = True
                break

        if not signoff_found:
            finding = self._make_finding(
                file_path,
                len(lines),
                1,
                "COMMIT-006",
                "Missing Signed-off-by trailer",
                "Add: Signed-off-by: Name <email@domain.com>",
                "\n".join(lines[-5:]) if lines else "",
            )
            findings.append(finding)

        return findings

    def _check_dco(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Check for Developer Certificate of Origin compliance."""
        findings = []
        require_dco = self.config.get("require_dco", False)

        if not require_dco:
            return findings

        # For DCO, we need Signed-off-by
        signoff_found = False
        for line in lines:
            if re.match(r'^Signed-off-by:', line):
                signoff_found = True
                break

        if not signoff_found:
            finding = self._make_finding(
                file_path,
                len(lines),
                1,
                "COMMIT-007",
                "Not DCO compliant (missing Signed-off-by)",
                "Sign off with: Signed-off-by: Name <email@domain.com>",
                "\n".join(lines[-5:]) if lines else "",
            )
            findings.append(finding)

        return findings

    def _check_trailers(self, file_path: str, lines: List[str]) -> List[Finding]:
        """Validate required/prohibited trailers."""
        findings = []
        required_trailers = self.config.get("required_trailers", [])
        prohibited_trailers = self.config.get("prohibited_trailers", [])

        # Collect all trailers
        trailers = {}
        for line in reversed(lines):
            if ":" in line and re.match(r'^[\w-]+:', line):
                key = line.split(":")[0]
                trailers[key] = line
            elif line.strip() == "":
                continue
            else:
                break

        # Check required
        for required in required_trailers:
            if required not in trailers:
                finding = self._make_finding(
                    file_path,
                    len(lines),
                    1,
                    "COMMIT-008",
                    f"Missing required trailer: {required}",
                    f"Add trailer: {required}: <value>",
                    "\n".join(lines[-5:]) if lines else "",
                )
                findings.append(finding)

        # Check prohibited
        for prohibited in prohibited_trailers:
            if prohibited in trailers:
                finding = self._make_finding(
                    file_path,
                    len(lines),
                    1,
                    "COMMIT-009",
                    f"Prohibited trailer present: {prohibited}",
                    f"Remove trailer: {prohibited}",
                    trailers.get(prohibited, ""),
                )
                findings.append(finding)

        return findings
