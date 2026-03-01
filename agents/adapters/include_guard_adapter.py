"""Include guard validation adapter for C/C++ headers."""
import re
from typing import Dict, List, Optional, Tuple
from agents.adapters.base_adapter import BaseComplianceAdapter, AdapterResult

class IncludeGuardAdapter(BaseComplianceAdapter):
    """Adapter for validating C/C++ header include guards."""
    
    DOMAIN = "code_structure"
    
    def __init__(self, rules: dict, config: dict):
        """Initialize include guard adapter.
        
        Args:
            rules: Configuration rules including structure settings
            config: Global configuration
        """
        super().__init__(rules, config)
        # Get naming convention from rules
        self.naming_convention = (
            rules.get("structure", {}).get("include_guard_convention", "path_based")
        )
    
    def analyze(self, file_cache: Dict[str, str], **kwargs) -> AdapterResult:
        """Analyze header files for proper include guards.
        
        Args:
            file_cache: Dict of {file_path: file_content}
            **kwargs: Additional arguments (unused)
            
        Returns:
            AdapterResult with findings and score
        """
        findings = []
        header_files = 0
        
        try:
            for file_path, content in file_cache.items():
                # Only check header files
                if not self._is_header_file(file_path):
                    continue
                
                header_files += 1
                findings.extend(self._check_header_file(file_path, content))
        
        except Exception as e:
            self.logger.error(f"Error analyzing include guards: {e}")
        
        score = self._compute_score(findings, max(header_files, 1))
        grade = self._compute_grade(score)
        
        return AdapterResult(
            score=score,
            grade=grade,
            domain=self.DOMAIN,
            findings=findings,
            summary={
                "headers_checked": header_files,
                "issues_found": len(findings),
                "convention": self.naming_convention,
            },
            tool_available=True,
            tool_name="include_guard_checker"
        )
    
    def _is_header_file(self, file_path: str) -> bool:
        """Check if file is a C/C++ header.
        
        Args:
            file_path: Path to file
            
        Returns:
            True if header file
        """
        return file_path.endswith(('.h', '.hpp', '.hxx', '.h++', '.hh'))
    
    def _check_header_file(self, file_path: str, content: str) -> List:
        """Validate include guard in header file.
        
        Args:
            file_path: Path to header file
            content: File content
            
        Returns:
            List of Finding objects
        """
        findings = []
        lines = content.split('\n')
        
        # Look for #pragma once OR #ifndef guard pattern
        has_pragma_once = any('pragma once' in line for line in lines[:10])
        
        guard_info = self._find_include_guard(lines)
        
        if has_pragma_once:
            # pragma once is acceptable
            self.logger.debug(f"{file_path}: Uses #pragma once")
            return findings
        
        if not guard_info:
            # No include guard found
            finding = self._make_finding(
                file_path=file_path,
                line=1,
                rule_id="guard:missing",
                message="Header file missing include guard (#ifndef/#define or #pragma once)",
                severity="high",
                domain=self.DOMAIN,
                suggested_fix=self._generate_guard_suggestion(file_path)
            )
            findings.append(finding)
            return findings
        
        ifndef_line, ifndef_guard, define_line, define_guard, endif_line = guard_info
        
        # Check guard names match
        if ifndef_guard != define_guard:
            finding = self._make_finding(
                file_path=file_path,
                line=ifndef_line,
                rule_id="guard:mismatch",
                message=f"Include guard mismatch: #ifndef {ifndef_guard} but #define {define_guard}",
                severity="high",
                domain=self.DOMAIN,
                suggested_fix=f"Ensure both #ifndef and #define use the same guard name"
            )
            findings.append(finding)
        
        # Check naming convention
        expected_guard = self._compute_expected_guard(file_path)
        if ifndef_guard != expected_guard:
            finding = self._make_finding(
                file_path=file_path,
                line=ifndef_line,
                rule_id="guard:naming",
                message=f"Include guard naming mismatch: {ifndef_guard} should be {expected_guard}",
                severity="medium",
                domain=self.DOMAIN,
                suggested_fix=f"Rename guard to follow {self.naming_convention} convention: {expected_guard}"
            )
            findings.append(finding)
        
        return findings
    
    def _find_include_guard(self, lines: List[str]) -> Optional[Tuple[int, str, int, str, int]]:
        """Find #ifndef/#define include guard pattern.
        
        Args:
            lines: List of file lines
            
        Returns:
            Tuple of (ifndef_line, ifndef_guard, define_line, define_guard, endif_line) or None
        """
        ifndef_match = None
        define_match = None
        endif_match = None
        
        # Find #ifndef in first 20 lines
        for i, line in enumerate(lines[:20]):
            if re.match(r'^\s*#ifndef\s+(\w+)', line):
                ifndef_match = (i, re.match(r'^\s*#ifndef\s+(\w+)', line).group(1))
                break
        
        if not ifndef_match:
            return None
        
        # Find corresponding #define
        ifndef_line, ifndef_guard = ifndef_match
        for i in range(ifndef_line + 1, min(ifndef_line + 5, len(lines))):
            line = lines[i]
            if re.match(r'^\s*#define\s+(\w+)', line):
                define_match = (i, re.match(r'^\s*#define\s+(\w+)', line).group(1))
                break
        
        if not define_match:
            return None
        
        # Find #endif (should be last non-empty line typically)
        define_line, define_guard = define_match
        for i in range(len(lines) - 1, max(len(lines) - 10, -1), -1):
            if re.match(r'^\s*#endif', lines[i]):
                endif_match = i
                break
        
        if endif_match is None:
            return None
        
        return (ifndef_line, ifndef_guard, define_line, define_guard, endif_match)
    
    def _compute_expected_guard(self, file_path: str) -> str:
        """Compute expected guard name based on convention.
        
        Args:
            file_path: Path to header file
            
        Returns:
            Expected guard name
        """
        if self.naming_convention == "filename_based":
            # Use filename only: myheader.h -> MYHEADER_H
            import os
            basename = os.path.basename(file_path)
            name = os.path.splitext(basename)[0]
            ext = basename.split('.')[-1]
            return f"{name.upper()}_{ext.upper()}"
        else:
            # path_based: full path converted to guard
            # include/mymodule/header.h -> INCLUDE_MYMODULE_HEADER_H
            guard = file_path.replace('/', '_').replace('.', '_').upper()
            # Remove leading underscores
            guard = guard.lstrip('_')
            return guard
    
    def _generate_guard_suggestion(self, file_path: str) -> str:
        """Generate sample include guard code.
        
        Args:
            file_path: Path to header file
            
        Returns:
            Suggested code snippet
        """
        guard = self._compute_expected_guard(file_path)
        suggestion = f"""Add to file start:
#ifndef {guard}
#define {guard}

... header content ...

#endif  /* {guard} */

OR use:
#pragma once"""
        return suggestion
