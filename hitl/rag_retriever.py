"""RAG context retrieval for LLM prompt injection."""
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from hitl.feedback_store import FeedbackStore, ComplianceDecision

logger = logging.getLogger(__name__)


@dataclass
class RAGContext:
    """Context retrieved from RAG for decision recommendations."""
    past_decisions: List[ComplianceDecision] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    recommendation: str = ""


class RAGRetriever:
    """Retrieves relevant context from feedback store for LLM decision support."""

    def __init__(self, feedback_store: FeedbackStore, config: Optional[Dict] = None):
        """Initialize RAG retriever.
        
        Args:
            feedback_store: FeedbackStore instance for querying decisions
            config: Optional configuration dictionary with keys:
                - similarity_threshold: float (default 0.3)
                - top_k: int (default 5)
        """
        self.feedback_store = feedback_store
        self.config = config or {}
        self.similarity_threshold = self.config.get('similarity_threshold', 0.3)
        self.top_k = self.config.get('top_k', 5)

    def retrieve_context(self, finding, top_k: Optional[int] = None) -> RAGContext:
        """Retrieve RAG context for a given finding.

        Args:
            finding: Dictionary or Finding object with keys: rule_id, file_path, violation_text, project
            top_k: Override default top_k

        Returns:
            RAGContext with past decisions and recommendation
        """
        k = top_k or self.top_k
        rule_id = self._get_field(finding, 'rule_id', '')
        file_path = self._get_field(finding, 'file_path', '')
        project = self._get_field(finding, 'project', '')
        
        # Find similar decisions
        similar_decisions = self._find_similar_decisions(finding)
        
        # Apply threshold filtering
        filtered_decisions = self._apply_threshold(similar_decisions, self.similarity_threshold)
        
        # Limit to top_k
        top_decisions = filtered_decisions[:k]
        
        # Generate recommendation from past decisions
        recommendation = self._generate_recommendation(top_decisions)
        
        # Extract constraints from decisions
        constraints = [d.constraints for d in top_decisions if d.constraints]
        
        context = RAGContext(
            past_decisions=top_decisions,
            constraints=constraints,
            recommendation=recommendation,
        )
        
        logger.debug(f"Retrieved {len(top_decisions)} similar decisions for {rule_id}")
        return context

    def _get_field(self, finding, field_name: str, default=''):
        """Extract field from either dict or Finding object.

        Args:
            finding: Dictionary or Finding dataclass object
            field_name: Name of field to extract
            default: Default value if field not found

        Returns:
            Field value or default
        """
        if isinstance(finding, dict):
            return finding.get(field_name, default)
        else:
            # Assume it's a Finding dataclass
            return getattr(finding, field_name, default)

    def _find_similar_decisions(self, finding) -> List[tuple[ComplianceDecision, float]]:
        """Find decisions similar to the given finding.

        Returns list of (ComplianceDecision, similarity_score) tuples sorted by score.

        Args:
            finding: Dictionary or Finding object with rule_id, file_path, violation_text, project

        Returns:
            List of (decision, similarity_score) tuples
        """
        rule_id = self._get_field(finding, 'rule_id', '')
        file_path = self._get_field(finding, 'file_path', '')
        project = self._get_field(finding, 'project', '')
        
        # Query all decisions for this rule
        similar_decisions = []
        
        # Get decisions for this rule
        decisions = self.feedback_store.query_by_rule(rule_id, project=project, limit=100)
        
        for decision in decisions:
            similarity = self._compute_similarity(finding, decision)
            similar_decisions.append((decision, similarity))
        
        # Sort by similarity score descending
        similar_decisions.sort(key=lambda x: x[1], reverse=True)
        return similar_decisions

    def _compute_similarity(self, finding, decision: ComplianceDecision) -> float:
        """Compute similarity score between finding and decision.

        Scoring:
        - Exact rule_id match: 1.0
        - Same file path: 0.3
        - Same domain (first part of path): 0.5

        Returns maximum score from matching criteria.

        Args:
            finding: Dictionary or Finding object with rule_id, file_path
            decision: ComplianceDecision to compare

        Returns:
            Similarity score (0.0-1.0)
        """
        scores = []

        # Exact rule_id match
        if self._get_field(finding, 'rule_id') == decision.rule_id:
            scores.append(1.0)

        # Same file path
        if self._get_field(finding, 'file_path') == decision.file_path:
            scores.append(0.3)

        # Same domain (directory)
        finding_file = self._get_field(finding, 'file_path', '')
        decision_file = decision.file_path
        
        if finding_file and decision_file:
            finding_domain = finding_file.split('/')[0] if '/' in finding_file else finding_file
            decision_domain = decision_file.split('/')[0] if '/' in decision_file else decision_file
            
            if finding_domain and finding_domain == decision_domain:
                scores.append(0.5)
        
        # Return max score, or 0 if no matches
        return max(scores) if scores else 0.0

    def _generate_recommendation(self, decisions: List[ComplianceDecision]) -> str:
        """Generate a text recommendation from past decisions.
        
        Args:
            decisions: List of ComplianceDecision objects
            
        Returns:
            Formatted recommendation text
        """
        if not decisions:
            return "No previous decisions found. Manual review recommended."
        
        # Group by decision type
        decision_groups: Dict[str, List[ComplianceDecision]] = {}
        for decision in decisions:
            if decision.decision not in decision_groups:
                decision_groups[decision.decision] = []
            decision_groups[decision.decision].append(decision)
        
        # Build recommendation text
        lines = ["Previous reviewer decisions for this rule:"]
        
        for decision in decisions:
            timestamp = decision.timestamp[:10] if decision.timestamp else "unknown"
            reviewer = decision.reviewer or "unknown"
            constraint_note = f" (constraints: {decision.constraints})" if decision.constraints else ""
            
            # Extract just the filename for brevity
            file_display = decision.file_path.split('/')[-1] if '/' in decision.file_path else decision.file_path
            
            lines.append(f"- {decision.decision}: {file_display} (reviewer: @{reviewer}, {timestamp}){constraint_note}")
        
        # Add summary recommendation
        lines.append("")
        most_common_decision = max(decision_groups.keys(), key=lambda k: len(decision_groups[k]))
        lines.append(f"Recommendation: Based on {len(decisions)} similar decisions, consider {most_common_decision}.")
        
        return "\n".join(lines)

    def format_for_prompt(self, context: RAGContext) -> str:
        """Format RAGContext as text for LLM prompt injection.
        
        Args:
            context: RAGContext to format
            
        Returns:
            Formatted text to inject into LLM prompt
        """
        if not context.past_decisions:
            return ""
        
        lines = []
        lines.append("\n=== HUMAN-IN-THE-LOOP FEEDBACK (RAG Context) ===")
        lines.append(context.recommendation)
        
        if context.constraints:
            lines.append("\nApplicable Constraints:")
            for constraint in context.constraints:
                lines.append(f"  - {constraint}")
        
        lines.append("===============================================\n")
        
        return "\n".join(lines)

    def _apply_threshold(
        self,
        decisions: List[tuple[ComplianceDecision, float]],
        threshold: float = 0.3,
    ) -> List[ComplianceDecision]:
        """Filter decisions below similarity threshold.
        
        Args:
            decisions: List of (ComplianceDecision, score) tuples
            threshold: Minimum similarity threshold (0.0-1.0)
            
        Returns:
            List of ComplianceDecision objects above threshold
        """
        filtered = [decision for decision, score in decisions if score >= threshold]
        return filtered
