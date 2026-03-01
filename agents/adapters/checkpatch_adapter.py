"""Checkpatch.pl adapter for kernel coding style compliance."""
import subprocess
import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from agents.adapters.base_adapter import BaseComplianceAdapter, AdapterResult

class CheckpatchAdapter(BaseComplianceAdapter):
    """Adapter for checkpatch.pl code style checker."""
    
    DOMAIN = "code_style"
    
    def __init__(self, rules: dict, config: dict):
        """Initialize checkpatch adapter.
        
        Args:
            rules: Configuration rules including patch.checkpatch settings
            config: Global configuration with optional --checkpatch-path
        """
        super().__init__(rules, config)
        self.checkpatch_path = self._find_checkpatch()
        self.tool_available = self.checkpatch_path is not None
    
    def _find_checkpatch(self) -> Optional[str]:
        """Find checkpatch.pl in common locations.
        
        Searches in order:
        1. config --checkpatch-path if provided
        2. ./scripts/checkpatch.pl relative to cwd
        3. $CHECKPATCH_PATH environment variable
        4. Standard locations like /usr/bin/checkpatch.pl
        
        Returns:
            Path to checkpatch.pl or None if not found
        """
        candidates = []
        
        # Config-specified path
        config_path = None
        if self.config:
            if hasattr(self.config, 'get'):
                config_path = self.config.get("checkpatch_path")
            elif hasattr(self.config, 'checkpatch_path'):
                config_path = self.config.checkpatch_path
        if config_path:
            candidates.append(config_path)
        
        # Relative to scripts directory
        candidates.append(os.path.join(os.getcwd(), "scripts", "checkpatch.pl"))
        
        # Environment variable
        env_path = os.environ.get("CHECKPATCH_PATH")
        if env_path:
            candidates.append(env_path)
        
        # Standard locations
        candidates.extend([
            "/usr/bin/checkpatch.pl",
            "/usr/local/bin/checkpatch.pl",
            "/usr/share/checkpatch/checkpatch.pl",
        ])
        
        for path in candidates:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                self.logger.info(f"Found checkpatch.pl at {path}")
                return path
        
        self.logger.warning("checkpatch.pl not found in any standard locations")
        return None
    
    def analyze(self, file_cache: Dict[str, str], **kwargs) -> AdapterResult:
        """Analyze files using checkpatch.pl.
        
        Args:
            file_cache: Dict of {file_path: file_content}
            **kwargs: Additional arguments (unused)
            
        Returns:
            AdapterResult with findings and score
        """
        findings = []
        error = None
        
        if not self.tool_available:
            return AdapterResult(
                score=100.0,
                grade="A",
                domain=self.DOMAIN,
                findings=[],
                summary={"status": "tool_unavailable"},
                tool_available=False,
                tool_name="checkpatch.pl",
                error="checkpatch.pl not found"
            )
        
        try:
            # Filter to C/patch files
            c_files = {
                path: content for path, content in file_cache.items()
                if path.endswith(('.c', '.h', '.patch'))
            }
            
            if not c_files:
                return AdapterResult(
                    score=100.0,
                    grade="A",
                    domain=self.DOMAIN,
                    findings=[],
                    summary={"files_checked": 0},
                    tool_available=True,
                    tool_name="checkpatch.pl"
                )
            
            for file_path, content in c_files.items():
                findings.extend(self._check_file(file_path, content))
        
        except Exception as e:
            self.logger.error(f"Error running checkpatch: {e}")
            error = str(e)
        
        score = self._compute_score(findings, len(c_files))
        grade = self._compute_grade(score)
        
        return AdapterResult(
            score=score,
            grade=grade,
            domain=self.DOMAIN,
            findings=findings,
            summary={
                "files_checked": len(c_files),
                "issues_found": len(findings),
                "critical": len([f for f in findings if f.severity == "critical"]),
                "high": len([f for f in findings if f.severity == "high"]),
            },
            tool_available=True,
            tool_name="checkpatch.pl",
            error=error
        )
    
    def _check_file(self, file_path: str, content: str) -> List:
        """Run checkpatch on a single file.
        
        Args:
            file_path: Path to file
            content: File content
            
        Returns:
            List of Finding objects
        """
        findings = []
        
        if not os.path.exists(file_path):
            # For files in cache that don't exist on disk, create temp file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                findings = self._run_checkpatch(tmp_path, file_path)
            finally:
                os.unlink(tmp_path)
        else:
            findings = self._run_checkpatch(file_path, file_path)
        
        return findings
    
    def _run_checkpatch(self, check_path: str, report_path: str) -> List:
        """Execute checkpatch.pl on a file.
        
        Args:
            check_path: Path to check (may be temp file)
            report_path: Path to report in findings (original path)
            
        Returns:
            List of Finding objects
        """
        findings = []
        
        try:
            result = subprocess.run(
                [self.checkpatch_path, check_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Parse output: FILE:LINE: TYPE: MESSAGE
            # Example: drivers/gpu/drm/i915/i915_drv.h:123: WARNING: line length
            pattern = r'^([^:]+):(\d+):\s*([A-Z]+):\s*(.+)$'
            
            for line in result.stdout.split('\n') + result.stderr.split('\n'):
                match = re.match(pattern, line)
                if match:
                    file_ref, line_num, issue_type, message = match.groups()
                    
                    # Map checkpatch types to our severity
                    severity = self._map_severity(issue_type)
                    
                    # Create finding
                    finding = self._make_finding(
                        file_path=report_path,
                        line=int(line_num),
                        rule_id=f"checkpatch:{issue_type.lower()}",
                        message=message.strip(),
                        severity=severity,
                        domain=self.DOMAIN,
                        suggested_fix=self._get_fix_suggestion(issue_type, message)
                    )
                    findings.append(finding)
        
        except subprocess.TimeoutExpired:
            self.logger.warning(f"checkpatch timeout for {check_path}")
        except Exception as e:
            self.logger.error(f"Error running checkpatch on {check_path}: {e}")
        
        return findings
    
    def _map_severity(self, checkpatch_type: str) -> str:
        """Map checkpatch issue type to severity level.
        
        Args:
            checkpatch_type: ERROR, WARNING, or CHECK
            
        Returns:
            Severity: critical, high, medium, or low
        """
        type_map = {
            "ERROR": "critical",
            "WARNING": "high",
            "CHECK": "medium",
        }
        return type_map.get(checkpatch_type.upper(), "low")
    
    def _get_fix_suggestion(self, issue_type: str, message: str) -> str:
        """Generate fix suggestion based on issue type.
        
        Args:
            issue_type: checkpatch issue type
            message: Issue message
            
        Returns:
            Suggested fix text
        """
        suggestions = {
            "line length": "Keep lines under 80 characters (or 100 for code)",
            "whitespace": "Fix whitespace issues (spaces vs tabs, trailing spaces)",
            "indentation": "Use tabs for indentation, not spaces",
            "spacing": "Fix spacing around operators and keywords",
            "braces": "Adjust brace placement per coding style",
            "comments": "Fix comment formatting",
        }
        
        for keyword, suggestion in suggestions.items():
            if keyword.lower() in message.lower():
                return suggestion
        
        return "Review checkpatch output and fix the reported issue"
    
    def is_available(self) -> bool:
        """Check if checkpatch.pl is available."""
        return self.tool_available
