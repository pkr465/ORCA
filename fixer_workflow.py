"""
ORCA Fixer Workflow — Human-In-The-Loop Automated Compliance Repair.

Orchestrates the full repair pipeline:

**Fixer mode** (default):
    Excel (human-reviewed) → Parse directives → ComplianceFixerAgent

**Patch mode** (--patch-file + --patch-target):
    Step 1: CompliancePatchAgent → detailed_code_review.xlsx (patch_* tabs)
    Step 2: Parse patch directives → ComplianceFixerAgent → fix & validate

**Batch-patch mode** (--batch-patch):
    Step 1: ComplianceBatchPatchAgent → detailed_code_review.xlsx (patch_* tabs)
    Step 2: Parse patch directives → ComplianceFixerAgent → fix & validate

Use --analyse-only to stop after Step 1 (analysis) without applying fixes.
Use --fix-only to skip analysis and run the fixer directly from a pre-existing Excel.
"""

import os
import sys
import argparse
from pathlib import Path

# Ensure project root is on path
ORCA_ROOT = os.path.dirname(os.path.abspath(__file__))
if ORCA_ROOT not in sys.path:
    sys.path.insert(0, ORCA_ROOT)

# Import helper classes (graceful when unavailable)
try:
    from agents.parsers.excel_to_agent_parser import ExcelToAgentParser
    _EXCEL_PARSER_AVAILABLE = True
except ImportError:
    _EXCEL_PARSER_AVAILABLE = False

try:
    from agents.compliance_fixer_agent import ComplianceFixerAgent
    _FIXER_AVAILABLE = True
except ImportError:
    _FIXER_AVAILABLE = False

try:
    from utils.llm_tools import LLMTools
    _LLM_AVAILABLE = True
except ImportError:
    _LLM_AVAILABLE = False

try:
    from utils.config_parser import load_config, GlobalConfig
    _CONFIG_AVAILABLE = True
except ImportError:
    _CONFIG_AVAILABLE = False


