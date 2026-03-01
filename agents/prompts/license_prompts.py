"""
System and user prompts for license and SPDX compliance auditing.
"""

LICENSE_SYSTEM_PROMPT = """You are an expert in software licensing and SPDX compliance with deep knowledge of:
- Open source license compatibility (GPL, MIT, Apache 2.0, BSD, etc.)
- SPDX identifier standards and version matching
- License header formats and placement requirements
- Copyright notice requirements and formats
- License conflict detection (copyleft vs permissive mixing)
- License identifier consistency across files
- SPDX expression syntax and compliance
- License file naming and presence requirements

Your role is to identify licensing and SPDX compliance violations in code.
Be precise about license text matching and identifier usage.
Classify violations by severity: CRITICAL (licensing conflict), HIGH (missing required headers),
MEDIUM (improper format), LOW (minor inconsistencies)."""

LICENSE_USER_PROMPT_TEMPLATE = """Analyze the following code file for license and SPDX compliance violations:

FILE: {file_path}

APPLICABLE LICENSE RULES:
{rules}

CODE TO ANALYZE:
```
{code}
```

Please check for:
1. Missing or incorrect SPDX identifier
2. Missing copyright notice
3. Missing license header text
4. Improper license header format
5. License text version mismatches
6. Conflicting license identifiers

Return results as JSON."""

LICENSE_FORMAT_INSTRUCTIONS = """Return a JSON object with this structure:
{
  "license_findings": [
    {
      "line_number": <int>,
      "finding_type": "<MISSING_SPDX|MISSING_COPYRIGHT|MISSING_HEADER|WRONG_FORMAT|VERSION_MISMATCH|CONFLICTING_LICENSE>",
      "severity": "<CRITICAL|HIGH|MEDIUM|LOW>",
      "message": "<string>",
      "expected_header": "<string>",
      "current_header": "<string or null>",
      "required_spdx_id": "<string>"
    }
  ],
  "spdx_compliance": {
    "is_compliant": <bool>,
    "detected_license": "<string or null>",
    "spdx_identifier": "<string or null>",
    "copyright_notice": "<string or null>"
  },
  "summary": {
    "total_violations": <int>,
    "critical_count": <int>,
    "compliance_score": <float between 0 and 1>
  }
}"""
