"""Compliance adapters for various standards and tools."""

from agents.adapters.base_adapter import BaseComplianceAdapter, AdapterResult
from agents.adapters.checkpatch_adapter import CheckpatchAdapter
from agents.adapters.spdx_adapter import SPDXAdapter
from agents.adapters.include_guard_adapter import IncludeGuardAdapter
from agents.adapters.commit_message_adapter import CommitMessageAdapter
from agents.adapters.structure_adapter import StructureAdapter
from agents.adapters.excel_report_adapter import ExcelReportAdapter, ExcelTheme

__all__ = [
    "BaseComplianceAdapter",
    "AdapterResult",
    "CheckpatchAdapter",
    "SPDXAdapter",
    "IncludeGuardAdapter",
    "CommitMessageAdapter",
    "StructureAdapter",
    "ExcelReportAdapter",
    "ExcelTheme",
]
