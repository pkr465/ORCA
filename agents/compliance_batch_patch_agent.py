"""
Multi-file batch patch agent for ORCA.

Parses multi-file patches in various formats and applies them to the codebase,
writing patched copies to output directory. Supports 5 diff formats with
auto-detection, dry-run mode, and detailed processing logs.
"""

import argparse
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from enum import Enum


# ============================================================================
# Logging Setup
# ============================================================================

def setup_logger(name: str, verbose: bool = False) -> logging.Logger:
    """Configure logger with appropriate level."""
    logger = logging.getLogger(name)
    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logger(__name__)


# ============================================================================
# Enums and Constants
# ============================================================================

class DiffFormat(Enum):
    """Supported diff format types."""
    TRIPLE_EQ = "triple_equals"      # === server — local
    P4_HEADER = "p4_header"           # ==== depot#rev - local ====
    GIT_DIFF = "git_diff"             # diff --git a/path b/path
    PLAIN_DIFF = "plain_diff"         # diff -flags path_a path_b
    UNIFIED_DIFF = "unified_diff"     # --- a/path / +++ b/path
    UNKNOWN = "unknown"


# Regex patterns for format detection and parsing
_FILE_HEADER_RE = re.compile(
    r'^===\s+(.+?)\s+—\s+(.+?)\s*$',
    re.MULTILINE
)

_P4_HEADER_RE = re.compile(
    r'^====\s+(.+?)\s+-\s+(.+?)\s+====\s*$',
    re.MULTILINE
)

_UNIFIED_MINUS_RE = re.compile(r'^---\s+(.+?)(?:\t|$)', re.MULTILINE)
_UNIFIED_PLUS_RE = re.compile(r'^\+\+\+\s+(.+?)(?:\t|$)', re.MULTILINE)

_GIT_DIFF_RE = re.compile(
    r'^diff --git\s+a/(.+?)\s+b/(.+?)\s*$',
    re.MULTILINE
)

_PLAIN_DIFF_RE = re.compile(
    r'^diff\s+(-\w+\s+)*(.+?)\s+(.+?)\s*$',
    re.MULTILINE
)

_UNIFIED_HUNK_RE = re.compile(
    r'^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(.*)$',
    re.MULTILINE
)

_NORMAL_CMD_RE = re.compile(r'^(\d+)(?:,(\d+))?([acd])(\d+)(?:,(\d+))?$')


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class PatchHunk:
    """Represents a single hunk from a patch."""
    orig_start: int
    orig_count: int
    new_start: int
    new_count: int
    header: str
    removed_lines: List[str] = field(default_factory=list)
    added_lines: List[str] = field(default_factory=list)
    context_lines: List[str] = field(default_factory=list)
    raw_lines: List[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"PatchHunk(orig={self.orig_start}+{self.orig_count}, "
            f"new={self.new_start}+{self.new_count}, "
            f"removed={len(self.removed_lines)}, added={len(self.added_lines)})"
        )


@dataclass
class FileEntry:
    """Represents a file with its associated patch."""
    server_path: str
    local_path: str
    diff_body: str
    hunks: List[PatchHunk] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"FileEntry(server={self.server_path}, local={self.local_path}, "
            f"hunks={len(self.hunks)})"
        )


# ============================================================================
# Format Detection and Parsing Functions
# ============================================================================

def detect_diff_format(text: str) -> DiffFormat:
    """
    Auto-detect the diff format from patch text.

    Args:
        text: Patch content to analyze

    Returns:
        DiffFormat enum indicating detected format
    """
    if not text or not text.strip():
        return DiffFormat.UNKNOWN

    lines = text.split('\n')

    for line in lines[:20]:  # Check first 20 lines
        if _FILE_HEADER_RE.match(line):
            return DiffFormat.TRIPLE_EQ
        if _P4_HEADER_RE.match(line):
            return DiffFormat.P4_HEADER
        if _GIT_DIFF_RE.match(line):
            return DiffFormat.GIT_DIFF
        if line.startswith('diff -') and not line.startswith('diff --git'):
            return DiffFormat.PLAIN_DIFF
        if line.startswith('---') and line.lstrip('-')[0].isspace():
            return DiffFormat.UNIFIED_DIFF

    return DiffFormat.UNKNOWN


