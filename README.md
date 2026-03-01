# ORCA — Open-source Rules Compliance Auditor

ORCA is an LLM-powered, multi-agent compliance auditing framework for **C/C++ codebases only**. It combines fast static analysis with optional LLM semantic reasoning to audit coding style, license compliance, patch format, and code structure. It features context-aware analysis (header resolution and auto-generated constraints), a fixer workflow for human-in-the-loop remediation, and context-enriched LLM analysis — then generates fix recommendations and detailed reports.

---

## Quick Start

The fastest way to get ORCA running is the installer script. It detects your OS, installs Python 3.9+ if needed, creates a virtual environment, installs all dependencies, bootstraps PostgreSQL, sets up `.env`, and validates the installation:

```bash
chmod +x install.sh
./install.sh
```

Once installed, activate the virtual environment and start using ORCA:

```bash
source .venv/bin/activate

# Run a basic audit on your source code
python main.py audit --codebase-path ./src

# Run context-aware analysis (auto-generate constraints + audit)
python main.py audit --codebase-path ./src --enable-context --audit-llm

# Auto-generate codebase constraints from enums/structs/macros
python main.py context-gen --codebase-path ./src

# Run the HITL fixer workflow
python main.py fixer-workflow --excel-file out/detailed_code_review.xlsx

# Run the full pipeline (audit → solutions → fix → report)
python main.py pipeline --codebase-path ./src

# Launch the interactive web UI
./launch.sh

# View CLI help
python main.py --help
```

---

## Installation

**Requirements:** Python 3.9+, PostgreSQL 12+

### Option A: Automated Install (Recommended)

`install.sh` handles the full setup — OS detection, Python installation, virtual environment, pip dependencies, PostgreSQL bootstrap, `.env` configuration, CLI tool install, and validation:

```bash
chmod +x install.sh
./install.sh
```

The installer supports macOS (Homebrew), Debian/Ubuntu (apt), RHEL/Fedora (dnf/yum), Arch Linux (pacman), and WSL.

### Option B: Manual Install

If you prefer manual control over each step:

**1. Python & Dependencies**

```bash
# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Linux / macOS
# .venv\Scripts\activate    # Windows

# Core install (static analysis + reporting + HITL database)
pip install -r requirements.txt

# Or install individual packages
pip install pyyaml>=6.0 openpyxl>=3.1.0 psycopg2-binary>=2.9.0

# Optional: LLM support (for semantic analysis)
pip install anthropic>=0.15.0 openai>=1.0.0

# Optional: Install as a CLI tool
pip install -e .
# Now you can use `orca` instead of `python main.py`
```

**2. Bootstrap PostgreSQL**

The bootstrap script handles everything — installs PostgreSQL via your system package manager (Homebrew on macOS, apt on Debian/Ubuntu, dnf on RHEL/Fedora), starts the service, creates the user, database, schema, tables, and indexes:

```bash
# One command does it all:
python db/bootstrap_db.py

# With custom user/password:
python db/bootstrap_db.py --user orca --password secret --database orca_feedback

# If PostgreSQL is already installed and running:
python db/bootstrap_db.py --skip-install
```

If you prefer manual control, you can use `db/setup_db.py` instead (assumes PostgreSQL is already running):

```bash
python db/setup_db.py --host localhost --user orca --database orca_feedback
```

**3. Environment Variables**

```bash
cp env.example .env
# Edit .env with your API keys (LLM_API_KEY, QGENIE_API_KEY)
```

---

## Configuration

ORCA uses a three-tier configuration priority system:

1. **CLI arguments** (highest priority — always wins)
2. **config.yaml** (project-level defaults)
3. **Built-in hardcoded defaults** (fallback)

This means every option has a sensible default. You only need to specify what you want to change.

### Config File Lookup Order

ORCA automatically searches for config files in this order:

1. `--config-file <path>` (explicit CLI flag)
2. `./config.yaml` (project root)
3. `./global_config.yaml` (legacy name)
4. `~/.orca/config.yaml` (user-level)

### Editing config.yaml