class HumanInTheLoopWorkflow:
    """
    Orchestrator for the ORCA Automated Compliance Repair Workflow.

    All three modes follow the same two-step pipeline:

    **Step 1 — Analyse**: Identify issues (from Excel review, patch analysis,
    or batch patch analysis).

    **Step 2 — Fix**: Parse findings + human feedback from Excel → generate
    JSONL directives → run ``ComplianceFixerAgent`` to apply fixes → validate →
    write patched files to ``out/patched_files/`` → generate audit report.

    Modes
    -----
    1. **Fixer mode** (default):
       Excel (human-reviewed) → Parse directives → ComplianceFixerAgent

    2. **Patch mode** (``--patch-file`` + ``--patch-target``):
       Step 1: CompliancePatchAgent → ``detailed_code_review.xlsx`` (patch_* tabs)
       Step 2: Parse patch directives → ComplianceFixerAgent → fix & validate

    3. **Batch-patch mode** (``--batch-patch``):
       Step 1: ComplianceBatchPatchAgent → ``detailed_code_review.xlsx`` (patch_* tabs)
       Step 2: Parse patch directives → ComplianceFixerAgent → fix & validate
    """

    def __init__(self, args):
        """Initialize the workflow with parsed CLI arguments."""
        self.args = args
        self.workspace_dir = Path(args.out_dir).resolve()

        # Mode flags
        self.batch_patch_file = getattr(args, "batch_patch", None)
        self.patch_file = getattr(args, "patch_file", None)
        self.patch_target = getattr(args, "patch_target", None)
        self.analyse_only = getattr(args, "analyse_only", False)
        self.fix_only = getattr(args, "fix_only", False)

        # Excel-related paths
        is_patch_mode = self.batch_patch_file or (self.patch_file and self.patch_target)
        if is_patch_mode:
            self.excel_path = Path(args.excel_file).resolve() if self.fix_only else None
        else:
            self.excel_path = Path(args.excel_file).resolve()

        self.directives_jsonl = self.workspace_dir / "agent_directives.jsonl"
        self.final_report = self.workspace_dir / "final_execution_audit.xlsx"

        # Initialize GlobalConfig
        self.global_config = self._initialize_global_config()

        # Resolve codebase_root: CLI arg → GlobalConfig → default
        cli_codebase = args.codebase_path
        if cli_codebase == "codebase" and self.global_config:
            config_path = (
                self.global_config.get_path("paths.code_base_path")
                if hasattr(self.global_config, "get_path")
                else None
            )
            if config_path:
                cli_codebase = config_path
        self.codebase_root = Path(cli_codebase).resolve()

        # Resolve constraints directory
        self.constraints_dir = getattr(args, "constraints_dir", None)
        if not self.constraints_dir and self.global_config:
            self.constraints_dir = (
                self.global_config.get("context", {}).get("constraints_dir")
                if isinstance(self.global_config, dict)
                else None
            )
        if not self.constraints_dir:
            self.constraints_dir = "./constraints"

        # Ensure workspace exists
        os.makedirs(self.workspace_dir, exist_ok=True)

    # ─── Shared helpers ──────────────────────────────────────────────

    def _build_llm_tools(self):
        """Resolve LLM model and build LLMTools instance.

        Resolution order: --llm-model CLI arg → global_config.yaml → default.
        """
        if not _LLM_AVAILABLE:
            if self.args.verbose:
                print("    [WARNING] LLMTools not available")
            return None

        llm_model = getattr(self.args, "llm_model", None)
        if not llm_model and self.global_config:
            try:
                llm_model = (
                    self.global_config.get("llm.model")
                    if hasattr(self.global_config, "get")
                    else None
                )
            except Exception:
                llm_model = None
        try:
            return LLMTools(model=llm_model) if llm_model else LLMTools()
        except Exception as e:
            if self.args.verbose:
                print(f"    [WARNING] LLMTools init failed: {e}")
            return None

    def _initialize_global_config(self):
        """Load GlobalConfig from default or custom config file."""
        if not _CONFIG_AVAILABLE:
            return None
        try:
            config_file = getattr(self.args, "config_file", None)
            if config_file:
                return GlobalConfig(config_file=config_file)
            # Try default config paths
            for path in [
                os.path.join(ORCA_ROOT, "config.yaml"),
                os.path.join(ORCA_ROOT, "global_config.yaml"),
            ]:
                if os.path.exists(path):
                    return load_config(path)
            return None
        except Exception as e:
            if self.args.verbose:
                print(f"    [WARNING] Could not load GlobalConfig: {e}")
            return None

    # ─── Shared fix pipeline (Step 2) ────────────────────────────────

    def _step_parse_and_fix(
        self,
        excel_path: str,
        fix_source: str = "patch",
        step_prefix: str = "Step 2",
    ) -> dict:
        """Parse findings from Excel and run ComplianceFixerAgent to apply fixes.

        Args:
            excel_path: Path to detailed_code_review.xlsx with findings.
            fix_source: Which sheets to parse — "patch", "llm", "static", or "all".
            step_prefix: Label prefix for console output.

        Returns:
            dict with fixer agent results, or empty dict on failure.
        """
        if not _EXCEL_PARSER_AVAILABLE:
            print("    [!] Error: ExcelToAgentParser not available")
            return {}

        # -- Step 2a: Parse Excel into directives ──────────────────────────
        print(f"\n[{step_prefix}a] Parsing Findings from Excel: {Path(excel_path).name}")
        print(f"    Fix source filter: {fix_source}")

        excel_p = Path(excel_path)
        if not excel_p.exists():
            print(f"    [!] Error: Excel file not found: {excel_p}")
            return {}

        try:
            parser = ExcelToAgentParser(str(excel_p))
            directive_count = parser.generate_agent_directives(
                str(self.directives_jsonl),
                fix_source=fix_source,
            )

            if not self.directives_jsonl.exists() or directive_count == 0:
                print("    [!] No actionable directives found — nothing to fix.")
                print(
                    "    Tip: Review the Excel and add Feedback/Constraints "
                    "columns to guide the fixer."
                )
                return {}

            print(
                f"    [OK] Directives generated: {self.directives_jsonl} "
                f"({directive_count} directives)"
            )

        except Exception as e:
            print(f"    [!] Exception during Excel parsing: {e}")
            if self.args.verbose:
                import traceback

                traceback.print_exc()
            return {}

        # -- Step 2b: Run ComplianceFixerAgent ─────────────────────────────
        print(f"\n[{step_prefix}b] Launching Fixer Agent")
        print(f"    Target Codebase: {self.codebase_root}")
        print(f"    Source Filter:   {fix_source}")

        if not _FIXER_AVAILABLE:
            print("    [!] Error: ComplianceFixerAgent not available")
            return {}

        try:
            llm_tools = self._build_llm_tools()
            agent = ComplianceFixerAgent(
                codebase_root=str(self.codebase_root),
                output_dir=str(self.workspace_dir),
                config=self.global_config or {},
                llm_tools=llm_tools,
                rules={},
                dry_run=self.args.dry_run,
                verbose=self.args.verbose,
                backup_dir=str(self.workspace_dir / "shelved_backups"),
                constraints_dir=self.constraints_dir,
            )

            # Load directives and run
            import json

            findings = []
            with open(self.directives_jsonl, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        findings.append(json.loads(line))

            result = agent.run_fixes(findings)

            if result:
                files_done = len(result)
                total_fixed = sum(r.fixed_count for r in result.values())
                print(
                    f"\n    Fixer Agent: {files_done} file(s) processed, "
                    f"{total_fixed} fixes applied"
                )
                print(f"    Audit report: {self.final_report}")

            return result or {}

        except Exception as e:
            print(f"    [!] Exception during fixer agent execution: {e}")
            if self.args.verbose:
                import traceback

                traceback.print_exc()
            return {}

    # ─── Dispatcher ──────────────────────────────────────────────────

    def execute(self):
        """Execute the workflow. Dispatches to the appropriate mode."""
        if self.patch_file and self.patch_target:
            return self._execute_patch_workflow()
        if self.batch_patch_file:
            return self._execute_batch_patch_workflow()
        return self._execute_fixer()

    # ─── Patch workflow (single-file) ────────────────────────────────

    def _execute_patch_workflow(self):
        """Two-step pipeline for single-file patch analysis and fixing."""
        total_steps = "2" if not self.analyse_only and not self.fix_only else "1"

        print("=" * 60)
        print(" ORCA Patch Analyse & Fix Workflow")
        print("=" * 60)

        excel_path = str(self.workspace_dir / "detailed_code_review.xlsx")

        # -- Step 1: Analyse ───────────────────────────────────────────────
        if not self.fix_only:
            patch_path = Path(self.patch_file).resolve()
            target_path = Path(self.patch_target).resolve()

            if not patch_path.exists():
                print(f"[!] Error: Patch file does not exist: {patch_path}")
                return
            if not target_path.exists():
                print(f"[!] Error: Target source file does not exist: {target_path}")
                return

            print(f"\n[Step 1/{total_steps}] Patch Analysis")
            print(f"    Target file: {target_path}")
            print(f"    Patch file:  {patch_path}")

            try:
                from agents.compliance_patch_agent import CompliancePatchAgent
            except ImportError as e:
                print(f"[!] Error: Could not import CompliancePatchAgent: {e}")
                return

            llm_tools = self._build_llm_tools()

            # Resolve codebase path for header/context resolution
            patch_codebase = getattr(self.args, "patch_codebase_path", None)
            if not patch_codebase:
                if self.codebase_root.exists() and str(self.codebase_root) != str(
                    Path("codebase").resolve()
                ):
                    patch_codebase = str(self.codebase_root)
                else:
                    patch_codebase = str(target_path.parent)

            enable_adapters = getattr(self.args, "enable_adapters", False)

            try:
                agent = CompliancePatchAgent(
                    file_path=str(target_path),
                    patch_file=str(patch_path),
                    output_dir=str(self.workspace_dir),
                    config=self.global_config or {},
                    llm_tools=llm_tools,
                    enable_adapters=enable_adapters,
                    verbose=self.args.verbose,
                    codebase_path=patch_codebase,
                )

                result = agent.run_analysis(excel_path=excel_path)

                print(f"\n    Analysis Complete:")
                print(f"    Original issues: {result.get('original_issue_count', 0)}")
                print(f"    Patched issues:  {result.get('patched_issue_count', 0)}")
                print(f"    NEW issues:      {result.get('new_issue_count', 0)}")
                print(f"    Excel output:    {result.get('excel_path', 'N/A')}")

                excel_path = result.get("excel_path", excel_path)

            except Exception as e:
                print(f"    [!] Patch Analysis failed: {e}")
                if self.args.verbose:
                    import traceback

                    traceback.print_exc()
                return

            if self.analyse_only:
                print("\n" + "=" * 60)
                print(" PATCH ANALYSIS COMPLETE (--analyse-only)")
                print(f" Excel: {excel_path}")
                print("=" * 60)
                return

        else:
            excel_path = str(self.excel_path) if self.excel_path else excel_path
            print(f"\n[--fix-only] Skipping analysis, reading from: {excel_path}")

        # -- Step 2: Fix ──────────────────────────────────────────────────
        fix_source = getattr(self.args, "fix_source", "patch")
        self._step_parse_and_fix(
            excel_path=excel_path,
            fix_source=fix_source,
            step_prefix=f"Step 2/{total_steps}",
        )

        print("\n" + "=" * 60)
        print(" ORCA PATCH ANALYSE & FIX COMPLETE")
        print(f" Report: {self.final_report}")
        print(f" Patched files: {self.workspace_dir / 'patched_files'}")
        print("=" * 60)

    # ─── Batch-patch workflow (multi-file) ────────────────────────────

    def _execute_batch_patch_workflow(self):
        """Two-step pipeline for multi-file batch patch analysis and fixing."""
        total_steps = "2" if not self.analyse_only and not self.fix_only else "1"

        print("=" * 60)
        print(" ORCA Batch Patch Analyse & Fix Workflow")
        print("=" * 60)

        excel_path = str(self.workspace_dir / "detailed_code_review.xlsx")

        # -- Step 1: Analyse ───────────────────────────────────────────────
        if not self.fix_only:
            patch_path = Path(self.batch_patch_file).resolve()

            if not patch_path.exists():
                print(f"[!] Error: Patch file does not exist: {patch_path}")
                return
            if not self.codebase_root.exists():
                print(f"[!] Error: Codebase path does not exist: {self.codebase_root}")
                return

            print(f"\n[Step 1/{total_steps}] Batch Patch Analysis")
            print(f"    Patch file: {patch_path}")
            print(f"    Codebase:   {self.codebase_root}")

            try:
                from agents.compliance_batch_patch_agent import ComplianceBatchPatchAgent
            except ImportError as e:
                print(f"[!] Error: Could not import ComplianceBatchPatchAgent: {e}")
                return

            llm_tools = self._build_llm_tools()
            enable_adapters = getattr(self.args, "enable_adapters", False)

            try:
                agent = ComplianceBatchPatchAgent(
                    patch_file=str(patch_path),
                    codebase_path=str(self.codebase_root),
                    output_dir=str(self.workspace_dir),
                    config=self.global_config or {},
                    llm_tools=llm_tools,
                    enable_adapters=enable_adapters,
                    dry_run=self.args.dry_run,
                    verbose=self.args.verbose,
                )

                result = agent.run(excel_path=excel_path)

                print(f"\n    Analysis Complete:")
                print(f"    Files analysed:  {result.get('patched', 0)}")
                print(f"    Original issues: {result.get('original_issue_count', 0)}")
                print(f"    Patched issues:  {result.get('patched_issue_count', 0)}")
                print(f"    NEW issues:      {result.get('new_issue_count', 0)}")
                print(f"    Excel output:    {result.get('excel_path', 'N/A')}")

                excel_path = result.get("excel_path", excel_path)

            except Exception as e:
                print(f"    [!] Batch Patch Analysis failed: {e}")
                if self.args.verbose:
                    import traceback

                    traceback.print_exc()
                return

            if self.analyse_only:
                print("\n" + "=" * 60)
                print(" BATCH PATCH ANALYSIS COMPLETE (--analyse-only)")
                print(f" Excel: {excel_path}")
                print("=" * 60)
                return

        else:
            excel_path = str(self.excel_path) if self.excel_path else excel_path
            print(f"\n[--fix-only] Skipping analysis, reading from: {excel_path}")

        # -- Step 2: Fix ──────────────────────────────────────────────────
        fix_source = getattr(self.args, "fix_source", "patch")
        self._step_parse_and_fix(
            excel_path=excel_path,
            fix_source=fix_source,
            step_prefix=f"Step 2/{total_steps}",
        )

        print("\n" + "=" * 60)
        print(" ORCA BATCH PATCH ANALYSE & FIX COMPLETE")
        print(f" Report: {self.final_report}")
        print(f" Patched files: {self.workspace_dir / 'patched_files'}")
        print("=" * 60)

    # ─── Fixer mode (default) ────────────────────────────────────────

    def _execute_fixer(self):
        """Default workflow: parse Excel → run ComplianceFixerAgent."""
        print("=" * 60)
        print(" ORCA Automated Compliance Repair Workflow")
        print("=" * 60)

        # Validate inputs before starting
        if not self.codebase_root.exists():
            print(f"[!] Error: Codebase path does not exist: {self.codebase_root}")
            return
        if not self.excel_path or not self.excel_path.exists():
            print(f"[!] Error: Excel file does not exist: {self.excel_path}")
            return

        fix_source = getattr(self.args, "fix_source", "all")
        self._step_parse_and_fix(
            excel_path=str(self.excel_path),
            fix_source=fix_source,
            step_prefix="Step 1/1",
        )

        print("\n" + "=" * 60)
        print(" WORKFLOW COMPLETE")
        print(f" Report: {self.final_report}")
        print("=" * 60)


# ═════════════════════════════════════════════════════════════════════════
#  Command Line Interface
# ═════════════════════════════════════════════════════════════════════════


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="ORCA Automated Compliance Repair Workflow using Human Feedback.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # --- File Paths ---
    parser.add_argument(
        "--excel-file",
        default="out/detailed_code_review.xlsx",
        help="Path to the reviewed Excel file (fixer mode, or --fix-only)",
    )
    parser.add_argument(
        "--batch-patch",
        default=None,
        metavar="PATCH_FILE",
        help="Path to a multi-file patch file.",
    )
    parser.add_argument(
        "--patch-file",
        default=None,
        help="Path to a .patch/.diff file for single-file patch analysis.",
    )
    parser.add_argument(
        "--patch-target",
        default=None,
        help="Path to the original source file being patched.",
    )
    parser.add_argument(
        "--patch-codebase-path",
        default=None,
        help="Root of the codebase for header/context resolution.",
    )
    parser.add_argument(
        "--enable-adapters",
        action="store_true",
        help="Enable deep static analysis adapters (checkpatch, SPDX, include-guard).",
    )
    parser.add_argument(
        "--codebase-path",
        default="codebase",
        help="Root directory of the source code.",
    )
    parser.add_argument(
        "--out-dir",
        default="out",
        help="Directory for output/patched files.",
    )
    parser.add_argument(
        "--config-file",
        default=None,
        help="Path to custom config.yaml file.",
    )

    # --- Pipeline Control ---
    pipeline_group = parser.add_argument_group("Pipeline Control")
    pipeline_group.add_argument(
        "--analyse-only",
        action="store_true",
        help="Run only the analysis step without applying fixes.",
    )
    pipeline_group.add_argument(
        "--fix-only",
        action="store_true",
        help="Skip analysis and run the fixer directly from pre-existing Excel.",
    )

    # --- Source Filtering ---
    parser.add_argument(
        "--fix-source",
        choices=["all", "llm", "static", "patch"],
        default="patch",
        help="Process only issues from a specific source.",
    )

    # --- LLM Configuration ---
    llm_group = parser.add_argument_group("LLM Configuration")
    llm_group.add_argument(
        "--llm-model",
        default=None,
        help="LLM model in 'provider::model' format.",
    )
    llm_group.add_argument(
        "--llm-api-key",
        default=None,
        help="API Key (overrides env vars).",
    )
    llm_group.add_argument(
        "--llm-max-tokens",
        type=int,
        default=15000,
        help="Token limit for context.",
    )
    llm_group.add_argument(
        "--llm-temperature",
        type=float,
        default=0.1,
        help="Sampling temperature.",
    )

    # --- Safety & Debugging ---
    safe_group = parser.add_argument_group("Safety & Debugging")
    safe_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate fixes without writing to disk.",
    )
    safe_group.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable detailed logging.",
    )
    safe_group.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode.",
    )

    return parser


if __name__ == "__main__":
    cli_parser = build_parser()
    cli_args = cli_parser.parse_args()

    # Validate conflicting flags
    if getattr(cli_args, "analyse_only", False) and getattr(cli_args, "fix_only", False):
        cli_parser.error("--analyse-only and --fix-only are mutually exclusive.")

    # In default fixer mode, override fix_source to 'llm' if user didn't
    # explicitly set it and we're not in a patch mode
    is_patch_mode = cli_args.batch_patch or (cli_args.patch_file and cli_args.patch_target)
    if not is_patch_mode and cli_args.fix_source == "patch":
        cli_args.fix_source = "llm"

    workflow = HumanInTheLoopWorkflow(cli_args)
    workflow.execute()
