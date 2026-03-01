"""Base compliance adapter abstract class."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

@dataclass
class AdapterResult:
    """Standardized result from a compliance adapter."""
    score: float  # 0-100
    grade: str  # A-F
    domain: str
    findings: List[Any]  # List of Finding objects
    summary: Dict[str, Any]
    tool_available: bool
    tool_name: str
    error: Optional[str] = None

class BaseComplianceAdapter(ABC):
    """Abstract base for all compliance adapters."""
    
    def __init__(self, rules: dict, config: dict):
        self.rules = rules
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def analyze(self, file_cache: Dict[str, str], **kwargs) -> AdapterResult:
        """Run analysis. Returns standardized AdapterResult."""
        ...
    
    def is_available(self) -> bool:
        """Check if external tool is available."""
        return True
    
    def _make_finding(self, file_path, line, rule_id, message, severity, domain, suggested_fix=None):
        """Create a Finding object for reporting."""
        # Import here to avoid circular dependencies
        from agents.analyzers.base_analyzer import Finding
        return Finding(
            file_path=file_path,
            line_number=line,
            column=1,
            severity=severity,
            category=domain,
            rule_id=rule_id,
            message=message,
            suggestion=suggested_fix or "",
            code_snippet="",
            confidence=1.0,
            tool=self.__class__.__name__
        )
    
    def _compute_score(self, findings: list, total_files: int) -> float:
        """Compute compliance score 0-100 based on findings severity.
        
        Args:
            findings: List of Finding objects
            total_files: Total number of files analyzed
            
        Returns:
            Score between 0-100
        """
        if total_files == 0:
            return 100.0
        severity_weights = {"critical": 15, "high": 10, "medium": 5, "low": 2}
        penalty = sum(severity_weights.get(f.severity, 2) for f in findings)
        max_penalty = total_files * 20  # rough normalization
        score = max(0, 100 - (penalty / max(max_penalty, 1) * 100))
        return round(score, 1)
    
    def _compute_grade(self, score: float) -> str:
        """Convert score to letter grade A-F.
        
        Args:
            score: Score 0-100
            
        Returns:
            Letter grade A-F
        """
        if score >= 90: return "A"
        if score >= 80: return "B"
        if score >= 70: return "C"
        if score >= 60: return "D"
        return "F"
