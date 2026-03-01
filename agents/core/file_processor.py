from dataclasses import dataclass
from typing import List, Set
import os
import fnmatch


# Standard C language file extensions
C_EXTENSIONS = {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hxx"}


@dataclass
class FileMetadata:
    """Metadata about a discovered file."""
    path: str  # Absolute path
    relative_path: str  # Path relative to codebase root
    size_bytes: int
    line_count: int
    extension: str
    is_header: bool  # True if .h/.hpp/.hxx
    is_test: bool  # True if matches test patterns


class FileProcessor:
    """Processes and discovers files in a codebase."""

    def __init__(self, config: dict):
        """
        Initialize the file processor.

        Args:
            config: Configuration dictionary with keys like:
                - exclude_patterns: list of glob patterns to exclude
                - file_extensions: set of extensions to include
        """
        self.config = config
        self.exclude_patterns = config.get("exclude_patterns", [])
        self.file_extensions = config.get("file_extensions", C_EXTENSIONS)

    def discover_files(self, codebase_path: str) -> List[FileMetadata]:
        """
        Discover all relevant files in the codebase.

        Args:
            codebase_path: Root directory to scan

        Returns:
            List of FileMetadata for discovered files
        """
        metadata_list = []

        for root, dirs, files in os.walk(codebase_path):
            # Respect .gitignore by excluding common directories
            dirs[:] = [
                d for d in dirs
                if d not in {".git", ".svn", "node_modules", "__pycache__", ".pytest_cache", "venv", ".venv"}
            ]

            for filename in files:
                file_path = os.path.join(root, filename)
                relative_path = os.path.relpath(file_path, codebase_path)

                # Check if file should be excluded
                if self._should_exclude(relative_path, self.exclude_patterns):
                    continue

                # Check file extension
                _, ext = os.path.splitext(filename)
                if ext not in self.file_extensions:
                    continue

                # Build metadata
                try:
                    metadata = self._build_metadata(file_path, codebase_path)
                    metadata_list.append(metadata)
                except (OSError, IOError):
                    # Skip files that can't be read
                    continue

        return metadata_list

    def _should_exclude(self, path: str, exclude_patterns: List[str]) -> bool:
        """
        Check if a path matches any exclude pattern.

        Args:
            path: Relative path to check
            exclude_patterns: List of glob patterns

        Returns:
            True if path should be excluded
        """
        for pattern in exclude_patterns:
            if fnmatch.fnmatch(path, pattern):
                return True
        return False

    def _build_metadata(self, file_path: str, base_path: str) -> FileMetadata:
        """
        Build FileMetadata for a file.

        Args:
            file_path: Absolute path to file
            base_path: Base codebase path for relative path calculation

        Returns:
            FileMetadata object
        """
        relative_path = os.path.relpath(file_path, base_path)
        size_bytes = os.path.getsize(file_path)

        # Count lines
        line_count = 0
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                line_count = sum(1 for _ in f)
        except (OSError, IOError):
            line_count = 0

        # Check if header file
        _, ext = os.path.splitext(file_path)
        is_header = ext in {".h", ".hpp", ".hxx"}

        # Check if test file
        basename = os.path.basename(file_path)
        is_test = (
            "test" in basename.lower()
            or "_test" in basename.lower()
            or basename.startswith("test_")
        )

        return FileMetadata(
            path=file_path,
            relative_path=relative_path,
            size_bytes=size_bytes,
            line_count=line_count,
            extension=ext,
            is_header=is_header,
            is_test=is_test,
        )

    def get_file_content(self, path: str) -> str:
        """
        Read file content with encoding fallback.

        Args:
            path: Path to file

        Returns:
            File content as string

        Raises:
            OSError: If file cannot be read
        """
        # Try UTF-8 first
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            pass

        # Fall back to latin-1 (ISO-8859-1)
        try:
            with open(path, "r", encoding="latin-1") as f:
                return f.read()
        except (OSError, IOError) as e:
            raise OSError(f"Cannot read file {path}: {e}")