The `config.yaml` file in the project root contains every configurable option with comments. Here are the key sections:

```yaml
# Paths
paths:
  codebase: "."              # Source code root
  output: "./out"            # Report output directory
  rules_preset: "kernel"     # Built-in rules: kernel | uboot | yocto | custom

# Audit behavior
audit:
  static: true               # Always run static analysis
  llm: false                 # Set to true for LLM-powered audits
  domains:                   # Which compliance domains to check
    - style
    - license
    - structure
    - patch

# Context system
context:
  enable: false              # Enable context-aware analysis
  constraints_dir: ""        # Custom constraints directory
  auto_generate: false       # Auto-generate constraints

# LLM (only needed if audit.llm is true)
llm:
  provider: "mock"           # anthropic | openai | qgenie | mock
  model: "anthropic::claude-sonnet-4-20250514"
  api_key: "${ANTHROPIC_API_KEY:-}"
  mock_mode: true            # Set to false for real LLM calls

# Reporting
reporting:
  formats:
    - excel
    - json
```

### Environment Variables

Copy `env.example` to `.env` and fill in your values:

```bash
cp env.example .env
# Edit .env with your API keys and database credentials
export $(grep -v '^#' .env | xargs)
```

Any string value in `config.yaml` supports `${VAR:-default}` interpolation. All variables below are pre-configured in `env.example`:

| Variable               | Description                        |
|------------------------|------------------------------------|
| `ANTHROPIC_API_KEY`   | Anthropic API key                   |
| `OPENAI_API_KEY`      | OpenAI API key (alternative)        |
| `ORCA_LLM_PROVIDER`   | LLM provider (anthropic/openai)    |
| `ORCA_LLM_MODEL`      | LLM model identifier               |
| `ORCA_CODEBASE_PATH`  | Source code root directory          |
| `ORCA_OUTPUT_DIR`      | Report output directory             |
| `ORCA_RULES_FILE`     | Path to custom rules YAML          |
| `ORCA_PG_HOST`        | PostgreSQL host (default: localhost)|
| `ORCA_PG_PORT`        | PostgreSQL port (default: 5432)    |
| `ORCA_PG_DATABASE`    | PostgreSQL database name           |
| `ORCA_PG_USER`        | PostgreSQL user (default: orca)    |
| `ORCA_PG_PASSWORD`    | PostgreSQL password                |
| `ORCA_PG_URL`         | Full PostgreSQL DSN (overrides above)|
| `CHECKPATCH_PATH`     | Path to checkpatch.pl              |
| `SCANCODE_PATH`       | Path to ScanCode toolkit           |

---

## Web UI (Streamlit)

ORCA includes a full-featured interactive web dashboard built with Streamlit.

```bash
# Install Streamlit
pip install streamlit

# Launch the UI
streamlit run ui/app.py
```

The UI provides:

- **Sidebar controls** — select codebase path (directory or single file), rules preset, analysis mode (Static only / LLM only / Both), domains, and advanced options
- **Findings browser** — filterable by severity, domain, file, with search and expandable detail cards showing code snippets, suggestions, and confidence scores
- **Domain breakdown** — severity distribution metrics, domain score progress bars, and a top-files-by-finding chart
- **Fix & Remediate** — select a domain, choose dry-run or apply mode, and run the fixer agent; view diffs, audit trails, and fix status per file
- **User Feedback** — review each finding and assign a decision (FIX, SKIP, WAIVE, NEEDS_REVIEW, UPSTREAM_EXCEPTION); decisions are persisted to the PostgreSQL HITL database for RAG-powered future audits
- **Reports & Export** — download generated JSON, Excel, and HTML reports; preview JSON inline; re-generate on demand
- **History** — track past audit runs with timestamp, grade, and finding count

---

## CLI Commands

### `audit` — Run Compliance Audit

The primary command. Scans source files and reports compliance findings.