def parse_normal_diff(text: str) -> List[PatchHunk]:
    """
    Parse hunks from normal diff format (ed-style commands).

    Args:
        text: Diff body without headers

    Returns:
        List of PatchHunk objects
    """
    hunks = []
    lines = text.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        match = _NORMAL_CMD_RE.match(line)

        if not match:
            i += 1
            continue

        start1_str, end1_str, cmd, start2_str, end2_str = match.groups()
        start1 = int(start1_str)
        start2 = int(start2_str)
        end1 = int(end1_str) if end1_str else start1
        end2 = int(end2_str) if end2_str else start2

        orig_count = end1 - start1 + 1 if cmd != 'a' else 0
        new_count = end2 - start2 + 1 if cmd != 'd' else 0

        hunk = PatchHunk(
            orig_start=start1,
            orig_count=orig_count,
            new_start=start2,
            new_count=new_count,
            header=line,
            raw_lines=[line]
        )

        i += 1

        # Collect hunk content
        if cmd in ('a', 'c'):
            while i < len(lines) and lines[i] != '.':
                hunk.added_lines.append(lines[i].lstrip('> '))
                i += 1
            if i < len(lines):
                i += 1  # Skip the '.' marker

        if cmd in ('d', 'c'):
            # Removed lines already counted
            pass

        hunks.append(hunk)

    return hunks


def parse_unified_diff(text: str) -> List[PatchHunk]:
    """
    Parse hunks from unified diff format.

    Args:
        text: Diff body without file headers

    Returns:
        List of PatchHunk objects
    """
    hunks = []
    lines = text.split('\n')
    i = 0

    while i < len(lines):
        match = _UNIFIED_HUNK_RE.match(lines[i])

        if not match:
            i += 1
            continue

        orig_start = int(match.group(1))
        orig_count = int(match.group(2)) if match.group(2) else 1
        new_start = int(match.group(3))
        new_count = int(match.group(4)) if match.group(4) else 1
        header = match.group(5).strip()

        hunk = PatchHunk(
            orig_start=orig_start,
            orig_count=orig_count,
            new_start=new_start,
            new_count=new_count,
            header=header,
            raw_lines=[lines[i]]
        )

        i += 1

        # Collect hunk content
        while i < len(lines):
            line = lines[i]

            if line.startswith('@@'):
                break
            if line.startswith('\\'):
                i += 1
                continue

            if line.startswith('-'):
                hunk.removed_lines.append(line[1:])
            elif line.startswith('+'):
                hunk.added_lines.append(line[1:])
            elif line.startswith(' '):
                hunk.context_lines.append(line[1:])
            else:
                # Might be blank line or end of hunk
                if line == '':
                    pass
                else:
                    break

            hunk.raw_lines.append(line)
            i += 1

        hunks.append(hunk)

    return hunks


def parse_diff(text: str) -> Tuple[DiffFormat, List[PatchHunk]]:
    """
    Parse a diff body and detect its format, returning format and hunks.

    Args:
        text: Complete diff body

    Returns:
        Tuple of (DiffFormat, List[PatchHunk])
    """
    fmt = detect_diff_format(text)

    if fmt == DiffFormat.UNIFIED_DIFF:
        hunks = parse_unified_diff(text)
    elif fmt == DiffFormat.PLAIN_DIFF:
        hunks = parse_normal_diff(text)
    else:
        hunks = parse_unified_diff(text)  # Try unified as fallback

    return fmt, hunks


def apply_patch(source: str, hunks: List[PatchHunk]) -> str:
    """
    Apply patch hunks to source code.

    Args:
        source: Original file content
        hunks: List of patch hunks to apply

    Returns:
        Patched file content
    """
    if not hunks:
        return source

    lines = source.split('\n')
    offset = 0

    for hunk in hunks:
        # Adjust for previous modifications
        adj_start = hunk.orig_start - 1 + offset
        adj_end = adj_start + hunk.orig_count

        # Remove original lines
        del lines[adj_start:adj_end]

        # Insert new lines
        for new_line in hunk.added_lines:
            lines.insert(adj_start, new_line)
            adj_start += 1

        # Update offset
        offset += len(hunk.added_lines) - hunk.orig_count

    return '\n'.join(lines)


def parse_multi_file_patch(patch_text: str) -> List[FileEntry]:
    """
    Parse a multi-file patch into individual FileEntry objects.

    Detects the patch format and delegates to appropriate parser.

    Args:
        patch_text: Complete multi-file patch content

    Returns:
        List of FileEntry objects, one per file
    """
    fmt = detect_diff_format(patch_text)

    if fmt == DiffFormat.TRIPLE_EQ:
        return _parse_triple_eq(patch_text.split('\n'))
    elif fmt == DiffFormat.P4_HEADER:
        return _parse_p4_header(patch_text.split('\n'))
    elif fmt in (DiffFormat.GIT_DIFF, DiffFormat.UNIFIED_DIFF):
        return _parse_unified_headers(patch_text.split('\n'))
    else:
        return _parse_unified_headers(patch_text.split('\n'))


