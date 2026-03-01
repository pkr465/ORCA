# ORCA Test Suite

Complete test suite for the Open Compliance & Resilience Auditor (ORCA) project.

## Fixture Files

### Good Examples
- **sample_good.c** (45 lines) - Well-formatted kernel-style C file with proper:
  - SPDX license header
  - Copyright notice
  - Tab indentation
  - snake_case naming
  - K&R brace style
  - Proper spacing after keywords
  - Clean documentation comments

- **sample_good.h** (11 lines) - Header file with:
  - SPDX license header
  - Include guards (#ifndef pattern)
  - Clean function declarations

### Bad Examples
- **sample_bad.c** (85 lines) - C file with MANY intentional violations:
  - Missing SPDX header
  - Missing copyright notice
  - Space indentation instead of tabs
  - CamelCase function and variable names
  - Hungarian notation (pName, Value)
  - Unnecessary typedef
  - Missing space after keywords (if, for)
  - Lines exceeding 80 characters
  - Unsafe macros without parens
  - extern declarations in .c file
  - Excessively long function (50+ lines)

- **sample_bad.h** (5 lines) - Header with:
  - No SPDX or copyright
  - No include guards
  - CamelCase naming

### Patch Examples
- **sample_patch.patch** - Git patch file with:
  - Long subject line (>72 chars)
  - Patch format issues
  - Improper indentation in code

## Test Files

### conftest.py
Pytest configuration and shared fixtures:
- `fixtures_dir` - Path to fixture directory
- `sample_good_c`, `sample_bad_c` - File contents
- `sample_good_h`, `sample_bad_h` - Header contents
- `kernel_rules` - Linux kernel compliance rules
- `default_config` - Default ORCA configuration
- `temp_dir` - Temporary test directory (auto-cleanup)
- `temp_codebase` - Temporary codebase with fixtures

### test_analyzers.py (173 lines)
Tests for all static analysis modules:

**TestStyleAnalyzer** (6 tests)
- Space vs tab detection
- Line length violations
- CamelCase naming
- Typedef usage
- Space after keywords
- Overall good file validation

**TestLicenseAnalyzer** (3 tests)
- Missing SPDX header detection
- Valid SPDX acceptance
- Missing copyright detection

**TestWhitespaceAnalyzer** (2 tests)
- Trailing whitespace detection
- Mixed line endings

**TestMacroAnalyzer** (1 test)
- Unparenthesized macro arguments

**TestIncludeAnalyzer** (1 test)
- Wrong include order

**TestStructureAnalyzer** (1 test)
- extern declarations in .c files

**TestCommitAnalyzer** (2 tests)
- Long subject lines
- Past tense detection

### test_adapters.py
Tests for compliance adapters:

**TestIncludeGuardAdapter**
- Missing include guard detection
- Valid guard acceptance

**TestSPDXAdapter**
- Missing SPDX detection
- Valid SPDX acceptance

**TestCheckpatchAdapter**
- Graceful handling when tool unavailable

**TestExcelReportAdapter**
- Report generation

### test_hitl.py
Tests for Human-in-the-Loop pipeline:

**TestFeedbackStore**
- Recording and querying decisions
- Decision statistics
- Export/import functionality

**TestRAGRetriever**
- Context retrieval for similar violations

### test_integration.py
End-to-end integration tests:

**TestFullPipeline**
- Full static audit on fixtures
- CLI help verification
- JSON report generation

## Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_analyzers.py

# Run specific test class
pytest tests/test_analyzers.py::TestStyleAnalyzer

# Run with verbose output
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=agents --cov=hitl
```

## Test Coverage

The test suite covers:
- All 8 analyzer types (style, license, whitespace, macro, include, structure, commit)
- 4 adapter types (include guard, SPDX, checkpatch, Excel report)
- HITL feedback store and RAG retriever
- End-to-end integration pipeline
- CLI functionality
- Report generation (Excel, JSON)

Total: 30+ test cases covering compliance domains and pipeline integration.
