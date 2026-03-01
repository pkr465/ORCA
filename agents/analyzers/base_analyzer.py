from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
import os


class Severity(Enum):
    """Severity levels for findings."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class Finding:
    """Represents a single compliance finding."""
    file_path: str
    line_number: int
    column: int
    severity: str
    category: str
    rule_id: str
    message: str
    suggestion: str
    code_snippet: str
    confidence: float  # 0.0 to 1.0
    tool: str


@dataclass
class ComplianceReport:
    """Complete compliance audit report."""
    findings: List[Finding] = field(default_factory=list)
    by_domain: Dict[str, List[Finding]] = field(default_factory=dict)
    domain_scores: Dict[str, float] = field(default_factory=dict)
    overall_grade: str = "A"
    file_count: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


class BaseAnalyzer(ABC):
    """Base class for all compliance analyzers."""

    def __init__(self, rules: dict, config: dict):
        """
        Initialize the analyzer with rules and configuration.

        Args:
            rules: Dictionary containing rule definitions
            config: Dictionary containing analyzer configuration
        """
        self.rules = rules
        self.config = config

    @abstractmethod
    def analyze(self, file_path: str, content: str) -> List[Finding]:
        """
        Analyze file content for compliance violations.

        Args:
            file_path: Path to the file being analyzed
            content: Full content of the file

        Returns:
            List of findings detected in the file
        """
        pass

    def _make_finding(
        self,
        file_path: str,
        line_number: int,
        column: int,
        rule_id: str,
        message: str,
        suggestion: str,
        code_snippet: str,
        confidence: float = 1.0,
    ) -> Finding:
        """
        Create a Finding object with standard fields.

        Args:
            file_path: Path to file with violation
            line_number: Line number of violation
            column: Column number of violation
            rule_id: ID of the violated rule
            message: Human-readable violation message
            suggestion: Suggested fix or improvement
            code_snippet: The problematic code snippet
            confidence: Confidence level 0.0-1.0

        Returns:
            Finding object
        """
        severity = self._get_severity(rule_id)
        rule_info = self.rules.get(rule_id, {})
        category = rule_info.get("category", "uncategorized")

        return Finding(
            file_path=file_path,
            line_number=line_number,
            column=column,
            severity=severity,
            category=category,
            rule_id=rule_id,
            message=message,
            suggestion=suggestion,
            code_snippet=code_snippet,
            confidence=confidence,
            tool=self.__class__.__name__,
        )

    def _read_file_context(
        self, lines: List[str], line_num: int, context: int = 2
    ) -> str:
        """
        Extract code snippet with context around a line number.

        Args:
            lines: List of all file lines
            line_num: 1-based line number to get context around
            context: Number of lines before/after to include

        Returns:
            String with code snippet and context
        """
        start = max(0, line_num - context - 1)
        end = min(len(lines), line_num + context)

        snippet_lines = []
        for i in range(start, end):
            if i < len(lines):
                prefix = ">>>" if i == line_num - 1 else "   "
                snippet_lines.append(f"{prefix} {i + 1}: {lines[i]}")

        return "\n".join(snippet_lines)

    def _get_severity(self, rule_id: str) -> str:
        """
        Get severity level for a rule, checking overrides first.

        Args:
            rule_id: ID of the rule

        Returns:
            Severity level as string (CRITICAL, HIGH, MEDIUM, LOW)
        """
        # Check severity overrides in config
        overrides = self.config.get("severity_overrides", {})
        if rule_id in overrides:
            return overrides[rule_id]

        # Check rule definition
        rule = self.rules.get(rule_id, {})
        severity = rule.get("severity", "MEDIUM")

        # Validate severity
        valid_severities = [s.value for s in Severity]
        if severity not in valid_severities:
            return "MEDIUM"

        return severity