def _parse_triple_eq(lines: List[str]) -> List[FileEntry]:
    """Parse patches with === server — local format."""
    entries = []
    i = 0

    while i < len(lines):
        match = _FILE_HEADER_RE.match(lines[i])

        if not match:
            i += 1
            continue

        server_path = match.group(1).strip()
        local_path = match.group(2).strip()

        i += 1
        diff_lines = []

        while i < len(lines) and not _FILE_HEADER_RE.match(lines[i]):
            diff_lines.append(lines[i])
            i += 1

        diff_body = '\n'.join(diff_lines).strip()
        fmt, hunks = parse_diff(diff_body)

        entry = FileEntry(
            server_path=server_path,
            local_path=local_path,
            diff_body=diff_body,
            hunks=hunks
        )
        entries.append(entry)

    return entries


def _parse_p4_header(lines: List[str]) -> List[FileEntry]:
    """Parse patches with ==== depot#rev - local ==== format."""
    entries = []
    i = 0

    while i < len(lines):
        match = _P4_HEADER_RE.match(lines[i])

        if not match:
            i += 1
            continue

        server_path = match.group(1).strip()
        local_path = match.group(2).strip()

        i += 1
        diff_lines = []

        while i < len(lines) and not _P4_HEADER_RE.match(lines[i]):
            diff_lines.append(lines[i])
            i += 1

        diff_body = '\n'.join(diff_lines).strip()
        fmt, hunks = parse_diff(diff_body)

        entry = FileEntry(
            server_path=server_path,
            local_path=local_path,
            diff_body=diff_body,
            hunks=hunks
        )
        entries.append(entry)

    return entries


def _parse_unified_headers(lines: List[str]) -> List[FileEntry]:
    """Parse patches with --- a/path / +++ b/path or diff --git format."""
    entries = []
    i = 0

    while i < len(lines):
        # Look for file header markers
        git_match = _GIT_DIFF_RE.match(lines[i])

        if git_match:
            path_a = git_match.group(1)
            path_b = git_match.group(2)
            i += 1

            # Skip index and similar lines
            while i < len(lines) and (
                lines[i].startswith('index ') or
                lines[i].startswith('---') or
                lines[i].startswith('+++')
            ):
                i += 1

            diff_lines = []
            while i < len(lines) and not _GIT_DIFF_RE.match(lines[i]):
                if _UNIFIED_MINUS_RE.match(lines[i]):
                    break
                diff_lines.append(lines[i])
                i += 1

            diff_body = '\n'.join(diff_lines).strip()
            fmt, hunks = parse_diff(diff_body)

            entry = FileEntry(
                server_path=path_a,
                local_path=path_b,
                diff_body=diff_body,
                hunks=hunks
            )
            entries.append(entry)
        else:
            i += 1

    return entries


# ============================================================================
# Main Agent Class
# ============================================================================

