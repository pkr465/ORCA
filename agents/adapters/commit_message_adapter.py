"""Commit message format validation adapter."""
import subprocess
import re
import os
from typing import Dict, List, Optional
from agents.adapters.base_adapter import BaseComplianceAdapter, AdapterResult

class CommitMessageAdapter(BaseComplianceAdapter):
    """Adapter for validating commit message format."""
    
    DOMAIN = "patch_format"
    
    def __init__(self, rules: dict, config: dict):
        """Initialize commit message adapter.
        
        Args:
            rules: Configuration rules including patch.commit settings
            config: Global configuration
        """
        super().__init__(rules, config)
        self.gitlint_available = self._check_gitlint_available()
        self.commit_rules = rules.get("patch", {}).get("commit", {})
    
    def _check_gitlint_available(self) -> bool:
        """Check if gitlint CLI tool is available."""
        try:
            result = subprocess.run(
                ["gitlint", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            available = result.returncode == 0
            self.logger.info(f"gitlint available: {available}")
            return available
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self.logger.debug("gitlint not available")
            return False
    
    def analyze(self, file_cache: Dict[str, str], **kwargs) -> AdapterResult:
        """Analyze commit messages for format compliance.
        
        Args:
            file_cache: Dict of {file_path: file_content}
            **kwargs: Additional arguments (may include commits list or COMMIT_EDITMSG)
            
        Returns:
            AdapterResult with findings and score
        """
        findings = []
        error = None
        commits_analyzed = 0
        
        try:
            # Check for COMMIT_EDITMSG file (during commit hook)
            if "COMMIT_EDITMSG" in file_cache:
                message = file_cache["COMMIT_EDITMSG"]
                findings.extend(self._validate_message(message, "COMMIT_EDITMSG", 1))
                commits_analyzed = 1
            else:
                # Try to get commits from git log
                commits = self._get_recent_commits(kwargs.get("commit_count", 5))
                for commit_hash, message in commits:
                    findings.extend(self._validate_message(message, commit_hash, 1))
                    commits_analyzed += 1
        
        except Exception as e:
            self.logger.error(f"Error analyzing commit messages: {e}")
            error = str(e)
        
        if commits_analyzed == 0:
            # No commits to analyze, that's okay
            commits_analyzed = 1
            findings = []
        
        score = self._compute_score(findings, commits_analyzed)
        grade = self._compute_grade(score)
        
        return AdapterResult(
            score=score,
            grade=grade,
            domain=self.DOMAIN,
            findings=findings,
            summary={
                "commits_analyzed": commits_analyzed,
                "issues_found": len(findings),
                "gitlint_available": self.gitlint_available,
            },
            tool_available=True,
            tool_name="gitlint/commit_validator"
        )
    
    def _get_recent_commits(self, count: int) -> List[tuple]:
        """Get recent commits from git log.
        
        Args:
            count: Number of commits to retrieve
            
        Returns:
            List of (hash, message) tuples
        """
        commits = []
        
        try:
            result = subprocess.run(
                ["git", "log", f"-{count}", "--format=%H%n%B%n---COMMIT_END---"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=os.getcwd()
            )
            
            if result.returncode == 0:
                entries = result.stdout.split("---COMMIT_END---")
                for entry in entries:
                    if not entry.strip():
                        continue
                    lines = entry.strip().split('\n', 1)
                    if len(lines) == 2:
                        commit_hash = lines[0].strip()
                        message = lines[1].strip()
                        commits.append((commit_hash[:8], message))
        
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self.logger.debug("Could not retrieve git commits")
        
        return commits
    
    def _validate_message(self, message: str, ref: str, line: int) -> List:
        """Validate a single commit message.
        
        Args:
            message: Commit message text
            ref: Commit reference (hash or file)
            line: Line number reference
            
        Returns:
            List of Finding objects
        """
        findings = []
        
        if self.gitlint_available:
            findings.extend(self._validate_with_gitlint(message, ref, line))
        else:
            findings.extend(self._validate_builtin(message, ref, line))
        
        return findings
    
    def _validate_with_gitlint(self, message: str, ref: str, line: int) -> List:
        """Validate using gitlint CLI.
        
        Args:
            message: Commit message
            ref: Commit reference
            line: Line number
            
        Returns:
            List of Finding objects
        """
        findings = []
        
        try:
            result = subprocess.run(
                ["gitlint"],
                input=message,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Parse gitlint output: "1: T1 Title too long"
            for line_text in result.stdout.split('\n'):
                if not line_text.strip():
                    continue
                
                match = re.match(r'(\d+):\s*([A-Z]\d+)\s*(.+)', line_text)
                if match:
                    line_num, rule_id, message_text = match.groups()
                    severity = self._gitlint_severity(rule_id)
                    
                    finding = self._make_finding(
                        file_path=ref,
                        line=int(line_num),
                        rule_id=f"gitlint:{rule_id}",
                        message=message_text,
                        severity=severity,
                        domain=self.DOMAIN,
                        suggested_fix=self._gitlint_suggestion(rule_id)
                    )
                    findings.append(finding)
        
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self.logger.debug("gitlint validation failed")
        except Exception as e:
            self.logger.error(f"Error validating with gitlint: {e}")
        
        return findings
    
    def _validate_builtin(self, message: str, ref: str, line: int) -> List:
        """Built-in commit message validation.
        
        Args:
            message: Commit message
            ref: Commit reference
            line: Line number
            
        Returns:
            List of Finding objects
        """
        findings = []
        lines = message.split('\n')
        
        if not lines:
            return findings
        
        subject = lines[0]
        body = '\n'.join(lines[1:]) if len(lines) > 1 else ""
        
        # Validate subject line length
        max_subject_len = self.commit_rules.get("subject_length", 72)
        if len(subject) > max_subject_len:
            finding = self._make_finding(
                file_path=ref,
                line=1,
                rule_id="commit:subject_length",
                message=f"Subject line too long ({len(subject)} > {max_subject_len} chars)",
                severity="medium",
                domain=self.DOMAIN,
                suggested_fix=f"Keep subject line under {max_subject_len} characters"
            )
            findings.append(finding)
        
        # Validate subject capitalization
        if subject and subject[0].islower():
            finding = self._make_finding(
                file_path=ref,
                line=1,
                rule_id="commit:subject_capitalization",
                message="Subject line should start with uppercase letter",
                severity="low",
                domain=self.DOMAIN,
                suggested_fix="Capitalize first character of subject line"
            )
            findings.append(finding)
        
        # Check blank line between subject and body
        if len(lines) > 1:
            if lines[1].strip() != "":
                finding = self._make_finding(
                    file_path=ref,
                    line=2,
                    rule_id="commit:blank_line",
                    message="Missing blank line between subject and body",
                    severity="medium",
                    domain=self.DOMAIN,
                    suggested_fix="Add blank line after subject line"
                )
                findings.append(finding)
        
        # Validate Signed-off-by format
        if self.commit_rules.get("require_signoff", False):
            if not self._has_valid_signoff(message):
                finding = self._make_finding(
                    file_path=ref,
                    line=len(lines),
                    rule_id="commit:missing_signoff",
                    message="Missing or invalid Signed-off-by trailer",
                    severity="high",
                    domain=self.DOMAIN,
                    suggested_fix='Add "Signed-off-by: Your Name <email@domain>" to end of message'
                )
                findings.append(finding)
        
        # Check for Co-authored-by format if present
        findings.extend(self._validate_trailers(message, ref))
        
        return findings
    
    def _has_valid_signoff(self, message: str) -> bool:
        """Check for valid Signed-off-by trailer.
        
        Args:
            message: Commit message
            
        Returns:
            True if valid Signed-off-by present
        """
        # Pattern: Signed-off-by: Name <email@domain>
        pattern = r'^Signed-off-by:\s+.+\s+<[^@]+@[^>]+>$'
        for line in message.split('\n'):
            if re.match(pattern, line.strip()):
                return True
        return False
    
    def _validate_trailers(self, message: str, ref: str) -> List:
        """Validate commit trailers (Signed-off-by, Co-authored-by, etc).
        
        Args:
            message: Commit message
            ref: Commit reference
            
        Returns:
            List of Finding objects
        """
        findings = []
        lines = message.split('\n')
        
        # Find trailer lines (typically at end after blank line)
        trailer_pattern = r'^([A-Z][a-z-]+):\s+(.+)$'
        
        for i, line in enumerate(lines):
            if re.match(trailer_pattern, line.strip()):
                key, value = re.match(trailer_pattern, line.strip()).groups()
                
                # Validate specific trailer formats
                if key == "Signed-off-by" or key == "Co-authored-by":
                    if not re.match(r'.+\s+<[^@]+@[^>]+>', value):
                        finding = self._make_finding(
                            file_path=ref,
                            line=i + 1,
                            rule_id=f"commit:{key.lower().replace('-', '_')}",
                            message=f"Invalid {key} format: {value}",
                            severity="high",
                            domain=self.DOMAIN,
                            suggested_fix=f"Use format: {key}: Name <email@domain>"
                        )
                        findings.append(finding)
        
        return findings
    
    def _gitlint_severity(self, rule_id: str) -> str:
        """Map gitlint rule to severity.
        
        Args:
            rule_id: gitlint rule ID (e.g., T1, R1, B1)
            
        Returns:
            Severity level
        """
        severity_map = {
            "T": "medium",  # Title rules
            "B": "medium",  # Body rules
            "R": "high",    # Recency rules
            "M": "high",    # Message rules
        }
        if rule_id and rule_id[0] in severity_map:
            return severity_map[rule_id[0]]
        return "medium"
    
    def _gitlint_suggestion(self, rule_id: str) -> str:
        """Get suggestion for gitlint rule violation.
        
        Args:
            rule_id: gitlint rule ID
            
        Returns:
            Suggestion text
        """
        suggestions = {
            "T1": "Keep subject line under 72 characters",
            "T2": "Ensure subject line ends with period",
            "T3": "Subject line should start with uppercase",
            "T4": "Subject line should not end with period",
            "T5": "Use imperative mood in subject line",
            "T6": "Separate subject from body with blank line",
            "R1": "Reference commits in format: commit <hash>",
            "R2": "Use well-formed references",
        }
        return suggestions.get(rule_id, "Review gitlint documentation for rule details")