```bash
# Basic audit (uses config.yaml defaults)
python main.py audit --codebase-path ./src

# Audit with Linux kernel rules
python main.py audit --codebase-path ./src --rules-preset kernel

# Audit specific domains only
python main.py audit --codebase-path ./src --domains style,license

# Audit with LLM semantic analysis
python main.py audit --codebase-path ./src --audit-llm

# Context-aware audit: auto-generate constraints + analyze
python main.py audit --codebase-path ./src --enable-context --audit-llm

# Audit with both static + LLM
python main.py audit --codebase-path ./src --audit-all

# Audit with HITL feedback enrichment
python main.py audit --codebase-path ./src --enable-hitl

# Custom output directory and report formats
python main.py audit --codebase-path ./src --out-dir ./reports --report-format html,json

# Verbose logging
python main.py audit --codebase-path ./src -vv
```

**Key options:**

| Flag                  | Default          | Description                              |
|-----------------------|------------------|------------------------------------------|
| `--codebase-path`     | `.` (from config)| Source code root directory               |
| `--rules-preset`      | `kernel`         | Built-in rules: kernel, uboot, yocto    |
| `--rules-file`        | —                | Path to custom rules YAML               |
| `--domains`           | `all`            | Domains: style,license,structure,patch   |
| `--enable-context`    | false            | Enable context-aware analysis           |
| `--constraints-dir`   | —                | Path to constraint .md files            |
| `--generate-constraints` | false         | Auto-generate constraints from codebase |
| `--include-paths`     | —                | Paths to include in context analysis    |
| `--audit-llm`         | false            | Enable LLM semantic analysis            |
| `--audit-all`         | false            | Run both static + LLM analysis          |
| `--enable-adapters`   | false            | Enable external tools (checkpatch, etc.) |
| `--enable-hitl`       | false            | Enable HITL feedback enrichment         |
| `--report-format`     | `excel,json`     | Output formats                          |
| `--out-dir`           | `./out`          | Report output directory                 |
| `--batch-size`        | 50               | Files per processing batch              |
| `--max-files`         | 10000            | Maximum files to scan                   |

---

### `context-gen` — Auto-Generate Codebase Constraints

Scans C/C++ codebase and auto-generates constraint .md files from enums, structs, macros, bitmasks, and validator functions. These constraints are injected into LLM prompts to reduce false positives.

```bash
# Basic constraint generation
python main.py context-gen --codebase-path ./src

# Custom output location
python main.py context-gen --codebase-path ./src --output constraints/my_constraints.md

# Exclude build/vendor directories
python main.py context-gen --codebase-path ./src --exclude-dirs build,vendor

# Exclude specific patterns
python main.py context-gen --codebase-path ./src --exclude-globs "*/test/*,*.gen.c"

# Verbose output (show extracted items)
python main.py context-gen --codebase-path ./src --verbose
```

**Key options:**

| Flag                | Default        | Description                            |
|---------------------|----------------|----------------------------------------|
| `--codebase-path`   | `.`            | Source code root directory             |
| `--output`          | `constraints.md` | Output constraint file                 |
| `--exclude-dirs`    | —              | Comma-separated directories to skip    |
| `--exclude-globs`   | —              | Glob patterns to exclude               |
| `--verbose`         | false          | Show extracted items during generation |

---

### `fixer-workflow` — HITL Repair Orchestrator

Runs the human-in-the-loop repair pipeline with three modes: **fixer** (Excel→fix), **patch** (single patch analysis+fix), and **batch-patch** (multi-file patch analysis+fix).

```bash
# Mode 1: Fixer — apply fixes from Excel review output
python main.py fixer-workflow --excel-file out/detailed_code_review.xlsx

# Mode 2: Single patch — analyze and fix a patch
python main.py fixer-workflow --patch-file fix.patch --patch-target src/main.c

# Mode 3: Batch patch — apply multi-file patch
python main.py fixer-workflow --batch-patch changes.patch --codebase-path ./src

# Analyse only (dry-run, no fixes applied)
python main.py fixer-workflow --analyse-only --batch-patch changes.patch

# Fix only (apply fixes without re-analysis)
python main.py fixer-workflow --fix-only --excel-file out/detailed_code_review.xlsx

# Specify fix source strategy
python main.py fixer-workflow --excel-file out/detailed_code_review.xlsx --fix-source llm

# Dry-run (preview changes without applying)
python main.py fixer-workflow --batch-patch changes.patch --codebase-path ./src --dry-run

# Custom LLM model
python main.py fixer-workflow --excel-file out/detailed_code_review.xlsx --llm-model anthropic::claude-opus
```

