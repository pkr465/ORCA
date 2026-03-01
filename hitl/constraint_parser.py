"""Parse markdown constraint files for automated decision support."""
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConstraintRule:
    """Represents a constraint rule for a compliance rule."""
    rule_id: str = ""
    conditions: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    scope: str = ""


class ConstraintParser:
    """Parse markdown constraint files to guide compliance decisions."""

    def __init__(self):
        """Initialize constraint parser."""
        self.constraints: Dict[str, List[ConstraintRule]] = {}

    def parse_file(self, file_path: str) -> Dict[str, List[ConstraintRule]]:
        """Parse constraint definitions from a markdown file.
        
        Args:
            file_path: Path to markdown constraint file
            
        Returns:
            Dictionary mapping rule_id to list of ConstraintRule objects
        """
        constraint_file = Path(file_path)
        
        if not constraint_file.exists():
            logger.warning(f"Constraint file not found: {file_path}")
            return {}
        
        with open(constraint_file, 'r') as f:
            content = f.read()
        
        return self.parse_text(content)

    def parse_text(self, content: str) -> Dict[str, List[ConstraintRule]]:
        """Parse constraint definitions from markdown text.
        
        Expected format:
        # Constraints for rule_id
        ## Conditions
        - Condition 1
        - Condition 2
        ## Actions
        - ACTION: Description
        - ACTION: Description
        
        Args:
            content: Markdown content to parse
            
        Returns:
            Dictionary mapping rule_id to list of ConstraintRule objects
        """
        self.constraints = {}
        
        lines = content.split('\n')
        current_rule_id = None
        current_section = None
        current_lines = []
        current_constraint = None
        
        for line in lines:
            # Check for main header (# Constraints for rule_id)
            main_match = re.match(r'^# Constraints for (\S+)', line)
            if main_match:
                # Save previous constraint if exists
                if current_constraint is not None and current_section and current_lines:
                    self._add_section_to_constraint(current_constraint, current_section, current_lines)
                
                # Create new constraint
                current_rule_id = main_match.group(1)
                current_constraint = ConstraintRule(rule_id=current_rule_id)
                
                # Add to constraints dict
                if current_rule_id not in self.constraints:
                    self.constraints[current_rule_id] = []
                self.constraints[current_rule_id].append(current_constraint)
                
                current_section = None
                current_lines = []
                continue
            
            # Check for subsection header (## Conditions or ## Actions)
            section_match = re.match(r'^## (\w+)', line)
            if section_match:
                # Save previous section
                if current_constraint is not None and current_section and current_lines:
                    self._add_section_to_constraint(current_constraint, current_section, current_lines)
                
                current_section = section_match.group(1).lower()
                current_lines = []
                continue
            
            # Accumulate lines for current section
            if current_constraint is not None and current_section:
                if line.strip() and not line.startswith('#'):
                    current_lines.append(line.strip())
        
        # Process final section
        if current_constraint is not None and current_section and current_lines:
            self._add_section_to_constraint(current_constraint, current_section, current_lines)
        
        logger.info(f"Parsed constraints for {len(self.constraints)} rules")
        return self.constraints

    def _add_section_to_constraint(self, constraint: ConstraintRule, section: str, lines: List[str]) -> None:
        """Add a section to a constraint rule.
        
        Args:
            constraint: ConstraintRule to add to
            section: Section name ('conditions' or 'actions')
            lines: List of content lines
        """
        # Parse items (lines starting with -)
        items = [line[1:].strip() for line in lines if line.startswith('-')]
        
        if section == 'conditions':
            constraint.conditions.extend(items)
        elif section == 'actions':
            constraint.actions.extend(items)

    def get_constraints_for_rule(self, rule_id: str) -> List[ConstraintRule]:
        """Get constraints for a specific rule.
        
        Args:
            rule_id: Rule identifier
            
        Returns:
            List of ConstraintRule objects for the rule
        """
        return self.constraints.get(rule_id, [])

    def evaluate_constraints(
        self,
        finding: Dict,
        constraints: Optional[List[ConstraintRule]] = None,
    ) -> Optional[str]:
        """Evaluate constraints against a finding.
        
        Args:
            finding: Dictionary with rule_id, file_path, violation_text, etc.
            constraints: Optional list of ConstraintRule. If None, queries from rule_id.
            
        Returns:
            Recommended action (e.g., 'WAIVE', 'SKIP') or None if no match
        """
        rule_id = finding.get('rule_id', '')
        file_path = finding.get('file_path', '')
        
        # Get constraints if not provided
        if constraints is None:
            constraints = self.get_constraints_for_rule(rule_id)
        
        # Evaluate each constraint rule
        for constraint_rule in constraints:
            # Check if all conditions match
            all_conditions_match = True
            for condition in constraint_rule.conditions:
                if not self._matches_condition(finding, condition):
                    all_conditions_match = False
                    break
            
            # If all conditions match, return first action
            if all_conditions_match and constraint_rule.actions:
                # Parse first action (format: "ACTION: description")
                action_str = constraint_rule.actions[0]
                match = re.match(r'(\w+):\s*(.*)', action_str)
                if match:
                    action = match.group(1)
                    logger.info(f"Constraint matched for {rule_id}: {action}")
                    return action
        
        return None

    def _matches_condition(self, finding: Dict, condition: str) -> bool:
        """Check if finding matches a condition.
        
        Supports conditions like:
        - "File matches vendor/*"
        - "File is auto-generated"
        - "File is a test fixture"
        - "Project is internal"
        
        Args:
            finding: Finding dictionary
            condition: Condition string to evaluate
            
        Returns:
            True if condition matches, False otherwise
        """
        file_path = finding.get('file_path', '').lower()
        violation_text = finding.get('violation_text', '').lower()
        
        # Pattern: "File matches <pattern>"
        file_pattern_match = re.match(r'File matches (\S+)', condition, re.IGNORECASE)
        if file_pattern_match:
            pattern = file_pattern_match.group(1)
            # Convert glob pattern to regex
            regex_pattern = pattern.replace('*', '.*').replace('?', '.')
            match_result = re.match(f"^{regex_pattern}", file_path) is not None
            logger.debug(f"Pattern match '{pattern}' against '{file_path}': {match_result}")
            return match_result
        
        # Pattern: "File is <characteristic>" with optional "a" or "an"
        file_char_match = re.match(r'File is (?:a |an )?(.+)', condition, re.IGNORECASE)
        if file_char_match:
            characteristic = file_char_match.group(1).lower().strip()
            
            # Check for auto-generated
            if 'auto-generated' in characteristic or 'autogenerated' in characteristic:
                auto_gen_indicators = ['auto-generated', 'autogenerated', 'do not edit', 'generated by']
                result = any(indicator in violation_text for indicator in auto_gen_indicators)
                logger.debug(f"Auto-generated check: {result}")
                return result
            
            # Check for test fixtures
            if 'test' in characteristic and 'fixture' in characteristic:
                test_indicators = ['test/', '/test/', '_test', 'fixture', 'mock']
                result = any(indicator in file_path for indicator in test_indicators)
                logger.debug(f"Test fixture check: {result}")
                return result
            
            # Check for vendor code
            if 'vendor' in characteristic:
                result = 'vendor' in file_path or 'third_party' in file_path
                logger.debug(f"Vendor code check: {result}")
                return result
        
        # Pattern: "Project is <name>"
        project_match = re.match(r'Project is (.+)', condition, re.IGNORECASE)
        if project_match:
            expected_project = project_match.group(1).lower()
            actual_project = finding.get('project', '').lower()
            result = expected_project in actual_project
            logger.debug(f"Project match '{expected_project}' in '{actual_project}': {result}")
            return result
        
        # Pattern: "Violation contains <text>"
        violation_match = re.match(r'Violation contains (.+)', condition, re.IGNORECASE)
        if violation_match:
            expected_text = violation_match.group(1).lower()
            result = expected_text in violation_text
            logger.debug(f"Violation contains '{expected_text}': {result}")
            return result
        
        # Default: no match
        logger.debug(f"No pattern matched for condition: {condition}")
        return False
