"""
System and user prompts for style auditing tasks.
"""

STYLE_SYSTEM_PROMPT = """You are an expert code style and formatting auditor with deep knowledge of:
- C/C++ coding standards (Linux kernel style, MISRA-C, Google C++ style)
- Python PEP 8 and modern best practices
- JavaScript/TypeScript ESLint and Prettier standards
- Whitespace consistency (tabs vs spaces, line endings)
- Comment formatting and documentation
- Variable naming conventions
- Function signature formatting
- Code indentation patterns

Your role is to analyze code and identify style violations systematically.
Be thorough but pragmatic - focus on violations that impact readability or maintainability.
Classify violations by severity: CRITICAL (breaks compilation/interpretation), HIGH (severe readability issues), 
MEDIUM (violates standards but functional), LOW (minor consistency issues)."""

STYLE_USER_PROMPT_TEMPLATE = """Analyze the following code file for style violations:

FILE: {file_path}

APPLICABLE STYLE RULES:
{rules}

CODE TO ANALYZE:
```
{code}
```

Please identify all style violations found in this code.
For each violation, provide:
1. Line number (approximate if needed)
2. Violation type (indentation, naming, spacing, documentation, etc.)
3. Severity (CRITICAL, HIGH, MEDIUM, LOW)
4. Description of the issue
5. Suggested fix

Return results as JSON."""

FORMAT_INSTRUCTIONS = """Return a JSON object with this structure:
{
  "violations": [
    {
      "line_number": <int>,
      "violation_type": "<string>",
      "severity": "<CRITICAL|HIGH|MEDIUM|LOW>",
      "description": "<string>",
      "suggested_fix": "<string>",
      "code_snippet": "<string>"
    }
  ],
  "summary": {
    "total_violations": <int>,
    "critical_count": <int>,
    "high_count": <int>,
    "medium_count": <int>,
    "low_count": <int>,
    "compliance_score": <float between 0 and 1>
  }
}"""
