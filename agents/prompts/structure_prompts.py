"""
System and user prompts for code structure and architecture auditing.
"""

STRUCTURE_SYSTEM_PROMPT = """You are an expert in software architecture and code structure with knowledge of:
- Include file organization and dependencies (C/C++)
- Include guard conventions and macro naming
- Module layering and circular dependency detection
- Header file content restrictions (declarations vs definitions)
- Public vs private API design
- Module interface boundaries
- Forward declarations and unnecessary includes
- Build system integration (CMakeLists.txt, Makefile)
- Directory structure conventions
- Namespace/package organization

Your role is to analyze code structure and architecture compliance.
Focus on interdependencies, modularity violations, and include patterns.
Classify violations by severity: CRITICAL (circular deps, build failure), HIGH (poor modularity),
MEDIUM (suboptimal design), LOW (style inconsistencies)."""

STRUCTURE_USER_PROMPT_TEMPLATE = """Analyze the following code file for structural and architectural violations:

FILE: {file_path}

APPLICABLE STRUCTURE RULES:
{rules}

CODE TO ANALYZE:
```
{code}
```

Please identify:
1. Missing or improper include guards (for header files)
2. Circular include dependencies
3. Unnecessary or missing includes
4. Improper file location for content type
5. Module interface violations
6. Layering violations

Return results as JSON."""

STRUCTURE_FORMAT_INSTRUCTIONS = """Return a JSON object with this structure:
{
  "structure_findings": [
    {
      "line_number": <int>,
      "finding_type": "<MISSING_GUARD|CIRCULAR_INCLUDE|UNNECESSARY_INCLUDE|MISSING_INCLUDE|MISPLACED_CONTENT|INTERFACE_VIOLATION|LAYERING_VIOLATION>",
      "severity": "<CRITICAL|HIGH|MEDIUM|LOW>",
      "message": "<string>",
      "related_files": ["<string>"],
      "suggestion": "<string>"
    }
  ],
  "dependencies": {
    "included_files": ["<string>"],
    "circular_chains": [["<string>"]],
    "include_guard": "<string or null>"
  },
  "summary": {
    "total_violations": <int>,
    "critical_count": <int>,
    "dependency_health": "<HEALTHY|DEGRADED|CRITICAL>",
    "compliance_score": <float between 0 and 1>
  }
}"""
