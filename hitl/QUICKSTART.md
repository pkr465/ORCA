# HITL Pipeline - Quick Start Guide

## Installation

No external dependencies needed! Just import:

```python
from hitl import FeedbackStore, RAGRetriever, ConstraintParser
```

## Basic Usage

### 1. Initialize FeedbackStore

```python
from hitl import FeedbackStore

# Create/open database
store = FeedbackStore("/path/to/feedback.db")

# Record a compliance decision
store.record_decision(
    project="myapp",
    file_path="src/main.py",
    rule_id="license_header",
    violation_text="Missing SPDX-License-Identifier",
    decision="FIX",  # or SKIP, WAIVE, FIX_WITH_CONSTRAINTS, NEEDS_REVIEW, UPSTREAM_EXCEPTION
    constraints="Internal code requires header",
    reviewer="alice@company.com",
    confidence=0.95
)

# Query decisions
decisions = store.query_by_rule("license_header")
for d in decisions:
    print(f"{d.file_path}: {d.decision}")

# Get statistics
stats = store.get_decision_stats("license_header")
print(f"FIX: {stats['FIX']}, WAIVE: {stats['WAIVE']}")

# Export/Import
store.export_to_json("backup.json")
store.import_from_json("backup.json")

# Clean up
store.close()
```

### 2. Initialize RAGRetriever

```python
from hitl import FeedbackStore, RAGRetriever

store = FeedbackStore("feedback.db")
rag = RAGRetriever(store, config={
    'similarity_threshold': 0.3,
    'top_k': 5
})

# Retrieve context for a finding
finding = {
    "rule_id": "license_header",
    "file_path": "vendor/requests.py",
    "violation_text": "Missing SPDX header",
    "project": "myapp"
}

context = rag.retrieve_context(finding)

# Access results
print(f"Found {len(context.past_decisions)} similar decisions")
print(f"Recommendation: {context.recommendation}")

# Format for LLM
prompt_text = rag.format_for_prompt(context)
print(f"Inject into prompt:\n{prompt_text}")
```

### 3. Initialize ConstraintParser

```python
from hitl import ConstraintParser

parser = ConstraintParser()

# Parse from file
parser.parse_file("constraints.md")

# Or parse from text
constraint_text = """
# Constraints for license_header
## Conditions
- File matches vendor/*
## Actions
- WAIVE: Vendor code has own license

# Constraints for docstring
## Conditions
- File is a test fixture
## Actions
- SKIP: Tests don't need docstrings
"""
parser.parse_text(constraint_text)

# Evaluate constraints
finding = {
    "rule_id": "license_header",
    "file_path": "vendor/lib.py",
    "violation_text": "Missing header"
}

action = parser.evaluate_constraints(finding)
if action:
    print(f"Constraint recommends: {action}")
else:
    print("No constraint matches")
```

## Complete Workflow

```python
from hitl import FeedbackStore, RAGRetriever, ConstraintParser

# 1. Setup
store = FeedbackStore("feedback.db")
rag = RAGRetriever(store)
parser = ConstraintParser()
parser.parse_file("constraints.md")

# 2. Process finding
finding = {
    "rule_id": "style_indent",
    "file_path": "src/utils.py",
    "violation_text": "Indentation error",
    "project": "myapp"
}

# 3. Check constraints first
action = parser.evaluate_constraints(finding)
if action:
    print(f"Automated: {action}")
    store.record_decision(**finding, decision=action, reviewer="bot")
else:
    # 4. If no constraint, get RAG context for human review
    context = rag.retrieve_context(finding)
    prompt = rag.format_for_prompt(context)
    
    # 5. Show LLM the context (simplified)
    print(f"Context for LLM:\n{prompt}")
    
    # 6. Human reviews and decides
    human_decision = "FIX"  # e.g., from user input
    
    # 7. Record decision
    store.record_decision(
        **finding,
        decision=human_decision,
        reviewer="human@company.com",
        confidence=0.9
    )

# 8. Export learned decisions
store.export_to_json("decisions_backup.json")

store.close()
```

