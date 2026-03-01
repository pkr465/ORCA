"""
ORCA Context Layer — C/C++ code-aware context modules for compliance analysis.

Context Modules:
    HeaderContextBuilder        — Resolves #include chains, parses headers for enums/structs/macros
    CodebaseConstraintGenerator — Auto-generates constraint .md from codebase symbols
"""

__all__ = [
    "HeaderContextBuilder",
    "CodebaseConstraintGenerator",
    "generate_constraints",
]


def __getattr__(name):
    """Lazy imports to avoid pulling in heavy dependencies at startup."""
    if name == "HeaderContextBuilder":
        from agents.context.header_context_builder import HeaderContextBuilder
        return HeaderContextBuilder
    if name in ("CodebaseConstraintGenerator", "generate_constraints"):
        from agents.context import codebase_constraint_generator as _mod
        if name == "CodebaseConstraintGenerator":
            return _mod.CodebaseSymbolExtractor
        return _mod.generate_constraints
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
