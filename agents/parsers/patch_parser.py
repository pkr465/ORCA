"""
Unified diff and git format-patch parser for compliance auditing.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
import re
from datetime import datetime


@dataclass
class Hunk:
    """Represents a single hunk in a unified diff."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: List[str] = field(default_factory=list)
    header: str = ""
    
    def get_added_lines(self) -> List[Tuple[int, str]]:
        """Extract added lines with their new line numbers."""
        added = []
        new_line_num = self.new_start
        for line in self.lines:
            if line.startswith('+') and not line.startswith('+++'):
                added.append((new_line_num, line[1:]))
                new_line_num += 1
            elif not line.startswith('-') and not line.startswith('\\'):
                new_line_num += 1
        return added
    
    def get_removed_lines(self) -> List[Tuple[int, str]]:
        """Extract removed lines with their old line numbers."""
        removed = []
        old_line_num = self.old_start
        for line in self.lines:
            if line.startswith('-') and not line.startswith('---'):
                removed.append((old_line_num, line[1:]))
                old_line_num += 1
            elif not line.startswith('+') and not line.startswith('\\'):
                old_line_num += 1
        return removed
    
    def get_context_lines(self) -> List[Tuple[int, int, str]]:
        """Extract context lines: (old_line_num, new_line_num, content)."""
        context = []
        old_num = self.old_start
        new_num = self.new_start
        for line in self.lines:
            if line.startswith(' '):
                context.append((old_num, new_num, line[1:]))
                old_num += 1
                new_num += 1
            elif line.startswith('-') and not line.startswith('---'):
                old_num += 1
            elif line.startswith('+') and not line.startswith('+++'):
                new_num += 1
        return context


@dataclass
class Patch:
    """Represents a single patch/diff."""
    filename: str
    subject: str = ""
    from_addr: str = ""
    date: str = ""
    body: str = ""
    hunks: List[Hunk] = field(default_factory=list)
    raw_content: str = ""
    signed_off_by: str = ""
    message_id: str = ""
    in_reply_to: str = ""
    
    def get_all_added_lines(self) -> List[Tuple[str, int, str]]:
        """Get all added lines: (filename, new_line_num, content)."""
        all_added = []
        for hunk in self.hunks:
            for line_num, content in hunk.get_added_lines():
                all_added.append((self.filename, line_num, content))
        return all_added
    
    def get_all_removed_lines(self) -> List[Tuple[str, int, str]]:
        """Get all removed lines: (filename, old_line_num, content)."""
        all_removed = []
        for hunk in self.hunks:
            for line_num, content in hunk.get_removed_lines():
                all_removed.append((self.filename, line_num, content))
        return all_removed


@dataclass
class PatchSeries:
    """Represents a series of patches."""
    patches: List[Patch] = field(default_factory=list)
    cover_letter: Optional[str] = None
    series_id: str = ""
    total_patches: int = 0