class ComplianceBatchPatchAgent:
    """
    Multi-file batch patch agent for applying patches to codebase.

    Parses multi-file patches in various formats, resolves source paths,
    applies patches, and writes output to specified directory with full
    folder structure preserved.
    """

    def __init__(
        self,
        patch_file: str,
        codebase_path: str,
        output_dir: str,
        config: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
        verbose: bool = False
    ):
        """
        Initialize the batch patch agent.

        Args:
            patch_file: Path to patch file
            codebase_path: Root directory of codebase
            output_dir: Output directory for patched files
            config: Optional configuration dictionary
            dry_run: If True, don't write files, just simulate
            verbose: Enable verbose logging
        """
        self.patch_file = Path(patch_file)
        self.codebase_path = Path(codebase_path)
        self.output_dir = Path(output_dir)
        self.config = config or {}
        self.dry_run = dry_run
        self.verbose = verbose

        self.logger = setup_logger(
            f"{__name__}.{self.__class__.__name__}",
            verbose=verbose
        )

        # Stats tracking
        self.stats = {
            'total': 0,
            'patched': 0,
            'skipped': 0,
            'failed': 0,
            'files': []
        }

    def run(self) -> Dict[str, Any]:
        """
        Execute patch application workflow.

        Returns:
            Dictionary with processing stats and file list
        """
        self.logger.info(f"Loading patch file: {self.patch_file}")

        if not self.patch_file.exists():
            self.logger.error(f"Patch file not found: {self.patch_file}")
            return self.stats

        # Read patch file
        try:
            patch_text = self.patch_file.read_text(encoding='utf-8')
        except Exception as e:
            self.logger.error(f"Failed to read patch file: {e}")
            return self.stats

        # Parse multi-file patch
        self.logger.info("Parsing multi-file patch...")
        try:
            entries = parse_multi_file_patch(patch_text)
        except Exception as e:
            self.logger.error(f"Failed to parse patch: {e}")
            return self.stats

        self.logger.info(f"Found {len(entries)} file(s) to patch")
        self.stats['total'] = len(entries)

        # Process each entry
        for idx, entry in enumerate(entries, 1):
            result = self._process_entry(idx, len(entries), entry)
            if result:
                self.stats['files'].append(result)

        # Summary
        self.logger.info(
            f"\nSummary: {self.stats['patched']} patched, "
            f"{self.stats['skipped']} skipped, {self.stats['failed']} failed"
        )

        return self.stats

    def _process_entry(self, idx: int, total: int, entry: FileEntry) -> Optional[str]:
        """
        Process a single file entry.

        Args:
            idx: Entry number (1-indexed)
            total: Total number of entries
            entry: FileEntry to process

        Returns:
            Output path if successful, None otherwise
        """
        self.logger.info(
            f"[{idx}/{total}] Processing: {entry.local_path} "
            f"({len(entry.hunks)} hunk(s))"
        )

        # Resolve source path
        source_path = self._resolve_source_path(entry)
        if not source_path:
            self.logger.warning(f"  Could not resolve source path for {entry.local_path}")
            self.stats['skipped'] += 1
            return None

        # Read source file
        try:
            source_content = source_path.read_text(encoding='utf-8')
        except Exception as e:
            self.logger.error(f"  Failed to read source: {e}")
            self.stats['failed'] += 1
            return None

        # Apply patch
        try:
            patched_content = apply_patch(source_content, entry.hunks)
        except Exception as e:
            self.logger.error(f"  Failed to apply patch: {e}")
            self.stats['failed'] += 1
            return None

        # Determine output path
        rel_path = self._get_relative_path(source_path)
        output_path = self.output_dir / 'patched_files' / rel_path

        # Write output
        if not self.dry_run:
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(patched_content, encoding='utf-8')
                self.logger.info(f"  Written to: {output_path}")
            except Exception as e:
                self.logger.error(f"  Failed to write output: {e}")
                self.stats['failed'] += 1
                return None
        else:
            self.logger.info(f"  [DRY-RUN] Would write to: {output_path}")

        self.stats['patched'] += 1
        return str(output_path)

    def _resolve_source_path(self, entry: FileEntry) -> Optional[Path]:
        """
        Resolve the actual source file path.

        Tries multiple strategies:
        1. Absolute path (if entry.local_path is absolute)
        2. Relative to codebase root
        3. Filename match in codebase

        Args:
            entry: FileEntry with path info

        Returns:
            Resolved Path or None if not found
        """
        candidates = []

        # Strategy 1: Absolute path
        abs_path = Path(entry.local_path)
        if abs_path.is_absolute() and abs_path.exists():
            candidates.append(abs_path)

        # Strategy 2: Relative to codebase
        rel_path = self.codebase_path / entry.local_path
        if rel_path.exists():
            candidates.append(rel_path)

        # Strategy 3: Filename match
        filename = Path(entry.local_path).name
        for found_path in self.codebase_path.rglob(filename):
            if found_path.is_file():
                candidates.append(found_path)
                break

        if candidates:
            chosen = candidates[0]
            self.logger.debug(f"  Resolved {entry.local_path} to {chosen}")
            return chosen

        return None

    def _get_relative_path(self, source_path: Path) -> Path:
        """
        Get path relative to codebase for output organization.

        Args:
            source_path: Absolute source path

        Returns:
            Relative path from codebase root
        """
        try:
            return source_path.relative_to(self.codebase_path)
        except ValueError:
            # Path is not under codebase, use filename
            return Path(source_path.name)


# Backward-compatible alias
BatchPatchAgent = ComplianceBatchPatchAgent


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    """Command-line interface for batch patch agent."""
    parser = argparse.ArgumentParser(
        description='Multi-file batch patch agent for ORCA',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s patch.diff /path/to/codebase /output
  %(prog)s patch.diff /path/to/codebase /output --dry-run
  %(prog)s patch.diff /path/to/codebase /output --verbose
        """
    )

    parser.add_argument(
        'patch_file',
        help='Path to patch file'
    )

    parser.add_argument(
        'codebase_path',
        help='Root directory of codebase to patch'
    )

    parser.add_argument(
        'output_dir',
        help='Output directory for patched files'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulate patching without writing files'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    parser.add_argument(
        '--config',
        type=str,
        help='Path to JSON configuration file'
    )

    args = parser.parse_args()

    # Load config if provided
    config = {}
    if args.config:
        import json
        try:
            with open(args.config) as f:
                config = json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load config: {e}")

    # Create agent and run
    agent = ComplianceBatchPatchAgent(
        patch_file=args.patch_file,
        codebase_path=args.codebase_path,
        output_dir=args.output_dir,
        config=config,
        dry_run=args.dry_run,
        verbose=args.verbose
    )

    stats = agent.run()

    # Exit with appropriate code
    if stats['failed'] > 0:
        exit(1)
    elif stats['patched'] == 0:
        exit(1)
    else:
        exit(0)


if __name__ == '__main__':
    main()
