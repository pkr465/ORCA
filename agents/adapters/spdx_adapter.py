"""SPDX license compliance adapter."""
import subprocess
import os
import re
from typing import Dict, List, Optional, Set, Tuple
from agents.adapters.base_adapter import BaseComplianceAdapter, AdapterResult

class SPDXAdapter(BaseComplianceAdapter):
    """Adapter for SPDX license compliance checking."""
    
    DOMAIN = "license_compliance"
    
    # Comprehensive SPDX license database (50+ entries)
    SPDX_LICENSES = {
        "Apache-2.0": "Apache License 2.0",
        "MIT": "MIT License",
        "GPL-2.0": "GNU General Public License v2",
        "GPL-2.0-only": "GNU General Public License v2 (no later versions)",
        "GPL-2.0-or-later": "GNU General Public License v2 or later",
        "GPL-3.0": "GNU General Public License v3",
        "GPL-3.0-only": "GNU General Public License v3 (no later versions)",
        "GPL-3.0-or-later": "GNU General Public License v3 or later",
        "LGPL-2.0": "GNU Lesser General Public License v2",
        "LGPL-2.0-only": "GNU Lesser General Public License v2 (no later versions)",
        "LGPL-2.0-or-later": "GNU Lesser General Public License v2 or later",
        "LGPL-2.1": "GNU Lesser General Public License v2.1",
        "LGPL-2.1-only": "GNU Lesser General Public License v2.1 (no later versions)",
        "LGPL-2.1-or-later": "GNU Lesser General Public License v2.1 or later",
        "LGPL-3.0": "GNU Lesser General Public License v3",
        "LGPL-3.0-only": "GNU Lesser General Public License v3 (no later versions)",
        "LGPL-3.0-or-later": "GNU Lesser General Public License v3 or later",
        "BSD-2-Clause": "BSD 2-Clause License",
        "BSD-3-Clause": "BSD 3-Clause License",
        "BSD-4-Clause": "BSD 4-Clause License",
        "BSL-1.0": "Boost Software License 1.0",
        "MPL-2.0": "Mozilla Public License 2.0",
        "CDDL-1.0": "Common Development and Distribution License 1.0",
        "CDDL-1.1": "Common Development and Distribution License 1.1",
        "ISC": "ISC License",
        "Unlicense": "The Unlicense",
        "CC0-1.0": "Creative Commons Zero v1.0 Universal",
        "EPL-1.0": "Eclipse Public License 1.0",
        "EPL-2.0": "Eclipse Public License 2.0",
        "AGPL-3.0": "GNU Affero General Public License v3",
        "AGPL-3.0-only": "GNU Affero General Public License v3 (no later versions)",
        "AGPL-3.0-or-later": "GNU Affero General Public License v3 or later",
        "EUPL-1.2": "European Union Public Licence 1.2",
        "GFDL-1.1": "GNU Free Documentation License v1.1",
        "GFDL-1.2": "GNU Free Documentation License v1.2",
        "GFDL-1.3": "GNU Free Documentation License v1.3",
        "Zlib": "zlib License",
        "Artistic-2.0": "Artistic License 2.0",
        "0BSD": "BSD Zero Clause License",
        "NetCDF": "NetCDF License",
        "ODbL-1.0": "Open Data Commons Open Database License v1.0",
        "OGL-UK-1.0": "Open Government Licence v1.0",
        "OGL-UK-2.0": "Open Government Licence v2.0",
        "OGL-UK-3.0": "Open Government Licence v3.0",
        "Unlicense": "The Unlicense",
        "Proprietary": "Proprietary License",
    }
    
    # Deprecated SPDX identifiers that should not be used
    DEPRECATED_LICENSES = {
        "GPL-2.0": "Use GPL-2.0-only or GPL-2.0-or-later instead",
        "GPL-3.0": "Use GPL-3.0-only or GPL-3.0-or-later instead",
        "LGPL-2.0": "Use LGPL-2.0-only or LGPL-2.0-or-later instead",
        "LGPL-2.1": "Use LGPL-2.1-only or LGPL-2.1-or-later instead",
        "LGPL-3.0": "Use LGPL-3.0-only or LGPL-3.0-or-later instead",
        "AGPL-3.0": "Use AGPL-3.0-only or AGPL-3.0-or-later instead",
    }
    
    def __init__(self, rules: dict, config: dict):
        """Initialize SPDX adapter.
        
        Args:
            rules: Configuration rules including license settings
            config: Global configuration
        """
        super().__init__(rules, config)
        self.reuse_available = self._check_reuse_available()
    
    def _check_reuse_available(self) -> bool:
        """Check if 'reuse' CLI tool is available."""
        try:
            result = subprocess.run(
                ["reuse", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            available = result.returncode == 0
            self.logger.info(f"REUSE tool available: {available}")
            return available
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self.logger.debug("REUSE tool not available")
            return False
    
    def analyze(self, file_cache: Dict[str, str], **kwargs) -> AdapterResult:
        """Analyze files for SPDX license compliance.
        
        Args:
            file_cache: Dict of {file_path: file_content}
            **kwargs: Additional arguments (unused)
            
        Returns:
            AdapterResult with findings and score
        """
        findings = []
        error = None
        
        try:
            # Try REUSE lint first if available
            if self.reuse_available:
                findings.extend(self._run_reuse_lint(file_cache))
            else:
                # Fall back to built-in checks
                findings.extend(self._check_files_builtin(file_cache))
            
            # Check LICENSES/ directory and .reuse/dep5
            findings.extend(self._check_license_files(file_cache))
            findings.extend(self._check_reuse_dep5(file_cache))
        
        except Exception as e:
            self.logger.error(f"Error analyzing SPDX compliance: {e}")
            error = str(e)
        
        score = self._compute_score(findings, len(file_cache))
        grade = self._compute_grade(score)
        
        return AdapterResult(
            score=score,
            grade=grade,
            domain=self.DOMAIN,
            findings=findings,
            summary={
                "files_checked": len(file_cache),
                "issues_found": len(findings),
                "reuse_available": self.reuse_available,
                "critical": len([f for f in findings if f.severity == "critical"]),
                "high": len([f for f in findings if f.severity == "high"]),
            },
            tool_available=True,
            tool_name="SPDX/REUSE",
            error=error
        )
    
    def _run_reuse_lint(self, file_cache: Dict[str, str]) -> List:
        """Run 'reuse lint' command.
        
        Args:
            file_cache: Dict of files to check
            
        Returns:
            List of Finding objects
        """
        findings = []
        
        try:
            result = subprocess.run(
                ["reuse", "lint"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=os.getcwd()
            )
            
            # Parse reuse lint output
            for line in result.stdout.split('\n'):
                if 'is missing' in line.lower() or 'not a valid spdx' in line.lower():
                    # Example: "file.c is missing licensing information"
                    match = re.match(r'([^\s]+)\s+is\s+(.+?)(?:\s|$)', line)
                    if match:
                        file_path = match.group(1)
                        issue = match.group(2)
                        
                        finding = self._make_finding(
                            file_path=file_path,
                            line=1,
                            rule_id="reuse:missing_license",
                            message=f"Missing license information: {issue}",
                            severity="high",
                            domain=self.DOMAIN,
                            suggested_fix="Add SPDX-License-Identifier header or update .reuse/dep5"
                        )
                        findings.append(finding)
        
        except subprocess.TimeoutExpired:
            self.logger.warning("REUSE lint timeout")
        except Exception as e:
            self.logger.error(f"Error running reuse lint: {e}")
        
        return findings
    
    def _check_files_builtin(self, file_cache: Dict[str, str]) -> List:
        """Built-in SPDX header validation.
        
        Args:
            file_cache: Dict of files to check
            
        Returns:
            List of Finding objects
        """
        findings = []
        
        # Skip certain file types
        skip_extensions = {'.md', '.txt', '.json', '.yaml', '.yml', '.xml', '.svg'}
        
        for file_path, content in file_cache.items():
            # Check file extension
            if any(file_path.endswith(ext) for ext in skip_extensions):
                continue
            
            # Skip binary files
            if self._is_binary(content):
                continue
            
            lines = content.split('\n')
            spdx_header = self._find_spdx_header(lines)
            
            if not spdx_header:
                finding = self._make_finding(
                    file_path=file_path,
                    line=1,
                    rule_id="spdx:missing_header",
                    message="Missing SPDX-License-Identifier header",
                    severity="high",
                    domain=self.DOMAIN,
                    suggested_fix="Add '// SPDX-License-Identifier: <license>' to file header"
                )
                findings.append(finding)
            else:
                # Validate the SPDX expression
                spdx_id = spdx_header.split("SPDX-License-Identifier:", 1)[1].strip()
                header_findings = self._validate_spdx_expression(file_path, spdx_id)
                findings.extend(header_findings)
        
        return findings
    
    def _find_spdx_header(self, lines: List[str]) -> Optional[str]:
        """Find SPDX-License-Identifier in file header.
        
        Args:
            lines: List of file lines
            
        Returns:
            SPDX header line or None
        """
        # Check first 10 lines for SPDX header
        for line in lines[:10]:
            if "SPDX-License-Identifier:" in line:
                return line
        return None
    
    def _validate_spdx_expression(self, file_path: str, spdx_expr: str) -> List:
        """Validate SPDX expression (may contain AND/OR operators).
        
        Args:
            file_path: Path to file
            spdx_expr: SPDX expression to validate
            
        Returns:
            List of Finding objects if invalid
        """
        findings = []
        
        # Parse expression with AND/OR
        # Simple parser: split by AND/OR and validate each license
        tokens = re.split(r'\s+(AND|OR)\s+', spdx_expr)
        licenses = [t.strip() for t in tokens if t not in ('AND', 'OR')]
        
        for lic in licenses:
            # Remove parentheses if present
            lic_clean = lic.strip('()')
            
            if lic_clean not in self.SPDX_LICENSES:
                finding = self._make_finding(
                    file_path=file_path,
                    line=1,
                    rule_id="spdx:invalid_license",
                    message=f"Invalid SPDX license identifier: {lic_clean}",
                    severity="high",
                    domain=self.DOMAIN,
                    suggested_fix=f"Use valid SPDX identifier from https://spdx.org/licenses/"
                )
                findings.append(finding)
            else:
                # Check if deprecated
                deprecated_msg = self._check_deprecated_ids(lic_clean)
                if deprecated_msg:
                    finding = self._make_finding(
                        file_path=file_path,
                        line=1,
                        rule_id="spdx:deprecated_license",
                        message=f"Deprecated SPDX identifier: {lic_clean}. {deprecated_msg}",
                        severity="medium",
                        domain=self.DOMAIN,
                        suggested_fix=deprecated_msg
                    )
                    findings.append(finding)
        
        return findings
    
    def _check_deprecated_ids(self, spdx_id: str) -> Optional[str]:
        """Check if SPDX identifier is deprecated.
        
        Args:
            spdx_id: SPDX license identifier
            
        Returns:
            Deprecation message or None
        """
        return self.DEPRECATED_LICENSES.get(spdx_id)
    
    def _check_license_files(self, file_cache: Dict[str, str]) -> List:
        """Check if LICENSES/ directory exists and contains referenced licenses.
        
        Args:
            file_cache: Dict of files to check
            
        Returns:
            List of Finding objects
        """
        findings = []
        
        # Collect all referenced licenses
        referenced_licenses = set()
        for content in file_cache.values():
            for line in content.split('\n')[:10]:
                if "SPDX-License-Identifier:" in line:
                    spdx_expr = line.split("SPDX-License-Identifier:", 1)[1].strip()
                    tokens = re.split(r'\s+(AND|OR)\s+', spdx_expr)
                    for token in tokens:
                        if token not in ('AND', 'OR'):
                            lic = token.strip('()')
                            if lic in self.SPDX_LICENSES:
                                referenced_licenses.add(lic)
        
        # Check if LICENSES directory exists
        licenses_dir = os.path.join(os.getcwd(), "LICENSES")
        if referenced_licenses:
            if not os.path.isdir(licenses_dir):
                finding = self._make_finding(
                    file_path="LICENSES/",
                    line=1,
                    rule_id="spdx:missing_licenses_dir",
                    message="LICENSES/ directory not found but licenses are referenced",
                    severity="medium",
                    domain=self.DOMAIN,
                    suggested_fix="Create LICENSES/ directory with license text files for all referenced licenses"
                )
                findings.append(finding)
            else:
                # Check each referenced license has a file
                for lic in referenced_licenses:
                    # Common filename patterns: MIT, MIT.txt, GPL-2.0, GPL-2.0.txt
                    candidates = [
                        os.path.join(licenses_dir, lic),
                        os.path.join(licenses_dir, f"{lic}.txt"),
                        os.path.join(licenses_dir, f"{lic}.md"),
                    ]
                    if not any(os.path.isfile(c) for c in candidates):
                        finding = self._make_finding(
                            file_path=f"LICENSES/{lic}",
                            line=1,
                            rule_id="spdx:missing_license_file",
                            message=f"License file missing for {lic}",
                            severity="medium",
                            domain=self.DOMAIN,
                            suggested_fix=f"Add {lic} license text to LICENSES/{lic}"
                        )
                        findings.append(finding)
        
        return findings
    
    def _check_reuse_dep5(self, file_cache: Dict[str, str]) -> List:
        """Check .reuse/dep5 file if REUSE compliance is required.
        
        Args:
            file_cache: Dict of files to check
            
        Returns:
            List of Finding objects
        """
        findings = []
        
        # Look for .reuse/dep5 file
        dep5_path = os.path.join(os.getcwd(), ".reuse", "dep5")
        if os.path.isfile(dep5_path):
            with open(dep5_path, 'r') as f:
                dep5_content = f.read()
            
            # Validate DEP5 format: should have Format:, Files:, License:, Copyright:
            if not re.search(r'^Format:\s*', dep5_content, re.MULTILINE):
                finding = self._make_finding(
                    file_path=".reuse/dep5",
                    line=1,
                    rule_id="dep5:invalid_format",
                    message="Invalid DEP5 format: missing Format field",
                    severity="medium",
                    domain=self.DOMAIN,
                    suggested_fix="See https://www.kernel.org/doc/html/latest/process/applying-patches.html#common-tasks"
                )
                findings.append(finding)
            
            # Check for license references in DEP5
            licenses = re.findall(r'License:\s*(.+)', dep5_content)
            for lic in licenses:
                if lic.strip() and lic.strip() not in self.SPDX_LICENSES:
                    finding = self._make_finding(
                        file_path=".reuse/dep5",
                        line=1,
                        rule_id="dep5:invalid_license",
                        message=f"Invalid SPDX license in DEP5: {lic}",
                        severity="medium",
                        domain=self.DOMAIN,
                        suggested_fix="Use valid SPDX identifier"
                    )
                    findings.append(finding)
        
        return findings
    
    def _is_binary(self, content: str) -> bool:
        """Check if content appears to be binary.
        
        Args:
            content: File content
            
        Returns:
            True if likely binary
        """
        try:
            content.encode('utf-8')
            return '\x00' in content
        except (UnicodeDecodeError, AttributeError):
            return True
