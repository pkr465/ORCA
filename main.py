#!/usr/bin/env python3
"""ORCA - Open-source Rules Compliance Auditor.

LLM-powered compliance auditing framework for C/C++ codebases.
Audits coding style, license compliance, patch format, and code structure.

Usage:
    orca audit   --codebase-path ./src
    orca fix     --codebase-path ./src --apply
    orca pipeline --codebase-path ./src
    orca report  --findings-file out/compliance_report.json
    orca hitl    --stats
"""

import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
ORCA_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ORCA_ROOT)

from utils.config_parser import load_config, merge_cli_overrides, GlobalConfig
from utils.file_utils import read_file_safe
from agents.core.file_processor import FileProcessor
from agents.core.compliance_calculator import ComplianceCalculator
from agents.analyzers.base_analyzer import ComplianceReport


logger = logging.getLogger("orca")

# ─── Default config file lookup order ────────────────────────────────────
DEFAULT_CONFIG_PATHS = [
    os.path.join(ORCA_ROOT, "config.yaml"),
    os.path.join(ORCA_ROOT, "global_config.yaml"),
    os.path.expanduser("~/.orca/config.yaml"),
]


# ═════════════════════════════════════════════════════════════════════════
#  Configuration Loading
# ═════════════════════════════════════════════════════════════════════════

def find_default_config() -> Optional[str]:
    """Search for the first available config file in default locations."""
    for path in DEFAULT_CONFIG_PATHS:
        if os.path.isfile(path):
            return path
    return None


def load_effective_config(config_file: str = "") -> Dict[str, Any]:
    """Load configuration from YAML and return as a dict.

    Priority: explicit --config-file > config.yaml > global_config.yaml > defaults
    """
    config_path = config_file or find_default_config()

    if config_path and os.path.isfile(config_path):
        try:
            config_obj = load_config(config_path)
            logger.info(f"Loaded config from {config_path}")
            return config_obj.to_dict()
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")

    # Return empty dict — CLI defaults will be used
    return {}


def cfg_get(cfg: dict, *keys, default=None):
    """Safely traverse nested dict keys, e.g. cfg_get(cfg, 'audit', 'domains')."""
    current = cfg
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return default
        if current is None:
            return default
    return current


# ═════════════════════════════════════════════════════════════════════════
#  Logging
# ═════════════════════════════════════════════════════════════════════════

def setup_logging(verbosity: int, quiet: bool = False):
    """Configure logging based on verbosity level."""
    if quiet:
        level = logging.ERROR
    elif verbosity >= 2:
        level = logging.DEBUG
    elif verbosity >= 1:
        level = logging.INFO
    else:
        level = logging.WARNING

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# ═════════════════════════════════════════════════════════════════════════
#  Argument Parser
# ═════════════════════════════════════════════════════════════════════════

