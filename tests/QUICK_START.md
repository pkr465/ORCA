# ORCA Test Infrastructure - Quick Start Guide

## Installation & Execution

### Prerequisites
```bash
cd /sessions/vibrant-nice-hawking/mnt/ORCA
pip install pytest openpyxl  # Optional dependencies
```

### Run All Tests
```bash
pytest tests/test_full_pipeline.py -v
```

### Run Specific Test Class
```bash
pytest tests/test_full_pipeline.py::TestStaticAnalysis -v
pytest tests/test_full_pipeline.py::TestAnalyzers -v
pytest tests/test_full_pipeline.py::TestFixerAgent -v
```

### Run Single Test
```bash
pytest tests/test_full_pipeline.py::TestStaticAnalysis::test_single_file_analysis -v
```

### Run with Verbose Output
```bash
pytest tests/test_full_pipeline.py -v -s
```

## What Was Created

### 1. Sample C Code Files
Located in `/sessions/vibrant-nice-hawking/mnt/ORCA/tests/fixtures/sample_codebase/`

| File | Purpose |
|------|---------|
| `good_style.c` | Well-formatted compliant code |
| `bad_style.c` | Code with style violations (15+ issues) |
| `bad_style.h` | Header with violations |
| `memory_issue.c` | Structural/alignment issues |

### 2. Patch File
- `sample.patch` - Valid unified diff for patch testing

### 3. Test File
- `test_full_pipeline.py` (855 lines)
  - 9 test classes
  - 27+ test methods
  - Full pipeline coverage

### 4. Documentation
- `TEST_INFRASTRUCTURE.md` - Comprehensive documentation
- `QUICK_START.md` - This file

## Test Coverage

### Static Analysis (5 tests)
- Single file analysis
- Directory scanning
- Domain filtering
- Grade calculation
- Multi-domain audit

### Analyzers (7 tests)
- Style, whitespace, macro analysis
- License, include, structure checks
- Commit message validation

### Adapters (3 tests)
- Excel report generation
- Include guard validation
- SPDX compliance

### Fixer Agent (3 tests)
- Dry-run mode
- File fixes
- Backup creation

### Reports (3 tests)
- JSON output
- HTML output
- Excel output

### HITL & Patches (4 tests)
- Decision simulation
- Patch parsing
- Batch processing

### End-to-End (1 test)
- Full pipeline workflow

### Configuration (3 tests)
- Rules loading
- Config validation
- Fixture accessibility

## Example Test Output

```
test_single_file_analysis PASSED
Single file analysis findings: 12
Grade: C

test_directory_analysis PASSED
Directory analysis found 45 total findings
Files scanned: 4

test_excel_report_generation PASSED
Excel sheets created: ['Summary', 'style_violations', ...]

test_full_pipeline PASSED
Phase 1 - Initial scan: 25 findings
Phase 2 - Analysis: 7 domains analyzed
Phase 3 - Report generated: /tmp/.../analysis_report.json
Phase 4 - Fix (dry-run) available
```

## Common Commands

### Run tests matching pattern
```bash
pytest tests/test_full_pipeline.py -k "analyzer" -v
```

### Run with coverage
```bash
pytest tests/test_full_pipeline.py --cov=agents --cov-report=html
```

### Show failed tests only
```bash
pytest tests/test_full_pipeline.py --lf
```

### Stop on first failure
```bash
pytest tests/test_full_pipeline.py -x
```

### Run 4 tests in parallel
```bash
pytest tests/test_full_pipeline.py -n 4
```

## File Locations (Absolute Paths)

```
/sessions/vibrant-nice-hawking/mnt/ORCA/
├── tests/
│   ├── test_full_pipeline.py              ← Main test file
│   ├── TEST_INFRASTRUCTURE.md             ← Full documentation
│   ├── QUICK_START.md                     ← This file
│   ├── conftest.py                        ← Shared fixtures
│   └── fixtures/
│       ├── sample_codebase/
│       │   ├── good_style.c               ← Compliant code
│       │   ├── bad_style.c                ← 15+ violations
│       │   ├── bad_style.h                ← Header violations
│       │   └── memory_issue.c             ← Struct issues
│       ├── sample.patch                   ← Unified diff
│       └── sample_good.c, sample_bad.c    ← Original fixtures
└── agents/
    ├── compliance_static_agent.py         ← Tested
    ├── compliance_fixer_agent.py          ← Tested
    └── analyzers/                         ← Tested
```

## Test Classes Reference

| Class | Tests | Focus |
|-------|-------|-------|
| TestStaticAnalysis | 5 | Pipeline execution |
| TestAnalyzers | 7 | Individual checkers |
| TestAdapters | 3 | Report generation |
| TestFixerAgent | 3 | Remediation |
| TestReportGeneration | 3 | Output formats |
| TestHITLSimulated | 2 | User decisions |
| TestPatchAnalysis | 2 | Diff parsing |
| TestEndToEnd | 1 | Full workflow |
| TestConfigurationAndUtils | 3 | Setup & fixtures |

## Troubleshooting

### pytest not found
```bash
pip install pytest
```

### openpyxl not available
Tests skip Excel generation gracefully. Install if needed:
```bash
pip install openpyxl
```

### Permission denied
```bash
chmod +x /sessions/vibrant-nice-hawking/mnt/ORCA/tests/test_full_pipeline.py
```

### Import errors
```bash
cd /sessions/vibrant-nice-hawking/mnt/ORCA
export PYTHONPATH=$(pwd):$PYTHONPATH
pytest tests/test_full_pipeline.py -v
```

## Integration with CI/CD

These tests are designed for automated pipelines:

```yaml
# Example GitHub Actions
- name: Run ORCA Tests
  run: |
    cd mnt/ORCA
    pytest tests/test_full_pipeline.py -v --junit-xml=results.xml
```

```yaml
# Example GitLab CI
test_orca:
  script:
    - cd mnt/ORCA
    - pytest tests/test_full_pipeline.py -v
```

## Next Steps

1. **Run tests locally:**
   ```bash
   pytest tests/test_full_pipeline.py -v
   ```

2. **Review test documentation:**
   - Read `TEST_INFRASTRUCTURE.md` for details

3. **Extend tests:**
   - Add new analyzers to `TestAnalyzers`
   - Add new fixtures to `conftest.py`
   - Create new test classes for new features

4. **Integrate with CI/CD:**
   - Set up automated test runs
   - Configure coverage reporting
   - Add pre-commit hooks

## Support

For detailed information:
- See `TEST_INFRASTRUCTURE.md` for comprehensive guide
- Check individual test methods for usage examples
- Review sample files for realistic test cases

All tests are self-contained and ready to execute!
