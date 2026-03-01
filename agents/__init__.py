"""
ORCA Agents — Multi-agent compliance auditing framework for C/C++ codebases.

Agents:
    ComplianceStaticAgent       — 7-phase static analysis pipeline
    ComplianceAuditAgent        — LLM-enriched semantic compliance audit
    ComplianceSolutionAgent     — Fix recommendation generator
    ComplianceFixerAgent        — Automated remediation engine with backup/rollback
    CompliancePatchAgent        — Patch diff analysis (isolate introduced issues)
    ComplianceBatchPatchAgent   — Multi-file batch patch application
    ComplianceAnalysisOrchestration — Conversational analysis chat agent

Context Layer (agents.context):
    HeaderContextBuilder        — #include resolution, header parsing (enums/structs/macros)
    CodebaseConstraintGenerator — Auto-generate constraint .md from codebase symbols
"""

# Lazy imports — each agent is imported on first access to avoid
# pulling in heavy dependencies (openpyxl, LLMTools, etc.) at startup.

__all__ = [
    "ComplianceStaticAgent",
    "ComplianceAuditAgent",
    "ComplianceSolutionAgent",
    "ComplianceFixerAgent",
    "CompliancePatchAgent",
    "ComplianceBatchPatchAgent",
    "BatchPatchAgent",
    "ComplianceAnalysisOrchestration",
    "ComplianceAnalysisSessionState",
    # Context Layer (access via agents.context)
    # HeaderContextBuilder, ContextValidator, FunctionParamValidator,
    # StaticCallStackAnalyzer, CodebaseConstraintGenerator, generate_constraints
]