def create_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="orca",
        description=(
            "ORCA - Open-source Rules Compliance Auditor\n"
            "LLM-powered compliance auditing for C/C++ codebases.\n\n"
            "All options have sensible defaults in config.yaml.\n"
            "Override any option via CLI flags."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick audit using defaults from config.yaml
  orca audit --codebase-path ./src

  # Full audit with Linux kernel rules
  orca audit --codebase-path ./src --rules-preset kernel

  # LLM-powered audit for style + license domains
  orca audit --codebase-path ./src --audit-llm --domains style,license

  # Run full pipeline: audit → solutions → fix → report
  orca pipeline --codebase-path ./src

  # Pipeline with HITL and LLM enabled
  orca pipeline --codebase-path ./src --audit-llm --enable-hitl

  # Audit a patch series
  orca patch-audit --patch-series-dir ./patches/ --rules-preset kernel

  # Auto-fix only style violations (dry-run)
  orca fix --codebase-path ./src --fix-domain style

  # Apply fixes (not dry-run)
  orca fix --codebase-path ./src --fix-domain style --apply

  # Generate fix recommendations from prior audit
  orca solution --findings-file out/compliance_report.json

  # Generate reports from prior audit findings
  orca report --findings-file out/compliance_report.json --format all

  # Manage HITL feedback database (PostgreSQL)
  orca hitl --stats

  # Use a custom config file
  orca audit --codebase-path ./src --config-file my_config.yaml
        """,
    )

    # Global flags
    parser.add_argument("--config-file", type=str, default="",
                        help="Path to config YAML (default: config.yaml in project root)")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── AUDIT command ────────────────────────────────────────────────
    audit_parser = subparsers.add_parser(
        "audit", help="Run compliance audit on a codebase")
    _add_common_args(audit_parser)
    _add_audit_args(audit_parser)

    # ── FIX command ──────────────────────────────────────────────────
    fix_parser = subparsers.add_parser(
        "fix", help="Apply automated fixes to findings")
    _add_common_args(fix_parser)
    _add_fix_args(fix_parser)

    # ── PIPELINE command ─────────────────────────────────────────────
    pipeline_parser = subparsers.add_parser(
        "pipeline",
        help="Run full end-to-end pipeline: audit → solution → fix → report")
    _add_common_args(pipeline_parser)
    _add_audit_args(pipeline_parser)
    _add_fix_args(pipeline_parser)
    pipe_grp = pipeline_parser.add_argument_group("Pipeline")
    pipe_grp.add_argument("--generate-solutions", action="store_true", default=None,
                          help="Generate fix recommendations after audit")
    pipe_grp.add_argument("--auto-fix", action="store_true", default=None,
                          help="Auto-apply high-confidence fixes")
    pipe_grp.add_argument("--hitl-review", action="store_true", default=None,
                          help="Enable HITL review before fix application")
    pipe_grp.add_argument("--full-report", action="store_true", default=None,
                          help="Generate all report formats at the end")

    # ── PATCH-AUDIT command ──────────────────────────────────────────
    patch_parser = subparsers.add_parser(
        "patch-audit", help="Audit patch files for compliance")
    _add_common_args(patch_parser)
    patch_parser.add_argument("--patch-file", type=str, default=None,
                              help="Single patch file to audit")
    patch_parser.add_argument("--patch-series-dir", type=str, default=None,
                              help="Directory containing patch series")
    patch_parser.add_argument("--format-only", action="store_true", default=None,
                              help="Only check patch format (skip code analysis)")

    # ── SOLUTION command ─────────────────────────────────────────────
    solution_parser = subparsers.add_parser(
        "solution", help="Generate fix recommendations from audit findings")
    _add_common_args(solution_parser)
    solution_parser.add_argument("--findings-file", type=str, default=None,
                                 help="Path to findings JSON from audit")
    solution_parser.add_argument("--solution-format", type=str, default=None,
                                 choices=["jsonl", "markdown"],
                                 help="Output format for solutions (default: jsonl)")
    solution_parser.add_argument("--max-suggestions", type=int, default=None,
                                 help="Max suggestions per finding (default: 10)")
    solution_parser.add_argument("--min-confidence", type=float, default=None,
                                 help="Minimum confidence threshold (default: 0.5)")

    # ── HITL command ─────────────────────────────────────────────────
    hitl_parser = subparsers.add_parser(
        "hitl", help="Manage HITL feedback database")
    hitl_parser.add_argument("--store-path", type=str, default=None,
                             help="(Deprecated) Ignored — PostgreSQL connection is configured in config.yaml")
    hitl_parser.add_argument("--export", type=str, default=None,
                             help="Export decisions to JSON file")
    hitl_parser.add_argument("--import-file", type=str, default=None,
                             help="Import decisions from JSON file")
    hitl_parser.add_argument("--stats", action="store_true",
                             help="Show decision statistics")

    # ── REPORT command ───────────────────────────────────────────────
    report_parser = subparsers.add_parser(
        "report", help="Generate reports from audit findings")
    report_parser.add_argument("--findings-file", type=str, default=None,
                               help="Path to findings JSON")
    report_parser.add_argument("--out-dir", type=str, default=None,
                               help="Output directory")
    report_parser.add_argument("--format", type=str, default=None,
                               choices=["excel", "json", "html", "all"],
                               help="Report format (default: all)")

    # ── CONTEXT-GEN command ──────────────────────────────────────────
    ctx_parser = subparsers.add_parser(
        "context-gen",
        help="Auto-generate codebase constraint rules from C/C++ symbols")
    ctx_parser.add_argument("--codebase-path", type=str, required=True,
                            help="Root path of the C/C++ codebase to scan")
    ctx_parser.add_argument("--output", "-o", type=str, default=None,
                            help="Output .md file path (default: agents/constraints/codebase_constraints.md)")
    ctx_parser.add_argument("--exclude-dirs", nargs="*", default=[],
                            help="Additional directory names to exclude")
    ctx_parser.add_argument("--exclude-globs", nargs="*", default=[],
                            help="Glob patterns to exclude (e.g., '*.test.cpp')")
    ctx_parser.add_argument("-v", "--verbose", action="store_true", default=None,
                            help="Enable verbose logging")

    # ── FIXER-WORKFLOW command ───────────────────────────────────────
    fw_parser = subparsers.add_parser(
        "fixer-workflow",
        help="Run HITL fixer workflow (Excel → fixer agent, patch, or batch-patch)")
    fw_parser.add_argument("--excel-file", default="out/detailed_code_review.xlsx",
                           help="Path to the reviewed Excel file")
    fw_parser.add_argument("--batch-patch", default=None, metavar="PATCH_FILE",
                           help="Path to a multi-file patch file")
    fw_parser.add_argument("--patch-file", default=None,
                           help="Path to a .patch/.diff file for single-file patch analysis")
    fw_parser.add_argument("--patch-target", default=None,
                           help="Path to the original source file being patched")
    fw_parser.add_argument("--patch-codebase-path", default=None,
                           help="Root of the codebase for header/context resolution")
    fw_parser.add_argument("--enable-adapters", action="store_true",
                           help="Enable deep static analysis adapters")
    fw_parser.add_argument("--codebase-path", default="codebase",
                           help="Root directory of the source code")
    fw_parser.add_argument("--out-dir", default="out",
                           help="Directory for output/patched files")
    fw_parser.add_argument("--config-file", default=None,
                           help="Path to custom config.yaml file")
    fw_parser.add_argument("--analyse-only", action="store_true",
                           help="Run only the analysis step without applying fixes")
    fw_parser.add_argument("--fix-only", action="store_true",
                           help="Skip analysis and run the fixer directly from Excel")
    fw_parser.add_argument("--fix-source", choices=["all", "llm", "static", "patch"],
                           default="patch", help="Process only issues from a specific source")
    fw_parser.add_argument("--llm-model", default=None,
                           help="LLM model in 'provider::model' format")
    fw_parser.add_argument("--dry-run", action="store_true",
                           help="Simulate fixes without writing to disk")
    fw_parser.add_argument("-v", "--verbose", action="store_true", default=False,
                           help="Enable detailed logging")

    return parser


def _add_common_args(parser):
    """Add arguments shared across audit / fix / pipeline commands."""
    core = parser.add_argument_group("Core Paths")
    core.add_argument("--codebase-path", type=str, default=None,
                      help="Path to source code root (default: from config.yaml)")
    core.add_argument("--out-dir", type=str, default=None,
                      help="Output directory (default: ./out)")
    core.add_argument("--config-file", type=str, default="",
                      help="Path to config YAML")

    rules = parser.add_argument_group("Rules")
    rules.add_argument("--rules-file", type=str, default=None,
                       help="Path to custom rules YAML")
    rules.add_argument("--rules-preset", type=str, default=None,
                       choices=["kernel", "uboot", "yocto", "custom"],
                       help="Use built-in rules preset")

    log = parser.add_argument_group("Logging")
    log.add_argument("-v", "--verbose", action="count", default=None,
                     help="Increase verbosity (-v, -vv)")
    log.add_argument("-D", "--debug", action="store_true", default=None,
                     help="Enable debug mode")
    log.add_argument("--quiet", action="store_true", default=None,
                     help="Suppress all output except errors")

    parser.add_argument("--exclude-dirs", type=str, default=None,
                        help="Comma-separated directories to exclude")


def _add_audit_args(parser):
    """Add audit-specific arguments."""
    mode = parser.add_argument_group("Analysis Mode")
    mode.add_argument("--audit-static", action="store_true", default=None,
                      help="Run static analysis (default: true)")
    mode.add_argument("--audit-llm", action="store_true", default=None,
                      help="Run LLM-powered semantic analysis")
    mode.add_argument("--audit-all", action="store_true", default=None,
                      help="Run both static and LLM analysis")

    domains = parser.add_argument_group("Domains")
    domains.add_argument("--domains", type=str, default=None,
                         help="Comma-separated domains: style,license,structure,patch,all")

    ctx_grp = parser.add_argument_group("Context Layers")
    ctx_grp.add_argument("--enable-context", action="store_true", default=None,
                         help="Enable context-aware analysis (header resolution, "
                              "validation tracing, call-stack analysis)")
    ctx_grp.add_argument("--constraints-dir", type=str, default=None,
                         help="Path to constraint .md files for LLM injection")
    ctx_grp.add_argument("--generate-constraints", action="store_true", default=None,
                         help="Auto-generate constraints from codebase before audit")
    ctx_grp.add_argument("--include-paths", type=str, default=None,
                         help="Comma-separated additional include paths for header resolution")

    adapters = parser.add_argument_group("Adapters")
    adapters.add_argument("--enable-adapters", action="store_true", default=None,
                          help="Enable external tool adapters (checkpatch, gitlint)")
    adapters.add_argument("--checkpatch-path", type=str, default=None,
                          help="Path to checkpatch.pl")

    hitl = parser.add_argument_group("HITL")
    hitl.add_argument("--enable-hitl", action="store_true", default=None,
                      help="Enable human-in-the-loop feedback")
    hitl.add_argument("--hitl-store-path", type=str, default=None,
                      help="(Deprecated) Ignored — PostgreSQL connection is configured in config.yaml")
    hitl.add_argument("--hitl-feedback-excel", type=str, default=None,
                      help="Path to HITL feedback Excel file")

    report_grp = parser.add_argument_group("Reporting")
    report_grp.add_argument("--report-format", type=str, default=None,
                            help="Output formats: excel,json,html,all")

    perf = parser.add_argument_group("Performance")
    perf.add_argument("--batch-size", type=int, default=None,
                      help="Files per batch (default: 50)")
    perf.add_argument("--max-files", type=int, default=None,
                      help="Maximum files to process (default: 10000)")


def _add_fix_args(parser):
    """Add fix-specific arguments."""
    fix_grp = parser.add_argument_group("Fix Options")
    fix_grp.add_argument("--fix-domain", type=str, default=None,
                         help="Domain to fix: all,style,license,structure,patch")
    fix_grp.add_argument("--dry-run", action="store_true", default=None,
                         help="Show fixes without applying (default: true)")
    fix_grp.add_argument("--apply", action="store_true", default=None,
                         help="Actually apply fixes")
    fix_grp.add_argument("--backup", action="store_true", default=None,
                         help="Create backups before fixing (default: true)")
    fix_grp.add_argument("--audit-after", action="store_true", default=None,
                         help="Re-audit after applying fixes")
    fix_grp.add_argument("--findings-file", type=str, default=None,
                         help="Path to findings JSON from previous audit")


# ═════════════════════════════════════════════════════════════════════════
#  Option Resolution  (CLI arg  →  config.yaml  →  hardcoded default)
# ═════════════════════════════════════════════════════════════════════════

def resolve(cli_val, cfg_val, default):
    """Return the first non-None value in priority order."""
    if cli_val is not None:
        return cli_val
    if cfg_val is not None:
        return cfg_val
    return default


def resolve_rules_path(args, cfg: dict) -> str:
    """Resolve rules file path: CLI > config.yaml > built-in preset."""
    # Explicit --rules-file
    rules_file = getattr(args, 'rules_file', None)
    if rules_file:
        return rules_file

    # Explicit --rules-preset
    preset = getattr(args, 'rules_preset', None) or cfg_get(cfg, "paths", "rules_preset")

    # Config paths.rules (if it points to a real file)
    cfg_rules = cfg_get(cfg, "paths", "rules", default="")
    if cfg_rules and os.path.isfile(cfg_rules):
        return cfg_rules

    # Resolve preset
    preset = preset or "kernel"
    preset_map = {
        "kernel": "linux_kernel.yaml",
        "uboot": "uboot.yaml",
        "yocto": "yocto.yaml",
        "custom": "custom.yaml",
    }
    return os.path.join(ORCA_ROOT, "rules", preset_map.get(preset, "linux_kernel.yaml"))


def load_rules(rules_path: str) -> dict:
    """Load and parse YAML rules file."""
    import yaml
    try:
        with open(rules_path, 'r') as f:
            rules = yaml.safe_load(f) or {}
        logger.info(f"Loaded rules from {rules_path}: "
                     f"{rules.get('project', {}).get('name', 'Unknown')}")
        return rules
    except Exception as e:
        logger.warning(f"Failed to load rules from {rules_path}: {e}")
        return {}


def parse_domains(domains_input) -> list:
    """Parse domains into list from string or list."""
    if isinstance(domains_input, list):
        return domains_input
    if isinstance(domains_input, str):
        if domains_input == "all":
            return ["style", "license", "structure", "patch"]
        return [d.strip() for d in domains_input.split(",") if d.strip()]
    return ["style", "license", "structure", "patch"]


# ═════════════════════════════════════════════════════════════════════════
#  Report Generation
# ═════════════════════════════════════════════════════════════════════════

def generate_reports(report, out_dir: str, formats: list, rules: dict):
    """Generate reports in requested formats."""
    os.makedirs(out_dir, exist_ok=True)
    generated = []

    if "json" in formats or "all" in formats:
        try:
            from agents.parsers.report_parser import JSONReportGenerator
            json_gen = JSONReportGenerator()
            json_path = os.path.join(out_dir, "compliance_report.json")
            json_gen.generate(report, json_path)
            generated.append(f"JSON  → {json_path}")
            logger.info(f"JSON report: {json_path}")
        except Exception as e:
            logger.warning(f"JSON report failed: {e}")

    if "excel" in formats or "all" in formats:
        try:
            from agents.adapters.excel_report_adapter import ExcelReportAdapter
            excel_adapter = ExcelReportAdapter(rules=rules, config={})
            excel_path = os.path.join(out_dir, "compliance_review.xlsx")
            excel_adapter.generate_report(report, excel_path)
            generated.append(f"Excel → {excel_path}")
            logger.info(f"Excel report: {excel_path}")
        except Exception as e:
            logger.warning(f"Excel report failed: {e}")

    if "html" in formats or "all" in formats:
        try:
            from agents.parsers.report_parser import HTMLDashboardGenerator
            html_gen = HTMLDashboardGenerator()
            html_path = os.path.join(out_dir, "compliance_dashboard.html")
            html_gen.generate(report, html_path)
            generated.append(f"HTML  → {html_path}")
            logger.info(f"HTML report: {html_path}")
        except Exception as e:
            logger.warning(f"HTML report failed: {e}")

    return generated


def print_summary(report, codebase_path: str, rules: dict, domains: list,
                  elapsed: float, out_dir: str, report_files: list):
    """Print a human-readable audit summary to stdout."""
    file_count = getattr(report, 'file_count', len(set(
        (f.file_path if hasattr(f, 'file_path') else f.get('file_path', ''))
        for f in report.findings
    )))
    print(f"\n{'='*64}")
    print(f"  ORCA Compliance Audit Report")
    print(f"{'='*64}")
    print(f"  Codebase:    {codebase_path}")
    print(f"  Rules:       {rules.get('project', {}).get('name', 'Default')}")
    print(f"  Domains:     {', '.join(domains)}")
    print(f"  Files:       {file_count}")
    print(f"  Grade:       {report.overall_grade}")
    print(f"  Findings:    {len(report.findings)}")
    print(f"  Time:        {elapsed:.1f}s")
    print(f"{'='*64}")

    for domain, score in report.domain_scores.items():
        count = len([f for f in report.findings
                     if (f.category if hasattr(f, 'category')
                         else f.get('category', '')) == domain])
        print(f"  {domain:15s}  Score: {score:.0%}  Findings: {count}")

    print(f"{'='*64}")
    if report_files:
        print(f"  Reports:")
        for rf in report_files:
            print(f"    {rf}")
    print(f"  Output: {out_dir}/")
    print(f"{'='*64}\n")


# ═════════════════════════════════════════════════════════════════════════
#  Command Handlers
# ═════════════════════════════════════════════════════════════════════════

def run_audit(args, cfg: dict) -> int:
    """Execute the audit command."""
    start_time = time.time()

    codebase_path = resolve(
        getattr(args, 'codebase_path', None),
        cfg_get(cfg, "paths", "codebase"),
        ".")
    out_dir = resolve(
        getattr(args, 'out_dir', None),
        cfg_get(cfg, "paths", "output"),
        "./out")
    domains_raw = resolve(
        getattr(args, 'domains', None),
        cfg_get(cfg, "audit", "domains"),
        "all")
    batch_size = resolve(
        getattr(args, 'batch_size', None),
        cfg_get(cfg, "audit", "batch_size"),
        50)
    max_files = resolve(
        getattr(args, 'max_files', None),
        cfg_get(cfg, "audit", "max_files"),
        10000)
    report_fmt = resolve(
        getattr(args, 'report_format', None),
        ",".join(cfg_get(cfg, "reporting", "formats", default=["excel", "json"])),
        "excel,json")
    audit_llm = resolve(
        getattr(args, 'audit_llm', None),
        cfg_get(cfg, "audit", "llm"),
        False)
    audit_all = resolve(
        getattr(args, 'audit_all', None),
        None,
        False)

    rules_path = resolve_rules_path(args, cfg)
    rules = load_rules(rules_path)
    domains = parse_domains(domains_raw)
    os.makedirs(out_dir, exist_ok=True)

    logger.info(f"Starting ORCA audit on {codebase_path}")
    logger.info(f"Rules: {rules.get('project', {}).get('name', 'Default')}")
    logger.info(f"Domains: {domains}")

    # ── Phase 1: Static audit ────────────────────────────────────────
    from agents.compliance_static_agent import ComplianceStaticAgent
    static_agent = ComplianceStaticAgent(rules=rules, config=cfg)
    report = static_agent.run_audit(
        codebase_path=codebase_path,
        output_dir=out_dir,
        domains=domains,
    )

    # ── Phase 1b: Resolve constraints directory ────────────────────
    constraints_dir = resolve(
        getattr(args, 'constraints_dir', None),
        cfg_get(cfg, "context", "constraints_dir"),
        "./constraints")

    # ── Phase 2: LLM audit (optional) ───────────────────────────────
    if audit_llm or audit_all:
        try:
            from utils.llm_tools import LLMClient
            from agents.compliance_audit_agent import ComplianceAuditAgent

            llm_cfg = cfg_get(cfg, "llm", default={})
            llm_client = LLMClient(llm_cfg if isinstance(llm_cfg, dict) else {})

            audit_agent = ComplianceAuditAgent(
                llm_client=llm_client, rules=rules, config=cfg,
                constraints_dir=constraints_dir)
            llm_report = audit_agent.run_analysis(
                codebase_path=codebase_path,
                output_dir=out_dir,
                domains=domains,
            )
            report.findings.extend(llm_report.findings)
            logger.info(f"LLM audit added {len(llm_report.findings)} findings")
        except Exception as e:
            logger.warning(f"LLM audit failed (continuing with static only): {e}")

    # ── Phase 3: HITL enrichment (optional) ──────────────────────────
    enable_hitl = resolve(
        getattr(args, 'enable_hitl', None),
        cfg_get(cfg, "hitl", "enabled"),
        False)
    if enable_hitl:
        report = _enrich_with_hitl(report, args, cfg)

    # ── Phase 4: Generate reports ────────────────────────────────────
    report_formats = [f.strip() for f in report_fmt.split(",")]
    report_files = generate_reports(report, out_dir, report_formats, rules)

    elapsed = time.time() - start_time
    print_summary(report, codebase_path, rules, domains, elapsed, out_dir, report_files)

    return 0 if report.overall_grade in ("A", "B") else 1


def run_fix(args, cfg: dict) -> int:
    """Execute the fix command."""
    codebase_path = resolve(
        getattr(args, 'codebase_path', None),
        cfg_get(cfg, "paths", "codebase"),
        ".")
    out_dir = resolve(
        getattr(args, 'out_dir', None),
        cfg_get(cfg, "paths", "output"),
        "./out")
    fix_domain = resolve(
        getattr(args, 'fix_domain', None),
        cfg_get(cfg, "fix", "domain"),
        "all")
    do_apply = resolve(
        getattr(args, 'apply', None),
        not cfg_get(cfg, "fix", "dry_run", default=True),
        False)
    audit_after = resolve(
        getattr(args, 'audit_after', None),
        cfg_get(cfg, "fix", "audit_after"),
        False)

    rules_path = resolve_rules_path(args, cfg)
    rules = load_rules(rules_path)

    # If a findings file is provided, load it instead of re-auditing
    findings_file = getattr(args, 'findings_file', None)
    if findings_file and os.path.isfile(findings_file):
        report = _load_findings_as_report(findings_file)
    else:
        # Run audit first to get findings
        from agents.compliance_static_agent import ComplianceStaticAgent
        static_agent = ComplianceStaticAgent(rules=rules, config=cfg)
        domains = parse_domains(fix_domain)
        report = static_agent.run_audit(
            codebase_path=codebase_path,
            output_dir=out_dir,
            domains=domains,
        )

    # Resolve constraints
    constraints_dir = resolve(
        getattr(args, 'constraints_dir', None),
        cfg_get(cfg, "context", "constraints_dir"),
        "./constraints")

    # Apply fixes
    from agents.compliance_fixer_agent import ComplianceFixerAgent
    fixer = ComplianceFixerAgent(config=cfg, constraints_dir=constraints_dir)

    dry_run = not do_apply
    total_fixed = 0
    total_remaining = 0

    findings_by_file = defaultdict(list)
    for f in report.findings:
        fp = f.file_path if hasattr(f, 'file_path') else f.get('file_path', '')
        findings_by_file[fp].append(f)

    for file_path, findings in findings_by_file.items():
        result = fixer.apply_fixes(
            file_path=file_path,
            findings=findings,
            solutions={},
            dry_run=dry_run,
            domain_filter=fix_domain if fix_domain != "all" else None,
        )
        total_fixed += result.fixed_count
        total_remaining += result.remaining_count

    mode = "DRY RUN" if dry_run else "APPLIED"
    print(f"\n[{mode}] Fixed {total_fixed} issues, {total_remaining} remaining")

    # Re-audit after fix if requested
    if audit_after and do_apply:
        print("\nRe-auditing after fixes...")
        return run_audit(args, cfg)

    return 0


def run_pipeline(args, cfg: dict) -> int:
    """Execute the full pipeline: audit → solution → fix → report.

    This orchestrates all ORCA components into a single end-to-end workflow.
    """
    start_time = time.time()

    codebase_path = resolve(
        getattr(args, 'codebase_path', None),
        cfg_get(cfg, "paths", "codebase"),
        ".")
    out_dir = resolve(
        getattr(args, 'out_dir', None),
        cfg_get(cfg, "paths", "output"),
        "./out")
    domains_raw = resolve(
        getattr(args, 'domains', None),
        cfg_get(cfg, "audit", "domains"),
        "all")
    gen_solutions = resolve(
        getattr(args, 'generate_solutions', None),
        cfg_get(cfg, "pipeline", "generate_solutions"),
        True)
    auto_fix = resolve(
        getattr(args, 'auto_fix', None),
        cfg_get(cfg, "pipeline", "auto_fix"),
        False)
    hitl_review = resolve(
        getattr(args, 'hitl_review', None),
        cfg_get(cfg, "pipeline", "hitl_review"),
        False)
    full_report = resolve(
        getattr(args, 'full_report', None),
        cfg_get(cfg, "pipeline", "full_report"),
        True)

    rules_path = resolve_rules_path(args, cfg)
    rules = load_rules(rules_path)
    domains = parse_domains(domains_raw)
    os.makedirs(out_dir, exist_ok=True)

    print(f"\n{'━'*64}")
    print(f"  ORCA Pipeline — Full End-to-End Compliance Workflow")
    print(f"{'━'*64}")
    print(f"  Codebase : {codebase_path}")
    print(f"  Rules    : {rules.get('project', {}).get('name', 'Default')}")
    print(f"  Domains  : {', '.join(domains)}")
    print(f"{'━'*64}\n")

    # Resolve constraints directory
    constraints_dir = resolve(
        getattr(args, 'constraints_dir', None),
        cfg_get(cfg, "context", "constraints_dir"),
        "./constraints")

    # ── Step 1: Static Audit ─────────────────────────────────────────
    print("  [1/5] Running static analysis...")
    from agents.compliance_static_agent import ComplianceStaticAgent
    static_agent = ComplianceStaticAgent(rules=rules, config=cfg)
    report = static_agent.run_audit(
        codebase_path=codebase_path,
        output_dir=out_dir,
        domains=domains,
    )
    print(f"        Found {len(report.findings)} findings  |  Grade: {report.overall_grade}")

    # ── Step 2: LLM Audit (optional) ────────────────────────────────
    audit_llm = resolve(
        getattr(args, 'audit_llm', None),
        cfg_get(cfg, "audit", "llm"),
        False)
    if audit_llm or getattr(args, 'audit_all', False):
        print("  [2/5] Running LLM semantic analysis...")
        try:
            from utils.llm_tools import LLMClient
            from agents.compliance_audit_agent import ComplianceAuditAgent
            llm_cfg = cfg_get(cfg, "llm", default={})
            llm_client = LLMClient(llm_cfg if isinstance(llm_cfg, dict) else {})
            audit_agent = ComplianceAuditAgent(
                llm_client=llm_client, rules=rules, config=cfg,
                constraints_dir=constraints_dir)
            llm_report = audit_agent.run_analysis(
                codebase_path=codebase_path,
                output_dir=out_dir,
                domains=domains,
            )
            report.findings.extend(llm_report.findings)
            print(f"        LLM added {len(llm_report.findings)} findings")
        except Exception as e:
            print(f"        LLM audit skipped: {e}")
    else:
        print("  [2/5] LLM audit — skipped (use --audit-llm to enable)")

    # ── Step 3: Solution Generation (optional) ───────────────────────
    solutions = {}
    if gen_solutions:
        print("  [3/5] Generating fix recommendations...")
        try:
            solutions = _generate_solutions(report, rules, cfg, out_dir,
                                             constraints_dir=constraints_dir)
            print(f"        Generated {len(solutions)} solution(s)")
        except Exception as e:
            print(f"        Solution generation skipped: {e}")
    else:
        print("  [3/5] Solution generation — skipped")

    # ── Step 4: Fix / HITL ───────────────────────────────────────────
    if hitl_review:
        print("  [4/5] Running HITL-reviewed fixes...")
        try:
            from fixer_workflow import FixerWorkflow
            hitl_cfg = cfg.get("hitl", {})
            workflow = FixerWorkflow(config=cfg)
            hitl_result = workflow.run(
                findings=report.findings,
                auto_mode=auto_fix,
                project=cfg_get(cfg, "hitl", "project", default="default"),
            )
            print(f"        Fixed: {hitl_result.get('fixed', 0)}  "
                  f"Skipped: {hitl_result.get('skipped', 0)}  "
                  f"Waived: {hitl_result.get('waived', 0)}")
            # Export audit trail
            trail_path = os.path.join(out_dir, "hitl_audit_trail.json")
            workflow.export_audit_trail(trail_path)
            workflow.close()
        except Exception as e:
            print(f"        HITL review skipped: {e}")
    elif auto_fix:
        print("  [4/5] Auto-applying high-confidence fixes...")
        try:
            from agents.compliance_fixer_agent import ComplianceFixerAgent
            fixer = ComplianceFixerAgent(config=cfg)
            total_fixed = 0
            findings_by_file = defaultdict(list)
            for f in report.findings:
                fp = f.file_path if hasattr(f, 'file_path') else f.get('file_path', '')
                findings_by_file[fp].append(f)
            for file_path, findings in findings_by_file.items():
                result = fixer.apply_fixes(
                    file_path=file_path,
                    findings=findings,
                    solutions=solutions,
                    dry_run=False,
                )
                total_fixed += result.fixed_count
            print(f"        Applied {total_fixed} fixes")
        except Exception as e:
            print(f"        Auto-fix skipped: {e}")
    else:
        print("  [4/5] Fix — skipped (use --auto-fix or --hitl-review to enable)")

    # ── Step 5: Full Report Generation ───────────────────────────────
    report_formats = ["all"] if full_report else \
        cfg_get(cfg, "reporting", "formats", default=["excel", "json"])
    print("  [5/5] Generating reports...")
    report_files = generate_reports(report, out_dir, report_formats, rules)
    for rf in report_files:
        print(f"        {rf}")

    elapsed = time.time() - start_time

    print(f"\n{'━'*64}")
    print(f"  Pipeline Complete")
    print(f"  Grade: {report.overall_grade}  |  "
          f"Findings: {len(report.findings)}  |  Time: {elapsed:.1f}s")
    print(f"  Output: {out_dir}/")
    print(f"{'━'*64}\n")

    return 0 if report.overall_grade in ("A", "B") else 1


def run_patch_audit(args, cfg: dict) -> int:
    """Execute the patch-audit command."""
    rules_path = resolve_rules_path(args, cfg)
    rules = load_rules(rules_path)

    from agents.compliance_patch_agent import CompliancePatchAgent
    patch_agent = CompliancePatchAgent(rules=rules, config=cfg)

    patch_file = getattr(args, 'patch_file', None)
    patch_series_dir = getattr(args, 'patch_series_dir', None)

    if patch_file:
        result = patch_agent.audit_patch(patch_file)
        print(f"\nPatch: {patch_file}")
        print(f"Compliant: {result.is_compliant}")
        print(f"Findings: {len(result.format_findings) + len(result.code_findings) + len(result.metadata_findings)}")
    elif patch_series_dir:
        results = patch_agent.audit_series(patch_series_dir)
        print(f"\nSeries: {patch_series_dir}")
        print(f"Patches: {len(results)}")
        compliant = sum(1 for r in results if r.is_compliant)
        print(f"Compliant: {compliant}/{len(results)}")
    else:
        print("Error: Specify --patch-file or --patch-series-dir")
        return 1

    return 0


def run_solution(args, cfg: dict) -> int:
    """Execute the solution command — generate fix recommendations."""
    findings_file = resolve(
        getattr(args, 'findings_file', None),
        None,
        os.path.join(
            cfg_get(cfg, "paths", "output", default="./out"),
            "compliance_report.json"))
    out_dir = resolve(
        getattr(args, 'out_dir', None),
        cfg_get(cfg, "paths", "output"),
        "./out")
    sol_format = resolve(
        getattr(args, 'solution_format', None),
        cfg_get(cfg, "solution", "format"),
        "jsonl")

    if not os.path.isfile(findings_file):
        print(f"Error: Findings file not found: {findings_file}")
        print("Run 'orca audit' first, or provide --findings-file")
        return 1

    report = _load_findings_as_report(findings_file)
    rules_path = resolve_rules_path(args, cfg)
    rules = load_rules(rules_path)

    solutions = _generate_solutions(report, rules, cfg, out_dir)
    print(f"\nGenerated {len(solutions)} solution(s) → {out_dir}/")

    return 0


def run_hitl(args, cfg: dict) -> int:
    """Execute the hitl command."""
    from hitl.feedback_store import FeedbackStore

    hitl_cfg = cfg_get(cfg, "hitl", default={})
    store = FeedbackStore(hitl_cfg if isinstance(hitl_cfg, dict) else {})

    if args.stats:
        stats = store.get_decision_stats()
        print("\nHITL Decision Statistics:")
        for decision, count in stats.items():
            print(f"  {decision}: {count}")

    export_path = getattr(args, 'export', None)
    if export_path:
        store.export_to_json(export_path)
        print(f"Exported decisions to {export_path}")

    import_file = getattr(args, 'import_file', None)
    if import_file:
        store.import_from_json(import_file)
        print(f"Imported decisions from {import_file}")

    store.close()
    return 0


def run_report(args, cfg: dict) -> int:
    """Execute the report command — generate reports from findings."""
    findings_file = resolve(
        getattr(args, 'findings_file', None),
        None,
        os.path.join(
            cfg_get(cfg, "paths", "output", default="./out"),
            "compliance_report.json"))
    out_dir = resolve(
        getattr(args, 'out_dir', None),
        cfg_get(cfg, "paths", "output"),
        "./out")
    fmt = resolve(
        getattr(args, 'format', None),
        None,
        "all")

    if not os.path.isfile(findings_file):
        print(f"Error: Findings file not found: {findings_file}")
        print("Run 'orca audit' first, or provide --findings-file")
        return 1

    report = _load_findings_as_report(findings_file)
    rules_path = resolve_rules_path(args, cfg)
    rules = load_rules(rules_path)

    report_files = generate_reports(report, out_dir, [fmt], rules)
    for rf in report_files:
        print(f"  {rf}")

    return 0


# ═════════════════════════════════════════════════════════════════════════
#  Helper Functions
# ═════════════════════════════════════════════════════════════════════════

def run_context_gen(args, cfg: dict) -> int:
    """Execute the context-gen command — auto-generate constraint rules."""
    from agents.context.codebase_constraint_generator import generate_constraints

    codebase_path = args.codebase_path
    exclude_dirs = getattr(args, "exclude_dirs", []) or []
    exclude_globs = getattr(args, "exclude_globs", []) or []

    if getattr(args, "verbose", False):
        logging.basicConfig(level=logging.DEBUG,
                            format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    print(f"Scanning codebase: {codebase_path}")
    md_text = generate_constraints(
        codebase_path=codebase_path,
        exclude_dirs=exclude_dirs,
        exclude_globs=exclude_globs,
    )

    output = getattr(args, "output", None)
    if not output:
        output = os.path.join(ORCA_ROOT, "agents", "constraints", "codebase_constraints.md")

    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(md_text)

    lines = md_text.count("\n") + 1
    print(f"Constraint file written to: {output}")
    print(f"  Lines: {lines}")

    return 0


def run_fixer_workflow(args, cfg: dict) -> int:
    """Execute the fixer-workflow command — HITL repair orchestrator."""
    from fixer_workflow import HumanInTheLoopWorkflow

    # Validate conflicting flags
    if getattr(args, "analyse_only", False) and getattr(args, "fix_only", False):
        print("Error: --analyse-only and --fix-only are mutually exclusive.")
        return 1

    # In default fixer mode, override fix_source to 'llm' if not in patch mode
    is_patch_mode = args.batch_patch or (args.patch_file and args.patch_target)
    if not is_patch_mode and args.fix_source == "patch":
        args.fix_source = "llm"

    workflow = HumanInTheLoopWorkflow(args)
    workflow.execute()
    return 0


def _load_findings_as_report(findings_file: str) -> ComplianceReport:
    """Load a JSON findings file into a ComplianceReport object."""
    from agents.analyzers.base_analyzer import Finding, Severity

    with open(findings_file, 'r') as f:
        data = json.load(f)

    findings_data = data if isinstance(data, list) else data.get("findings", [])
    findings = []
    for fd in findings_data:
        findings.append(Finding(
            file_path=fd.get("file_path", ""),
            line_number=fd.get("line_number", 0),
            column=fd.get("column", 0),
            severity=fd.get("severity", "medium"),
            category=fd.get("category", fd.get("domain", "")),
            rule_id=fd.get("rule_id", ""),
            message=fd.get("message", ""),
            suggestion=fd.get("suggestion", ""),
            code_snippet=fd.get("code_snippet", fd.get("context", "")),
            confidence=fd.get("confidence", 0.5),
            tool=fd.get("tool", "orca"),
        ))

    report = ComplianceReport(
        findings=findings,
        domain_scores=data.get("domain_scores", {}) if isinstance(data, dict) else {},
        overall_grade=data.get("overall_grade", "?") if isinstance(data, dict) else "?",
        file_count=data.get("file_count", len(set(f.file_path for f in findings))) if isinstance(data, dict) else len(set(f.file_path for f in findings)),
    )
    return report


def _generate_solutions(report, rules: dict, cfg: dict, out_dir: str,
                        constraints_dir: str = "./constraints") -> dict:
    """Generate solutions for report findings (using LLM or fallback)."""
    from agents.compliance_solution_agent import ComplianceSolutionAgent

    llm_cfg = cfg_get(cfg, "llm", default={})
    try:
        from utils.llm_tools import LLMClient
        llm_client = LLMClient(llm_cfg if isinstance(llm_cfg, dict) else {})
    except Exception:
        llm_client = None

    solution_agent = ComplianceSolutionAgent(
        llm_client=llm_client,
        rules=rules,
        config=cfg,
        constraints_dir=constraints_dir,
    )

    # Convert findings to dicts for the solution agent API
    findings_dicts = []
    file_contents = {}
    for f in report.findings:
        fd = {
            "id": f.rule_id if hasattr(f, 'rule_id') else f.get('rule_id', ''),
            "file_path": f.file_path if hasattr(f, 'file_path') else f.get('file_path', ''),
            "line_number": f.line_number if hasattr(f, 'line_number') else f.get('line_number', 0),
            "message": f.message if hasattr(f, 'message') else f.get('message', ''),
            "domain": f.category if hasattr(f, 'category') else f.get('category', ''),
            "severity": f.severity if hasattr(f, 'severity') else f.get('severity', ''),
        }
        findings_dicts.append(fd)
        fp = fd["file_path"]
        if fp and fp not in file_contents:
            content = read_file_safe(fp)
            if content:
                file_contents[fp] = content

    solutions = solution_agent.generate_solutions(findings_dicts, file_contents)

    # Save solutions
    sol_path = os.path.join(out_dir, "solutions.json")
    try:
        with open(sol_path, 'w') as f:
            json.dump(
                {k: v.to_dict() if hasattr(v, 'to_dict') else v
                 for k, v in solutions.items()},
                f, indent=2)
        logger.info(f"Solutions saved to {sol_path}")
    except Exception as e:
        logger.warning(f"Failed to save solutions: {e}")

    return solutions


def _enrich_with_hitl(report, args, cfg: dict):
    """Enrich report with HITL context (past decisions as annotations)."""
    try:
        from hitl.feedback_store import FeedbackStore
        from hitl.rag_retriever import RAGRetriever

        hitl_cfg = cfg_get(cfg, "hitl", default={})
        store = FeedbackStore(hitl_cfg if isinstance(hitl_cfg, dict) else {})
        rag = RAGRetriever(store, config=hitl_cfg)

        for finding in report.findings:
            ctx = rag.retrieve_context(finding)
            if ctx.recommendation:
                if hasattr(finding, 'suggestion'):
                    finding.suggestion = f"{finding.suggestion} [HITL: {ctx.recommendation}]"
        store.close()
    except Exception as e:
        logger.warning(f"HITL enrichment skipped: {e}")

    return report


# ═════════════════════════════════════════════════════════════════════════
#  Main Entry Point
# ═════════════════════════════════════════════════════════════════════════

def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Load config
    config_file = getattr(args, 'config_file', '') or ""
    cfg = load_effective_config(config_file)

    # Setup logging
    cli_verbose = getattr(args, 'verbose', None) or 0
    cfg_verbose = cfg_get(cfg, "logging", "verbosity", default=0)
    verbosity = cli_verbose if cli_verbose else cfg_verbose
    if getattr(args, 'debug', None):
        verbosity = 2
    quiet = resolve(getattr(args, 'quiet', None),
                    cfg_get(cfg, "logging", "quiet"), False)
    setup_logging(verbosity, quiet)

    # Dispatch
    try:
        if args.command == "audit":
            return run_audit(args, cfg)
        elif args.command == "fix":
            return run_fix(args, cfg)
        elif args.command == "pipeline":
            return run_pipeline(args, cfg)
        elif args.command == "patch-audit":
            return run_patch_audit(args, cfg)
        elif args.command == "solution":
            return run_solution(args, cfg)
        elif args.command == "hitl":
            return run_hitl(args, cfg)
        elif args.command == "report":
            return run_report(args, cfg)
        elif args.command == "context-gen":
            return run_context_gen(args, cfg)
        elif args.command == "fixer-workflow":
            return run_fixer_workflow(args, cfg)
        else:
            parser.print_help()
            return 0
    except KeyboardInterrupt:
        print("\nAborted.")
        return 130
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