**Key options:**

| Flag                | Default        | Description                            |
|---------------------|----------------|----------------------------------------|
| `--excel-file`      | —              | Path to detailed_code_review.xlsx      |
| `--batch-patch`     | —              | Path to multi-file patch               |
| `--patch-file`      | —              | Path to single patch file              |
| `--patch-target`    | —              | Target file for patch (with --patch-file) |
| `--codebase-path`   | `.`            | Source code root (for batch-patch)     |
| `--analyse-only`    | false          | Skip fix application                   |
| `--fix-only`        | false          | Skip analysis, apply fixes only        |
| `--fix-source`      | `auto`         | Fix strategy: auto, llm, heuristic     |
| `--dry-run`         | false          | Preview changes (no writes)            |
| `--llm-model`       | from config    | LLM model to use                       |

---

### `pipeline` — Full End-to-End Workflow

Runs the complete ORCA pipeline in one command: audit → solution → fix → report.

```bash
# Full pipeline with defaults
python main.py pipeline --codebase-path ./src

# Pipeline with LLM analysis
python main.py pipeline --codebase-path ./src --audit-llm

# Pipeline with auto-fix enabled
python main.py pipeline --codebase-path ./src --auto-fix

# Pipeline with HITL review
python main.py pipeline --codebase-path ./src --hitl-review

# Pipeline with everything enabled
python main.py pipeline --codebase-path ./src --audit-llm --auto-fix --hitl-review --full-report
```

**Pipeline steps:**

| Step | Phase                  | Default  | Flag               |
|------|------------------------|----------|--------------------|
| 1    | Static Analysis        | always   | —                  |
| 2    | LLM Semantic Audit     | off      | `--audit-llm`      |
| 3    | Solution Generation    | on       | `--generate-solutions` |
| 4    | Fix Application        | off      | `--auto-fix` or `--hitl-review` |
| 5    | Report Generation      | all      | `--full-report`    |

---

### `fix` — Apply Automated Fixes

Runs an audit and applies automated fixes to findings.

```bash
# Dry-run (default: shows what would be fixed)
python main.py fix --codebase-path ./src

# Actually apply fixes
python main.py fix --codebase-path ./src --apply

# Fix only style violations
python main.py fix --codebase-path ./src --fix-domain style --apply

# Fix based on prior audit results
python main.py fix --codebase-path ./src --findings-file out/compliance_report.json --apply

# Fix and re-audit to verify
python main.py fix --codebase-path ./src --apply --audit-after
```

---

### `patch-audit` — Audit Patch Files

Audits patch files or patch series for compliance with submission guidelines.

```bash
# Audit a single patch
python main.py patch-audit --codebase-path ./src --patch-file my_change.patch

# Audit a patch series directory
python main.py patch-audit --codebase-path ./src --patch-series-dir ./patches/

# Check only patch formatting (skip code analysis)
python main.py patch-audit --codebase-path ./src --patch-file my.patch --format-only
```

---

### `solution` — Generate Fix Recommendations

Generates detailed fix recommendations for each finding from a prior audit.

```bash
# Generate solutions from audit output
python main.py solution --findings-file out/compliance_report.json

# Specify output format
python main.py solution --findings-file out/compliance_report.json --solution-format markdown

# Custom confidence threshold
python main.py solution --findings-file out/compliance_report.json --min-confidence 0.7
```

---

### `report` — Generate Reports

Generates reports from a prior audit's findings JSON.

```bash
# Generate all report formats
python main.py report --findings-file out/compliance_report.json --format all

# Generate only HTML dashboard
python main.py report --findings-file out/compliance_report.json --format html

# Custom output directory
python main.py report --findings-file out/compliance_report.json --out-dir ./reports
```

**Available formats:**

