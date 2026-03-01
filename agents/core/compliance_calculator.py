from typing import Dict, List, Tuple
from datetime import datetime
from agents.analyzers.base_analyzer import Finding, ComplianceReport


class ComplianceCalculator:
    """Calculates compliance metrics and generates reports."""

    def __init__(self, rules: dict, config: dict):
        """
        Initialize the compliance calculator.

        Args:
            rules: Dictionary of rule definitions
            config: Configuration dictionary
        """
        self.rules = rules
        self.config = config
        self.analyzers: Dict[str, object] = {}

    def register_analyzer(self, domain: str, analyzer: object) -> None:
        """
        Register an analyzer for a domain.

        Args:
            domain: Domain name (e.g., "style", "license", "whitespace")
            analyzer: Analyzer instance
        """
        self.analyzers[domain] = analyzer

    def audit_codebase(self, file_metadata_list) -> ComplianceReport:
        """
        Audit entire codebase using registered analyzers.

        Args:
            file_metadata_list: List of FileMetadata objects

        Returns:
            ComplianceReport with findings and scores
        """
        all_findings = []

        # Process each file through all analyzers
        from agents.core.file_processor import FileProcessor
        processor = FileProcessor(self.config)

        for metadata in file_metadata_list:
            try:
                content = processor.get_file_content(metadata.path)
                findings = self._audit_file(metadata.path, content)
                all_findings.extend(findings)
            except (OSError, IOError):
                # Skip files that can't be read
                continue

        # Deduplicate findings
        deduplicated = self._dedup_findings(all_findings)

        # Compute domain scores
        domain_scores = self._compute_domain_scores(deduplicated)

        # Compute overall grade
        if domain_scores:
            avg_score = sum(domain_scores.values()) / len(domain_scores)
        else:
            avg_score = 100.0
        overall_grade = self._compute_grade(avg_score)

        # Group findings by domain
        by_domain = {}
        for finding in deduplicated:
            domain = finding.category
            if domain not in by_domain:
                by_domain[domain] = []
            by_domain[domain].append(finding)

        return ComplianceReport(
            findings=deduplicated,
            by_domain=by_domain,
            domain_scores=domain_scores,
            overall_grade=overall_grade,
            file_count=len(file_metadata_list),
            timestamp=datetime.now(),
        )

    def _audit_file(self, file_path: str, content: str) -> List[Finding]:
        """
        Run all registered analyzers on a file.

        Args:
            file_path: Path to the file
            content: File content

        Returns:
            List of findings from all analyzers
        """
        findings = []

        for domain, analyzer in self.analyzers.items():
            try:
                domain_findings = analyzer.analyze(file_path, content)
                findings.extend(domain_findings)
            except Exception:
                # Skip analyzers that fail
                continue

        return findings

    def _dedup_findings(self, findings: List[Finding]) -> List[Finding]:
        """
        Remove duplicate findings keyed on (file, line, rule_id).

        Args:
            findings: List of findings

        Returns:
            Deduplicated list of findings
        """
        seen: Dict[Tuple[str, int, str], Finding] = {}

        for finding in findings:
            key = (finding.file_path, finding.line_number, finding.rule_id)
            # Keep first occurrence, which has highest confidence
            if key not in seen:
                seen[key] = finding

        return list(seen.values())

    def _compute_domain_scores(self, findings: List[Finding]) -> Dict[str, float]:
        """
        Compute compliance scores for each domain.

        Args:
            findings: List of all findings

        Returns:
            Dictionary mapping domain to score (0-100)
        """
        # Group findings by category (domain)
        by_category = {}
        for finding in findings:
            if finding.category not in by_category:
                by_category[finding.category] = []
            by_category[finding.category].append(finding)

        # Score each domain
        domain_scores = {}
        for domain, domain_findings in by_category.items():
            score = self._score_domain(domain_findings)
            domain_scores[domain] = score

        return domain_scores

    def _score_domain(self, findings: List[Finding]) -> float:
        """
        Score a domain based on severity-weighted penalties.

        Args:
            findings: List of findings in the domain

        Returns:
            Score from 0-100
        """
        # Severity penalty weights
        penalties = {
            "CRITICAL": -15.0,
            "HIGH": -10.0,
            "MEDIUM": -5.0,
            "LOW": -2.0,
        }

        score = 100.0

        for finding in findings:
            penalty = penalties.get(finding.severity, -5.0)
            score += penalty

        # Clamp to 0-100
        return max(0.0, min(100.0, score))

    def _compute_grade(self, avg_score: float) -> str:
        """
        Convert average score to letter grade.

        Args:
            avg_score: Average domain score

        Returns:
            Letter grade A/B/C/D/F
        """
        if avg_score >= 90:
            return "A"
        elif avg_score >= 80:
            return "B"
        elif avg_score >= 70:
            return "C"
        elif avg_score >= 60:
            return "D"
        else:
            return "F"
