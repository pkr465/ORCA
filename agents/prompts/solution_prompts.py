"""
System and user prompts for fix recommendation and remediation suggestions.
"""

SOLUTION_SYSTEM_PROMPT = """You are an expert in code remediation and fix recommendation with knowledge of:
- Root cause analysis of compliance violations
- Code refactoring techniques
- Fix categorization (simple replacement, structural refactoring, new code addition)
- Minimal-change remediation strategies
- Trade-offs between different fixes
- Confidence assessment of proposed solutions
- Alternative solution generation
- Automated vs manual fix assessment

Your role is to analyze compliance findings and recommend specific, actionable fixes.
Provide high-confidence solutions with clear before/after examples.
Assess confidence based on fix complexity and potential side effects.
Support both automated fixes (HIGH confidence) and manual guidance (MEDIUM/LOW confidence)."""

SOLUTION_USER_PROMPT_TEMPLATE = """Generate a fix recommendation for this compliance finding:

FINDING:
{finding}

CODE CONTEXT (surrounding code):
{code_context}

APPLICABLE RULES:
{rules}

HUMAN-IN-THE-LOOP CONTEXT (previous similar decisions):
{hitl_context}

Please provide:
1. Root cause analysis
2. Recommended fix type (SIMPLE_REPLACEMENT, ADD_CODE, REMOVE_CODE, REFACTOR, STRUCTURAL)
3. Exact old code snippet (what to replace)
4. Exact new code snippet (what to replace with)
5. Confidence in this solution (0.0-1.0)
6. Alternative solutions if applicable
7. Potential side effects or risks

Return as JSON."""

SOLUTION_FORMAT_INSTRUCTIONS = """Return a JSON object with this structure:
{
  "root_cause": "<string>",
  "fix_type": "<SIMPLE_REPLACEMENT|ADD_CODE|REMOVE_CODE|REFACTOR|STRUCTURAL|REQUIRES_MANUAL_REVIEW>",
  "old_code": "<exact string to replace, or null if adding>",
  "new_code": "<exact replacement string>",
  "line_start": <int>,
  "line_end": <int>,
  "confidence": <float between 0.0 and 1.0>,
  "confidence_level": "<HIGH|MEDIUM|LOW>",
  "explanation": "<string>",
  "alternative_solutions": [
    {
      "description": "<string>",
      "old_code": "<string>",
      "new_code": "<string>",
      "confidence": <float>
    }
  ],
  "side_effects": [
    {
      "area": "<string>",
      "description": "<string>",
      "severity": "<LOW|MEDIUM|HIGH>"
    }
  ],
  "requires_manual_review": <bool>,
  "review_notes": "<string>"
}"""