| Format  | Output File                     | Description                     |
|---------|----------------------------------|---------------------------------|
| `json`  | `compliance_report.json`        | Machine-readable findings       |
| `excel` | `compliance_review.xlsx`        | Formatted spreadsheet           |
| `html`  | `compliance_dashboard.html`     | Interactive web dashboard       |
| `all`   | All three above                 | Generate everything             |

---

### `hitl` — Manage Feedback Database

Manage the Human-in-the-Loop feedback store (PostgreSQL).

```bash
# First-time setup: install PostgreSQL, create db, schema, tables
python db/bootstrap_db.py

# Migrate from an existing SQLite database
python db/setup_db.py --migrate-from ./orca_feedback.db

# View decision statistics
python main.py hitl --stats

# Export decisions to JSON
python main.py hitl --export decisions.json

# Import decisions from JSON
python main.py hitl --import-file decisions.json
```

---

## Architecture

ORCA is built on a modular, layered architecture with context-aware analysis for pre-analyzing code structure:

```
┌──────────────────────────────────────────────────────────┐
│  CLI (main.py)  +  Fixer Workflow (fixer_workflow.py)    │
├──────────────────────────────────────────────────────────┤
│  Pipeline Orchestrator                                   │
├──────────┬──────────┬──────────┬──────────┬─────────────┤
│  Static  │  Audit   │ Solution │  Fixer   │  Batch      │
│  Agent   │  Agent   │  Agent   │  Agent   │  Patch      │
├──────────┴──────────┴──────────┴──────────┴─────────────┤
│  Context Layer (2 modules)                               │
│  ├─ HeaderContextBuilder      (#include, enums, macros)  │
│  └─ CodebaseConstraintGen     (auto-gen constraints)     │
├──────────┬──────────┬──────────┬──────────┬─────────────┤
│  Analyzers (7)                │  Adapters (7)            │
│  ├─ StyleAnalyzer             │  ├─ CheckpatchAdapter    │
│  ├─ LicenseAnalyzer           │  ├─ SPDXAdapter          │
│  ├─ WhitespaceAnalyzer        │  ├─ IncludeGuardAdapter  │
│  ├─ IncludeAnalyzer           │  ├─ CommitMessageAdapter │
│  ├─ MacroAnalyzer             │  ├─ StructureAdapter     │
│  ├─ CommitAnalyzer            │  ├─ ExcelReportAdapter   │
│  └─ StructureAnalyzer         │  └─ BaseComplianceAdapter│
├──────────────────────────────┬────────────────────────────┤
│  HITL + Fixer Workflow                                    │
├───────────────────────────────────────────────────────────┤
│  Config Parser │ File Processor │ LLM Tools │ Reports    │
└───────────────────────────────────────────────────────────┘
```

### Context Layer

The context system provides 2 modules that pre-analyze code structure and reduce LLM false positives:

| Module | Purpose |
|--------|---------|
| HeaderContextBuilder | Resolves #include chains, parses headers for enums/structs/macros/typedefs/function prototypes/extern vars |
| CodebaseConstraintGenerator | Auto-generates constraint .md files from enums, structs, macros, bitmasks, and validator functions |

### User-Defined Constraints

ORCA supports user-defined constraint markdown files that are injected into LLM prompts for both analysis and fix generation. Place constraint files in the `constraints/` directory (or specify with `--constraints-dir`).

**File naming convention:**

| File | Scope | Description |
|------|-------|-------------|
| `common_constraints.md` or `sample_constraints.md` | Global | Applied to ALL domains — loaded first by every agent |
| `{domain}_constraints.md` or `{domain}.md` | Domain-specific | Applied only when auditing/fixing that domain (e.g., `style_constraints.md`) |

Agents load common constraints first, then domain-specific constraints, and concatenate both into the LLM prompt. This ensures the LLM respects project-wide rules (e.g., pointer validation patterns, performance constraints) alongside domain-specific guidance.

A default file is provided at `constraints/common_constraints.md` with open-source C/C++ compliance constraints covering all four domains (style, license, structure, patch), plus cross-cutting rules for confidence levels, false-positive avoidance, fix generation, and severity classification.