## Decision Types

| Type | Meaning | Use Case |
|------|---------|----------|
| `FIX` | Apply fix to file | Code needs correction |
| `SKIP` | Ignore violation | Not applicable to file |
| `WAIVE` | Exempt from rule | Policy exception |
| `FIX_WITH_CONSTRAINTS` | Fix with conditions | Conditional compliance |
| `NEEDS_REVIEW` | Escalate | Needs human review |
| `UPSTREAM_EXCEPTION` | Another team handles | External responsibility |

## Constraint Conditions

Markdown format for rules:

```markdown
# Constraints for rule_id

## Conditions
- File matches vendor/*              # Glob pattern
- File is auto-generated            # Auto-gen detection
- File is a test fixture            # Test file detection
- File is vendor code               # Vendor directory
- Project is legacy_system          # Project name
- Violation contains deprecated     # Text search

## Actions
- WAIVE: Reason for exemption
- SKIP: Reason to skip
- FIX: Reason to apply fix
```

Multiple conditions use AND logic (all must match).

## API Reference

### FeedbackStore

```python
store = FeedbackStore(db_path=":memory:")  # or file path

# Core operations
store.record_decision(project, file_path, rule_id, violation_text, 
                     decision, constraints=None, reviewer=None, confidence=1.0)
store.query_by_rule(rule_id, project=None, limit=10)
store.query_by_file(file_path, limit=10)
store.query_similar(rule_id, file_path=None, project=None, limit=5)
store.get_decision_stats(rule_id=None)
store.get_all_decisions(project=None, limit=100)
store.delete_decision(decision_id)
store.export_to_json(output_path)
store.import_from_json(input_path)
store.close()
```

### RAGRetriever

```python
rag = RAGRetriever(feedback_store, config=None)

# Retrieve context
context = rag.retrieve_context(finding, top_k=None)

# Format for prompt
text = rag.format_for_prompt(context)

# Access results
context.past_decisions  # List[ComplianceDecision]
context.constraints     # List[str]
context.recommendation  # str
```

### ConstraintParser

```python
parser = ConstraintParser()

# Load constraints
parser.parse_file(file_path)
parser.parse_text(content)

# Query and evaluate
constraints = parser.get_constraints_for_rule(rule_id)
action = parser.evaluate_constraints(finding, constraints=None)
```

## Examples

### Query Recent Decisions
```python
decisions = store.query_by_rule("license_header", limit=5)
for d in decisions:
    print(f"{d.timestamp}: {d.file_path} -> {d.decision}")
```

### Find Patterns
```python
stats = store.get_decision_stats()
for decision_type, count in stats.items():
    if count > 0:
        print(f"{decision_type}: {count}")
```

### Backup and Restore
```python
# Backup
store.export_to_json("backup.json")

# Restore
store2 = FeedbackStore("new.db")
store2.import_from_json("backup.json")
```

### RAG-Enhanced Prompts
```python
context = rag.retrieve_context(finding)
prompt = f"""
You are a compliance reviewer. Use the following context:

{rag.format_for_prompt(context)}

Now review this finding:
{finding}

What action should be taken?
"""
# Send to LLM
```

## Performance Tips

1. Use project filtering in queries for large databases
2. Set appropriate similarity_threshold in RAGRetriever
3. Create constraint rules to automate common patterns
4. Export decisions periodically for backup
5. Use database path instead of in-memory for production

## Troubleshooting

**No constraints matching?**
- Check condition syntax in markdown
- Remember: all conditions must match (AND logic)
- Use `parser.get_constraints_for_rule()` to verify parsing

**Low similarity scores?**
- Increase `similarity_threshold` in RAGRetriever config
- Check that past decisions have similar rule_ids
- Verify project matching in similar decisions

**Database locked error?**
- Call `store.close()` when done
- Use context manager: `with FeedbackStore() as store:`

