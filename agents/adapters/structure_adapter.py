"""Code structure and modularity validation adapter."""
import os
import re
from typing import Dict, List, Set, Optional, Tuple
from agents.adapters.base_adapter import BaseComplianceAdapter, AdapterResult

class StructureAdapter(BaseComplianceAdapter):
    """Adapter for analyzing code organization and modularity."""
    
    DOMAIN = "code_structure"
    
    def __init__(self, rules: dict, config: dict):
        """Initialize structure adapter.
        
        Args:
            rules: Configuration rules including structure settings
            config: Global configuration
        """
        super().__init__(rules, config)
        self.structure_rules = rules.get("structure", {})
    
    def analyze(self, file_cache: Dict[str, str], **kwargs) -> AdapterResult:
        """Analyze code structure and modularity.
        
        Args:
            file_cache: Dict of {file_path: file_content}
            **kwargs: Additional arguments (unused)
            
        Returns:
            AdapterResult with findings and score
        """
        findings = []
        error = None
        
        try:
            # Build module map
            module_map = self._build_module_map(file_cache)
            
            # Check cross-module includes
            for file_path, content in file_cache.items():
                if self._is_source_file(file_path):
                    findings.extend(
                        self._check_cross_module_includes(file_path, content, module_map)
                    )
            
            # Check API surface
            findings.extend(self._check_api_surface(file_cache))
            
            # Check misplaced files
            findings.extend(self._check_misplaced_files(file_cache))
            
            # Check build system references
            findings.extend(self._check_build_references(file_cache, module_map))
        
        except Exception as e:
            self.logger.error(f"Error analyzing code structure: {e}")
            error = str(e)
        
        score = self._compute_score(findings, len(file_cache))
        grade = self._compute_grade(score)
        
        return AdapterResult(
            score=score,
            grade=grade,
            domain=self.DOMAIN,
            findings=findings,
            summary={
                "files_analyzed": len(file_cache),
                "issues_found": len(findings),
                "modules_detected": len(set(self._get_module(p) for p in file_cache.keys())),
            },
            tool_available=True,
            tool_name="structure_analyzer"
        )
    
    def _build_module_map(self, file_cache: Dict[str, str]) -> Dict[str, Set[str]]:
        """Build a map of modules to their files.
        
        Args:
            file_cache: Dict of files
            
        Returns:
            Dict mapping module name to set of file paths
        """
        module_map = {}
        
        for file_path in file_cache.keys():
            module = self._get_module(file_path)
            if module not in module_map:
                module_map[module] = set()
            module_map[module].add(file_path)
        
        return module_map
    
    def _get_module(self, file_path: str) -> str:
        """Extract module name from file path.
        
        Args:
            file_path: Path to file
            
        Returns:
            Module name (top-level directory)
        """
        # Remove leading ./ or /
        clean_path = file_path.lstrip('./')
        parts = clean_path.split('/')
        
        # If file is in root, module is "root"
        if len(parts) == 1:
            return "root"
        
        # Module is first directory
        return parts[0]
    
    def _is_source_file(self, file_path: str) -> bool:
        """Check if file is a C source file.
        
        Args:
            file_path: Path to file
            
        Returns:
            True if source file
        """
        return file_path.endswith(('.c', '.cpp', '.cc', '.cxx'))
    
    def _check_cross_module_includes(
        self, file_path: str, content: str, module_map: Dict[str, Set[str]]
    ) -> List:
        """Detect cross-module include violations.
        
        Args:
            file_path: Path to file being analyzed
            content: File content
            module_map: Map of modules to files
            
        Returns:
            List of Finding objects
        """
        findings = []
        source_module = self._get_module(file_path)
        
        # Extract includes
        include_pattern = r'#include\s+[<"]([^>"]+)[>"]'
        includes = re.findall(include_pattern, content)
        
        for include in includes:
            include_module = self._get_module(include)
            
            # Check if cross-module
            if include_module != source_module and include_module != "root":
                # Check if this cross-module include is allowed
                allowed_modules = self.structure_rules.get("allowed_cross_module", [])
                
                is_allowed = (
                    include_module in allowed_modules or
                    f"{source_module}->{include_module}" in allowed_modules
                )
                
                if not is_allowed and self.structure_rules.get("enforce_module_boundaries", False):
                    finding = self._make_finding(
                        file_path=file_path,
                        line=1,
                        rule_id="structure:cross_module_include",
                        message=f"Cross-module include: {source_module} -> {include_module}",
                        severity="medium",
                        domain=self.DOMAIN,
                        suggested_fix="Use public API headers or refactor module boundaries"
                    )
                    findings.append(finding)
        
        return findings
    
    def _check_api_surface(self, file_cache: Dict[str, str]) -> List:
        """Check that non-static functions have header declarations.
        
        Args:
            file_cache: Dict of files
            
        Returns:
            List of Finding objects
        """
        findings = []
        
        # Build map of exported functions
        exported_functions = {}  # module -> set of function names
        
        for file_path, content in file_cache.items():
            if not file_path.endswith('.h'):
                continue
            
            module = self._get_module(file_path)
            if module not in exported_functions:
                exported_functions[module] = set()
            
            # Find function declarations
            # Simple pattern: type name(args);
            decl_pattern = r'^\s*\w+[\s\*]+(\w+)\s*\([^)]*\)\s*;'
            for line in content.split('\n'):
                match = re.match(decl_pattern, line)
                if match:
                    exported_functions[module].add(match.group(1))
        
        # Check source files for non-static functions
        for file_path, content in file_cache.items():
            if not self._is_source_file(file_path):
                continue
            
            module = self._get_module(file_path)
            
            # Find function definitions (simplified)
            func_pattern = r'^(?!static\s)\w+[\s\*]+(\w+)\s*\([^)]*\)\s*\{'
            for line_num, line in enumerate(content.split('\n'), 1):
                match = re.match(func_pattern, line)
                if match:
                    func_name = match.group(1)
                    
                    # Check if exported in header
                    if (module not in exported_functions or
                        func_name not in exported_functions[module]):
                        
                        if self.structure_rules.get("require_api_declarations", False):
                            finding = self._make_finding(
                                file_path=file_path,
                                line=line_num,
                                rule_id="structure:undeclared_api",
                                message=f"Non-static function {func_name} not declared in header",
                                severity="medium",
                                domain=self.DOMAIN,
                                suggested_fix="Either mark as static or add declaration to header file"
                            )
                            findings.append(finding)
        
        return findings
    
    def _check_misplaced_files(self, file_cache: Dict[str, str]) -> List:
        """Detect misplaced files (.c in include/, .h in src/ without match).
        
        Args:
            file_cache: Dict of files
            
        Returns:
            List of Finding objects
        """
        findings = []
        
        for file_path in file_cache.keys():
            # Check for .c files in include directories
            if '/include/' in file_path and file_path.endswith('.c'):
                finding = self._make_finding(
                    file_path=file_path,
                    line=1,
                    rule_id="structure:misplaced_source",
                    message="Source file (.c) found in include directory",
                    severity="high",
                    domain=self.DOMAIN,
                    suggested_fix="Move to src/ or appropriate source directory"
                )
                findings.append(finding)
            
            # Check for .h files in src without matching .c
            if '/src/' in file_path and file_path.endswith('.h'):
                # Check if there's a matching .c file
                expected_c = file_path.replace('.h', '.c')
                if expected_c not in file_cache:
                    # This might be internal, check if it's in a subdir
                    if '/internal/' not in file_path and '/private/' not in file_path:
                        finding = self._make_finding(
                            file_path=file_path,
                            line=1,
                            rule_id="structure:header_without_source",
                            message="Header file in src/ without matching source file",
                            severity="low",
                            domain=self.DOMAIN,
                            suggested_fix="Move to include/, or create matching .c file"
                        )
                        findings.append(finding)
        
        return findings
    
    def _check_build_references(self, file_cache: Dict[str, str], module_map: Dict[str, Set[str]]) -> List:
        """Check that source files are referenced in build system.
        
        Args:
            file_cache: Dict of files
            module_map: Map of modules to files
            
        Returns:
            List of Finding objects
        """
        findings = []
        
        # Find build files
        build_files = {
            'Makefile': None,
            'CMakeLists.txt': None,
            'kbuild': None,
            'Kconfig': None,
        }
        
        for file_path in file_cache.keys():
            for build_name in build_files.keys():
                if file_path.endswith(build_name):
                    build_files[build_name] = file_cache[file_path]
        
        if not any(build_files.values()):
            # No build files found
            return findings
        
        # Collect all referenced source files from build files
        referenced_sources = set()
        for build_content in build_files.values():
            if build_content:
                # Simple pattern: look for .c/.cpp files mentioned
                referenced_sources.update(re.findall(r'\b([a-zA-Z0-9_./+-]+\.c[px]{0,2})\b', build_content))
        
        # Check for orphaned source files
        for file_path in file_cache.keys():
            if self._is_source_file(file_path):
                # Check if referenced
                if file_path not in referenced_sources:
                    # Might be in a different format, do fuzzy check
                    basename = os.path.basename(file_path)
                    if not any(basename in ref for ref in referenced_sources):
                        if self.structure_rules.get("require_build_references", False):
                            finding = self._make_finding(
                                file_path=file_path,
                                line=1,
                                rule_id="structure:orphaned_source",
                                message="Source file not referenced in build system",
                                severity="medium",
                                domain=self.DOMAIN,
                                suggested_fix="Add to Makefile, CMakeLists.txt, or kbuild"
                            )
                            findings.append(finding)
        
        return findings