### Analyzers

Seven static analyzers perform regex/heuristic checks across four compliance domains:

| Analyzer            | Domain     | Rules Checked | Key Checks                                    |
|---------------------|------------|:-------------:|-----------------------------------------------|
| `StyleAnalyzer`     | style      | STYLE-001–007 | Indentation, line length, braces, naming       |
| `LicenseAnalyzer`   | license    | LICENSE-001–006 | SPDX headers, copyright, allowed licenses    |
| `WhitespaceAnalyzer`| style      | WHITESPACE-001–006 | Trailing spaces, mixed tabs, line endings |
| `MacroAnalyzer`     | style      | MACRO-001–004 | do-while wrappers, paren args, naming         |
| `IncludeAnalyzer`   | structure  | INCLUDE-001–003 | Include order, depth, circular deps          |
| `CommitAnalyzer`    | patch      | COMMIT-001–009 | Subject format, Signed-off-by, DCO           |
| `StructureAnalyzer` | structure  | STRUCT-001–006 | File naming, extern in .c, header matching   |

All analyzers inherit from `BaseAnalyzer` and share the signature `__init__(rules, config)`.

### Adapters

Seven adapters integrate external tools and extend analysis capabilities:

| Adapter                 | Purpose                             | External Tool     |
|-------------------------|-------------------------------------|-------------------|
| `CheckpatchAdapter`     | Linux kernel style checking         | checkpatch.pl     |
| `SPDXAdapter`           | License compliance validation       | Built-in DB (50+) |
| `IncludeGuardAdapter`   | Header include guard validation     | Built-in          |
| `CommitMessageAdapter`  | Commit message format validation    | gitlint (optional)|
| `StructureAdapter`      | Code organization analysis          | Built-in          |
| `ExcelReportAdapter`    | Excel report generation             | openpyxl          |
| `BaseComplianceAdapter` | Abstract base for custom adapters   | —                 |

### Agents

Seven agents orchestrate different phases of the compliance workflow:

| Agent                     | Role                                          | LLM Required? |
|---------------------------|-----------------------------------------------|:-------------:|
| `ComplianceStaticAgent`   | 7-phase static analysis pipeline              | No            |
| `ComplianceAuditAgent`    | LLM-powered semantic compliance analysis      | Yes           |
| `ComplianceSolutionAgent` | Fix recommendation generation                 | Yes           |
| `ComplianceFixerAgent`    | Automated code remediation                    | No            |
| `CompliancePatchAgent`    | Patch/diff format auditing                    | No            |
| `ComplianceBatchPatchAgent` | Multi-file batch patch application          | No            |
| `ComplianceChatAgent`     | Conversational analysis chat interface        | Yes           |

### HITL (Human-in-the-Loop)

The HITL system provides feedback persistence and learning:

| Component          | Description                                                   |
|--------------------|---------------------------------------------------------------|
| `FeedbackStore`    | PostgreSQL-backed decision store (FIX, SKIP, WAIVE, etc.)    |
| `RAGRetriever`     | Retrieves past decisions as context for new findings          |
| `ConstraintParser` | Parses markdown constraint files for automated decision logic |

---

## Rules Presets

ORCA ships with four built-in rules presets:

| Preset   | Target              | Style      | Line Limit | License Default     |
|----------|---------------------|------------|:----------:|---------------------|
| `kernel` | Linux Kernel        | Tabs (8)   | 80         | GPL-2.0-only        |
| `uboot`  | Das U-Boot          | Tabs (8)   | 80/120     | GPL-2.0-or-later    |
| `yocto`  | Yocto/OpenEmbedded  | Spaces (4) | 200        | GPL-2.0-only        |
| `custom` | User-defined        | Any        | Any        | Any                 |

### Writing Custom Rules

Create a YAML file based on `rules/custom.yaml`:

```yaml
project:
  name: "My Project"
  version: "1.0"

style:
  indentation: "spaces"
  tab_width: 4
  line_length: 120
  brace_style: "kr"
  naming:
    functions: "snake_case"
    variables: "camelCase"

license:
  required_spdx: true
  default_license: "Apache-2.0"
  allowed_licenses:
    - "Apache-2.0"
    - "MIT"
    - "BSD-3-Clause"

structure:
  include_guard_style: "ifndef"
  no_extern_in_c: true

patch:
  require_signed_off_by: false
  subject_max_length: 72
```

Use it: `python main.py audit --codebase-path ./src --rules-file my_rules.yaml`

---

## Extending ORCA

ORCA's plugin architecture makes it straightforward to extend for non-open-source domains such as MISRA-C (automotive), CERT C (security), or proprietary corporate standards.

### Adding a Custom Analyzer

Create a new analyzer by subclassing `BaseAnalyzer`:

```python
from agents.analyzers.base_analyzer import BaseAnalyzer, Finding

class MISRAAnalyzer(BaseAnalyzer):
    """MISRA-C compliance analyzer for automotive/safety-critical code."""

    def analyze(self, file_path: str, content: str) -> list:
        findings = []
        # Your MISRA rule checks here
        findings.append(self._make_finding(
            file_path=file_path,
            line_number=10,
            rule_id="MISRA-11.3",
            severity="high",
            message="Cast between pointer and integer type",
            category="misra",
        ))
        return findings
```

Register it in `ComplianceStaticAgent` to include it in the pipeline.

### Adding a Custom Adapter

Wrap an external tool by subclassing `BaseComplianceAdapter`:

```python
from agents.adapters.base_adapter import BaseComplianceAdapter, AdapterResult

class CoverityAdapter(BaseComplianceAdapter):
    """Adapter for Coverity static analysis tool."""

    def analyze(self, file_cache, **kwargs) -> AdapterResult:
        # Run Coverity, parse results, return findings
        return AdapterResult(
            score=85, grade="B", domain="security",
            findings=[...],
            summary="Coverity scan complete",
            tool_available=True, tool_name="coverity",
        )
```

### Adding a Custom Rules Preset

Create a new YAML file in `rules/` following the structure of `linux_kernel.yaml`, then use it with `--rules-file rules/my_rules.yaml` or add it to the `preset_map` in `main.py`.

---

## Project Structure

