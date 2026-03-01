"""File utilities for ORCA code analysis."""

import os
import fnmatch
from pathlib import Path
from typing import List, Set, Optional


C_EXTENSIONS = {'.c', '.h', '.cc', '.cpp', '.hpp', '.hh', '.cxx', '.hxx'}


def is_c_file(path: str) -> bool:
    """
    Check if a file has a C/C++ extension.
    
    Args:
        path: File path to check
        
    Returns:
        True if file has a C/C++ extension, False otherwise
    """
    ext = os.path.splitext(path)[1].lower()
    return ext in C_EXTENSIONS


def parse_gitignore(gitignore_path: str) -> List[str]:
    """
    Parse .gitignore file into list of patterns.
    
    Args:
        gitignore_path: Path to .gitignore file
        
    Returns:
        List of glob patterns from .gitignore
    """
    patterns = []
    
    if not os.path.exists(gitignore_path):
        return patterns
    
    try:
        with open(gitignore_path, 'r', encoding='utf-8') as f:
            for line in f:
                # Strip whitespace
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Remove trailing slash for directories (fnmatch compatibility)
                if line.endswith('/'):
                    line = line[:-1]
                
                patterns.append(line)
    
    except (IOError, UnicodeDecodeError):
        pass
    
    return patterns


def matches_pattern(path: str, patterns: List[str]) -> bool:
    """
    Check if a path matches any glob patterns.
    
    Args:
        path: File path to check
        patterns: List of glob patterns
        
    Returns:
        True if path matches any pattern, False otherwise
    """
    for pattern in patterns:
        # Handle directory patterns
        if pattern.endswith('/*'):
            dir_pattern = pattern[:-2]
            if fnmatch.fnmatch(path, dir_pattern + '*') or fnmatch.fnmatch(path, dir_pattern + '/*'):
                return True
        
        # Standard fnmatch
        if fnmatch.fnmatch(path, pattern):
            return True
        
        # Check if path is within a directory pattern
        if fnmatch.fnmatch(path, pattern + '/*'):
            return True
    
    return False


def get_relative_path(file_path: str, base_path: str) -> str:
    """
    Get relative path from a base path.
    
    Args:
        file_path: Full file path
        base_path: Base path to compute relative path from
        
    Returns:
        Relative path from base_path to file_path
    """
    try:
        abs_file = os.path.abspath(file_path)
        abs_base = os.path.abspath(base_path)
        return os.path.relpath(abs_file, abs_base)
    except ValueError:
        # Paths on different drives (Windows)
        return file_path


def read_file_safe(path: str) -> Optional[str]:
    """
    Read file content with encoding fallback.
    
    Tries UTF-8 first, falls back to latin-1 if that fails.
    
    Args:
        path: Path to file
        
    Returns:
        File content as string, or None if file cannot be read
    """
    if not os.path.exists(path):
        return None
    
    encodings = ['utf-8', 'latin-1']
    
    for encoding in encodings:
        try:
            with open(path, 'r', encoding=encoding) as f:
                return f.read()
        except (UnicodeDecodeError, IOError):
            continue
    
    return None


def find_files(root_dir: str, extensions: Optional[Set[str]] = None, 
               exclude_patterns: Optional[List[str]] = None) -> List[str]:
    """
    Find files recursively with optional extension and pattern filtering.
    
    Args:
        root_dir: Root directory to search
        extensions: Set of file extensions to include (e.g., {'.c', '.h'})
        exclude_patterns: List of glob patterns to exclude
        
    Returns:
        List of file paths matching criteria
    """
    files = []
    exclude_patterns = exclude_patterns or []
    
    if not os.path.isdir(root_dir):
        return files
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Filter directories to skip excluded patterns
        dirnames[:] = [
            d for d in dirnames
            if not matches_pattern(os.path.join(dirpath, d), exclude_patterns)
        ]
        
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            
            # Check exclusion patterns
            rel_path = get_relative_path(file_path, root_dir)
            if matches_pattern(rel_path, exclude_patterns):
                continue
            
            # Check extensions if specified
            if extensions and not is_c_file(file_path):
                continue
            
            files.append(file_path)
    
    return files