class PatchParser:
    """Parse unified diffs and git format-patch output."""
    
    HUNK_HEADER_PATTERN = re.compile(
        r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@'
    )
    
    def parse(self, content: str) -> Patch:
        """Parse single patch/diff file content."""
        lines = content.split('\n')
        patch = Patch(filename="", raw_content=content)
        
        # Parse headers and metadata
        header_dict = self._parse_headers(lines)
        patch.from_addr = header_dict.get('from', '')
        patch.date = header_dict.get('date', '')
        patch.subject = header_dict.get('subject', '')
        patch.signed_off_by = header_dict.get('signed_off_by', '')
        patch.message_id = header_dict.get('message_id', '')
        patch.in_reply_to = header_dict.get('in_reply_to', '')
        
        # Find patch content start
        patch_start = self._find_patch_start(lines)
        
        # Parse filename and hunks
        if patch_start >= 0:
            patch.filename = self._extract_filename(lines[patch_start:patch_start + 5])
            patch.hunks = self._parse_hunks(lines[patch_start:])
        
        # Parse body (message between headers and diff)
        body_start = self._find_body_start(lines)
        body_end = patch_start if patch_start >= 0 else len(lines)
        if body_start >= 0 and body_end > body_start:
            patch.body = '\n'.join(lines[body_start:body_end]).strip()
        
        return patch
    
    def parse_series(self, directory: str) -> PatchSeries:
        """Parse patch series from directory of patch files."""
        import os
        import glob
        
        series = PatchSeries()
        patch_files = sorted(glob.glob(os.path.join(directory, '*.patch')))
        
        patches = []
        for patch_file in patch_files:
            with open(patch_file, 'r') as f:
                content = f.read()
                patch = self.parse(content)
                patches.append(patch)
        
        series.patches = patches
        series.total_patches = len(patches)
        
        # Look for cover letter
        cover_letter_path = os.path.join(directory, '0000-cover-letter.patch')
        if os.path.exists(cover_letter_path):
            with open(cover_letter_path, 'r') as f:
                series.cover_letter = f.read()
        
        return series
    
    def _parse_headers(self, lines: List[str]) -> Dict[str, str]:
        """Extract email headers: From, Date, Subject, Signed-off-by."""
        headers = {}
        for i, line in enumerate(lines):
            if not line or line[0] not in ('A-Z', 'a-z'):
                break
            
            if ':' not in line:
                continue
            
            key, value = line.split(':', 1)
            key = key.strip().lower()
            value = value.strip()
            
            if key == 'from':
                headers['from'] = value
            elif key == 'date':
                headers['date'] = value
            elif key == 'subject':
                headers['subject'] = value
            elif key == 'signed-off-by':
                headers['signed_off_by'] = value
            elif key == 'message-id':
                headers['message_id'] = value
            elif key == 'in-reply-to':
                headers['in_reply_to'] = value
        
        return headers
    
    def _find_patch_start(self, lines: List[str]) -> int:
        """Find where the actual diff content starts."""
        for i, line in enumerate(lines):
            if line.startswith('diff --git') or line.startswith('--- '):
                return i
        return -1
    
    def _find_body_start(self, lines: List[str]) -> int:
        """Find where the commit message body starts."""
        in_headers = True
        for i, line in enumerate(lines):
            if in_headers and not line and (i > 0):
                return i + 1
            if ':' in line and in_headers:
                continue
            if line and not (':' in line or line[0].isspace()):
                in_headers = False
        return -1
    
    def _extract_filename(self, lines: List[str]) -> str:
        """Extract filename from diff header lines."""
        for line in lines:
            if line.startswith('+++ '):
                return line[4:].strip()
            elif line.startswith('--- '):
                return line[4:].strip()
        return "unknown"
    
    def _parse_hunks(self, lines: List[str]) -> List[Hunk]:
        """Parse @@ hunk headers and content."""
        hunks = []
        current_hunk = None
        i = 0
        
        while i < len(lines):
            line = lines[i]
            match = self.HUNK_HEADER_PATTERN.match(line)
            
            if match:
                if current_hunk:
                    hunks.append(current_hunk)
                
                old_start = int(match.group(1))
                old_count = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_count = int(match.group(4)) if match.group(4) else 1
                
                current_hunk = Hunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    header=line
                )
            elif current_hunk is not None:
                if line.startswith(('+', '-', ' ', '\\')):
                    current_hunk.lines.append(line)
                elif line.startswith('diff ') or line.startswith('--- ') or line.startswith('+++ '):
                    break
            
            i += 1
        
        if current_hunk:
            hunks.append(current_hunk)
        
        return hunks
    
    def _extract_added_lines(self, hunk: Hunk) -> List[str]:
        """Extract lines added in a hunk."""
        return [line[1:] for line in hunk.lines if line.startswith('+') and not line.startswith('+++')]
    
    def _extract_removed_lines(self, hunk: Hunk) -> List[str]:
        """Extract lines removed in a hunk."""
        return [line[1:] for line in hunk.lines if line.startswith('-') and not line.startswith('---')]