```
ORCA/
├── main.py                    # CLI entry point and pipeline orchestrator
├── fixer_workflow.py          # HITL fixer workflow orchestrator
├── ui/
│   └── app.py                 # Streamlit web UI dashboard
├── config.yaml                # Default configuration (all options documented)
├── env.example                # Environment variable template (cp to .env)
├── global_config.yaml         # Legacy config (auto-detected)
├── db/
│   ├── bootstrap_db.py        # Full PostgreSQL bootstrap (install + setup)
│   └── setup_db.py            # PostgreSQL schema setup & migration (advanced)
├── constraints/               # User-defined constraint files for LLM injection
│   └── common_constraints.md  #   Open-source C/C++ compliance constraints (all domains)
├── requirements.txt           # Python dependencies
├── setup.py                   # Package installer
│
├── agents/
│   ├── analyzers/             # 7 static analyzers
│   │   ├── base_analyzer.py   #   BaseAnalyzer, Finding, ComplianceReport
│   │   ├── style_analyzer.py
│   │   ├── license_analyzer.py
│   │   ├── whitespace_analyzer.py
│   │   ├── include_analyzer.py
│   │   ├── macro_analyzer.py
│   │   ├── commit_analyzer.py
│   │   └── structure_analyzer.py
│   ├── adapters/              # 7 external tool adapters
│   │   ├── base_adapter.py    #   BaseComplianceAdapter, AdapterResult
│   │   ├── checkpatch_adapter.py
│   │   ├── spdx_adapter.py
│   │   ├── include_guard_adapter.py
│   │   ├── commit_message_adapter.py
│   │   ├── structure_adapter.py
│   │   └── excel_report_adapter.py
│   ├── context/               # Context-aware analysis modules
│   │   ├── __init__.py
│   │   ├── header_context_builder.py    # #include resolution, header parsing
│   │   └── codebase_constraint_generator.py  # Auto-gen constraint .md from symbols
│   ├── core/                  # Shared infrastructure
│   │   ├── file_processor.py  #   File discovery and metadata
│   │   └── compliance_calculator.py
│   ├── parsers/               # Report and patch parsers
│   │   ├── patch_parser.py
│   │   └── report_parser.py   #   JSON, HTML dashboard generators
│   ├── prompts/               # LLM prompt templates
│   │   ├── style_prompts.py
│   │   ├── license_prompts.py
│   │   ├── structure_prompts.py
│   │   ├── patch_prompts.py
│   │   └── solution_prompts.py
│   ├── compliance_static_agent.py        # 7-phase static pipeline
│   ├── compliance_audit_agent.py         # LLM semantic auditor
│   ├── compliance_solution_agent.py      # Fix recommendation generator
│   ├── compliance_fixer_agent.py         # Automated remediation
│   ├── compliance_patch_agent.py         # Patch/diff auditor
│   ├── compliance_batch_patch_agent.py   # Batch patch applicator
│   └── compliance_chat_agent.py          # Conversational chat interface
│
├── hitl/                      # Human-in-the-Loop system
│   ├── feedback_store.py      #   PostgreSQL decision store
│   ├── rag_retriever.py       #   RAG context retrieval
│   └── constraint_parser.py   #   Markdown constraint parser
│
├── rules/                     # Compliance rule presets
│   ├── linux_kernel.yaml
│   ├── uboot.yaml
│   ├── yocto.yaml
│   └── custom.yaml
│
├── utils/                     # Utility modules
│   ├── config_parser.py       #   YAML config + env var interpolation
│   ├── file_utils.py          #   Safe file I/O utilities
│   ├── llm_tools.py           #   LLM client abstraction (base)
│   ├── llm_tools_anthropic.py #   Anthropic LLM provider
│   ├── llm_tools_openai.py    #   OpenAI LLM provider
│   ├── llm_tools_qgenie.py    #   QGenie LLM provider
│   ├── llm_tools_mock.py      #   Mock LLM provider
│   └── excel_writer.py        #   Excel generation utilities
│
├── tests/                     # Test suite
│   ├── test_analyzers.py
│   ├── test_adapters.py
│   ├── test_hitl.py
│   ├── test_integration.py
│   └── fixtures/              #   Sample good/bad C files, patches
│
└── docs/
    ├── ORCA_Architecture_Design_Document.docx
    └── ORCA_Pitch_Deck.pptx
```

---

## Technology Stack

| Component       | Technology                  | Purpose                          |
|----------------|-----------------------------|----------------------------------|
| Language        | Python 3.9+                 | Core framework                   |
| Config          | PyYAML 6.0+                 | YAML configuration parsing       |
| Reports         | openpyxl 3.1+               | Excel report generation          |
| Database        | PostgreSQL + psycopg2       | HITL feedback persistence        |
| Data Models     | dataclasses (stdlib)        | Type-safe configuration/findings |
| Analysis        | re, ast (stdlib)            | Regex/heuristic static analysis  |
| LLM Tools       | Multi-provider abstraction  | Anthropic, OpenAI, QGenie        |
| LLM (optional)  | anthropic / openai SDKs     | Semantic analysis and solutions  |

---

## Running Tests

```bash
# Run all tests
python -m unittest discover -s tests -v

# Run specific test modules
python -m unittest tests.test_analyzers -v
python -m unittest tests.test_adapters -v
python -m unittest tests.test_hitl -v
python -m unittest tests.test_integration -v
```

---

## Project Metrics

- **69 Python modules** across 8 packages
- **~16,000 lines of code**
- **41 compliance rules** across 7 analyzers
- **7 external tool adapters**
- **7 compliance agents** (including batch patch and chat)
- **2 context modules** (HeaderContextBuilder, CodebaseConstraintGenerator)
- **4 rules presets** (kernel, uboot, yocto, custom)
- **3 report formats** (JSON, Excel, HTML dashboard)
- **3 LLM providers** (Anthropic, OpenAI, QGenie)

---

## License

See `LICENSES/` directory for applicable licenses.
