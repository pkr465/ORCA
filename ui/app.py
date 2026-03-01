#!/usr/bin/env python3
"""ORCA Streamlit UI — Interactive Compliance Auditing Dashboard.

Launch:  streamlit run ui/app.py
"""

import json
import os
import sys
import time
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

# ── Bootstrap ORCA on sys.path ──────────────────────────────────────────
# ui/app.py lives one level below the project root
ORCA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ORCA_ROOT not in sys.path:
    sys.path.insert(0, ORCA_ROOT)

from utils.config_parser import load_config
from agents.compliance_static_agent import ComplianceStaticAgent
from agents.analyzers.base_analyzer import Finding

# ── Silence noisy loggers in the UI ─────────────────────────────────────
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("orca.ui")

# ═════════════════════════════════════════════════════════════════════════
#  Streamlit Page Config
# ═════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="ORCA — Compliance Auditor",
    page_icon="🐋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═════════════════════════════════════════════════════════════════════════
#  Custom CSS
# ═════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
    /* ══ ORCA Light Theme — Open-source codebase style ═══════════ */

    /* ── Grade badge ─────────────────────────────────────────────── */
    .grade-badge {
        display: inline-block;
        font-size: 3rem;
        font-weight: 800;
        width: 90px; height: 90px;
        line-height: 90px;
        text-align: center;
        border-radius: 50%;
        color: #fff;
        box-shadow: 0 4px 12px rgba(0,0,0,.10);
    }
    .grade-A { background: linear-gradient(135deg, #22c55e, #16a34a); }
    .grade-B { background: linear-gradient(135deg, #84cc16, #65a30d); }
    .grade-C { background: linear-gradient(135deg, #eab308, #ca8a04); }
    .grade-D { background: linear-gradient(135deg, #f97316, #ea580c); }
    .grade-F { background: linear-gradient(135deg, #ef4444, #dc2626); }

    /* ── Severity pills ──────────────────────────────────────────── */
    .sev-pill {
        display: inline-block;
        padding: 2px 12px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
        color: #fff;
    }
    .sev-CRITICAL { background: #dc2626; }
    .sev-HIGH     { background: #ea580c; }
    .sev-MEDIUM   { background: #ca8a04; }
    .sev-LOW      { background: #16a34a; }

    /* ── Fix status pills ────────────────────────────────────────── */
    .fix-applied  { color: #16a34a; font-weight: 600; }
    .fix-dryrun   { color: #0E6BB0; font-weight: 600; }
    .fix-failed   { color: #dc2626; font-weight: 600; }

    /* ── Stat card ───────────────────────────────────────────────── */
    .stat-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 14px;
        padding: 1.25rem 1.5rem;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,.06);
        transition: box-shadow .2s;
    }
    .stat-card:hover {
        box-shadow: 0 4px 12px rgba(14,107,176,.10);
    }
    .stat-card h2 { margin: 0; font-size: 2rem; color: #0E6BB0; }
    .stat-card p  { margin: 0; font-size: 0.85rem; color: #64748b; }

    /* ── Feedback button row ─────────────────────────────────────── */
    .fb-row { display: flex; gap: 6px; flex-wrap: wrap; }

    /* ── Phase progress ──────────────────────────────────────────── */
    .phase-active { color: #0E6BB0; font-weight: 600; }
    .phase-done   { color: #16a34a; }
    .phase-wait   { color: #94a3b8; }

    /* ── Sidebar ─────────────────────────────────────────────────── */
    div[data-testid="stSidebar"] {
        min-width: 320px;
        background: #f8fafc;
    }

    /* ── Links & accents ─────────────────────────────────────────── */
    a { color: #0E6BB0; }
    a:hover { color: #0c5a96; }

    /* ── Heading accent line ─────────────────────────────────────── */
    h2 { color: #1e293b; }
</style>
""", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════
#  Session State Helpers
# ═════════════════════════════════════════════════════════════════════════

def _ss(key, default=None):
    """Shortcut to read session_state."""
    return st.session_state.get(key, default)


def _init_state():
    """Initialise session state on first run."""
    defaults = {
        "report": None,
        "findings": [],
        "rules": {},
        "cfg": {},
        "fix_results": {},
        "feedback": {},          # finding_key → decision
        "analysis_mode": "static",
        "audit_running": False,
        "fix_running": False,
        "history": [],           # list of past audit summaries
        # Browse-state defaults (shared between text inputs and browsers)
        "browse_codebase": ".",
        "browse_file": "",
        "browse_rules": "",
        "browse_outdir": "./out",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()


# ═════════════════════════════════════════════════════════════════════════
#  Helper: Inline Filesystem Browser  (no tkinter, no @st.dialog)
# ═════════════════════════════════════════════════════════════════════════

def _list_dir_safe(path: str) -> tuple:
    """List directories and files in *path*. Returns (dirs, files)."""
    dirs, files = [], []
    try:
        for entry in sorted(os.scandir(path), key=lambda e: e.name.lower()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir(follow_symlinks=False):
                dirs.append(entry.name)
            elif entry.is_file(follow_symlinks=False):
                files.append(entry.name)
    except PermissionError:
        pass
    return dirs, files


def _flush_browse_selections():
    """Sync any pending browser selections into widget keys BEFORE widgets render.

    Browsers write to ``_browse_sel_{key}`` to avoid the Streamlit error:
    "st.session_state.X cannot be modified after the widget with key X is
    instantiated."  This helper copies pending values into the real widget
    keys at the very start of the script run (before any widget is created).
    """
    pending = [k for k in st.session_state if k.startswith("_browse_sel_")]
    for sel_key in pending:
        widget_key = sel_key[len("_browse_sel_"):]    # strip prefix
        st.session_state[widget_key] = st.session_state.pop(sel_key)


def _render_folder_browser(state_key: str, container, start: str = ""):
    """Render an inline folder browser. Updates session_state[state_key] on selection.

    Uses a *_cwd* session key to track the current directory across reruns
    and a *_open* key to track whether the browser panel is visible.
    """
    open_key = f"_browse_open_{state_key}"
    cwd_key = f"_browse_cwd_{state_key}"
    sel_key = f"_browse_sel_{state_key}"   # pending-selection key

    # Toggle open/close
    if open_key not in st.session_state:
        st.session_state[open_key] = False

    if container.button(
        "Browse folder..." if not st.session_state[open_key] else "Close browser",
        key=f"_brtoggle_{state_key}",
        use_container_width=True,
    ):
        st.session_state[open_key] = not st.session_state[open_key]
        if st.session_state[open_key] and cwd_key not in st.session_state:
            st.session_state[cwd_key] = start or os.path.expanduser("~")
        st.rerun()

    if not st.session_state[open_key]:
        return

    # ── Browser panel ──────────────────────────────────────────────
    cwd = st.session_state.get(cwd_key, os.path.expanduser("~"))
    with container.container(border=True):
        st.caption(f"📂  `{cwd}`")

        dirs, _ = _list_dir_safe(cwd)

        # Columns: [parent] [select]
        c1, c2 = st.columns(2)
        parent = os.path.dirname(cwd)
        with c1:
            if parent != cwd and st.button("⬆ Parent", key=f"_brp_{state_key}", use_container_width=True):
                st.session_state[cwd_key] = parent
                st.rerun()
        with c2:
            if st.button("✅ Select this folder", key=f"_brsel_{state_key}", type="primary", use_container_width=True):
                st.session_state[sel_key] = cwd
                st.session_state[open_key] = False
                st.rerun()

        # Subdirectories as clickable buttons
        for d in dirs[:40]:
            if st.button(f"📁  {d}", key=f"_brd_{state_key}_{d}", use_container_width=True):
                st.session_state[cwd_key] = os.path.join(cwd, d)
                st.rerun()

        if len(dirs) > 40:
            st.caption(f"… and {len(dirs) - 40} more folders")
        if not dirs:
            st.caption("(no subdirectories)")


def _render_file_browser(state_key: str, container, start: str = "", extensions: list = None):
    """Render an inline file browser. Updates session_state[state_key] on selection."""
    open_key = f"_browse_open_{state_key}"
    cwd_key = f"_browse_cwd_{state_key}"
    sel_key = f"_browse_sel_{state_key}"   # pending-selection key

    if open_key not in st.session_state:
        st.session_state[open_key] = False

    if container.button(
        "Browse file..." if not st.session_state[open_key] else "Close browser",
        key=f"_brtoggle_{state_key}",
        use_container_width=True,
    ):
        st.session_state[open_key] = not st.session_state[open_key]
        if st.session_state[open_key] and cwd_key not in st.session_state:
            st.session_state[cwd_key] = start or os.path.expanduser("~")
        st.rerun()

    if not st.session_state[open_key]:
        return

    cwd = st.session_state.get(cwd_key, os.path.expanduser("~"))
    with container.container(border=True):
        st.caption(f"📂  `{cwd}`")

        dirs, files = _list_dir_safe(cwd)

        # Filter by extension
        if extensions:
            ext_set = set(extensions)
            files = [f for f in files if any(f.endswith(e) for e in ext_set)]

        # Parent button
        parent = os.path.dirname(cwd)
        if parent != cwd:
            if st.button("⬆ Parent", key=f"_bfp_{state_key}", use_container_width=True):
                st.session_state[cwd_key] = parent
                st.rerun()

        # Subdirectories
        for d in dirs[:30]:
            if st.button(f"📁  {d}", key=f"_bfd_{state_key}_{d}", use_container_width=True):
                st.session_state[cwd_key] = os.path.join(cwd, d)
                st.rerun()

        if len(dirs) > 30:
            st.caption(f"… and {len(dirs) - 30} more folders")

        # Files
        if files:
            st.divider()
            for fn in files[:50]:
                if st.button(f"📄  {fn}", key=f"_bff_{state_key}_{fn}", use_container_width=True):
                    st.session_state[sel_key] = os.path.join(cwd, fn)
                    st.session_state[open_key] = False
                    st.rerun()
            if len(files) > 50:
                st.caption(f"… and {len(files) - 50} more files")
        elif not dirs:
            st.caption("(empty directory)")


# ═════════════════════════════════════════════════════════════════════════
#  Helper: Load Config
# ═════════════════════════════════════════════════════════════════════════

def _load_cfg() -> dict:
    """Load ORCA config.yaml and return as plain dict."""
    for candidate in ["config.yaml", "global_config.yaml"]:
        path = os.path.join(ORCA_ROOT, candidate)
        if os.path.isfile(path):
            try:
                return load_config(path).to_dict()
            except Exception:
                pass
    return {}


def _load_rules(preset: str, custom_path: str = "") -> dict:
    """Load rules from preset name or custom path."""
    import yaml
    if custom_path and os.path.isfile(custom_path):
        rules_path = custom_path
    else:
        preset_map = {
            "kernel": "linux_kernel.yaml",
            "uboot": "uboot.yaml",
            "yocto": "yocto.yaml",
            "custom": "custom.yaml",
        }
        rules_path = os.path.join(ORCA_ROOT, "rules", preset_map.get(preset, "linux_kernel.yaml"))
    try:
        with open(rules_path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


# ═════════════════════════════════════════════════════════════════════════
#  Helper: Finding Accessors  (handle both dict and dataclass)
# ═════════════════════════════════════════════════════════════════════════

def _fg(finding, key, default=""):
    """Get attribute from Finding (dict or dataclass)."""
    if isinstance(finding, dict):
        return finding.get(key, default)
    return getattr(finding, key, default)


def _finding_key(f) -> str:
    """Unique string key for a finding."""
    return f"{_fg(f,'file_path')}:{_fg(f,'line_number')}:{_fg(f,'rule_id')}"


# ═════════════════════════════════════════════════════════════════════════
#  Sidebar
# ═════════════════════════════════════════════════════════════════════════

def _sidebar():
    # Sync any pending browser selections BEFORE widgets are instantiated.
    _flush_browse_selections()

    with st.sidebar:
        st.image("https://img.icons8.com/fluency/96/orca.png", width=64)
        st.title("ORCA")
        st.caption("Open-source Rules Compliance Auditor")
        st.divider()

        # ── Input source ────────────────────────────────────────────
        st.subheader("Source")
        input_mode = st.radio(
            "Input type",
            ["Codebase directory", "Single file"],
            horizontal=True,
            label_visibility="collapsed",
        )
        if input_mode == "Codebase directory":
            codebase = st.text_input(
                "Codebase path",
                help="Absolute or relative path",
                key="browse_codebase",
            )
            _render_folder_browser(
                "browse_codebase", st.sidebar,
                start=codebase if os.path.isdir(codebase) else "",
            )
        else:
            codebase = st.text_input(
                "File path",
                help="Path to a single source file",
                key="browse_file",
            )
            _render_file_browser(
                "browse_file", st.sidebar,
                start=os.path.dirname(codebase) if codebase else "",
            )

        st.divider()

        # ── Rules ───────────────────────────────────────────────────
        st.subheader("Rules")
        preset = st.selectbox("Preset", ["kernel", "uboot", "yocto", "custom"], index=0)
        custom_rules = st.text_input(
            "Custom rules YAML (optional)",
            key="browse_rules",
        )
        _render_file_browser(
            "browse_rules", st.sidebar,
            extensions=[".yaml", ".yml"],
        )

        st.divider()

        # ── Analysis mode ───────────────────────────────────────────
        st.subheader("Analysis Mode")
        mode = st.radio(
            "Mode",
            ["Static only", "LLM only", "Static + LLM"],
            index=0,
            help="Static = regex/heuristic checks. LLM = semantic analysis via API.",
        )
        mode_map = {"Static only": "static", "LLM only": "llm", "Static + LLM": "both"}
        st.session_state["analysis_mode"] = mode_map[mode]

        # ── Domains ─────────────────────────────────────────────────
        st.subheader("Domains")
        all_domains = ["style", "license", "structure", "patch"]
        selected_domains = st.multiselect("Select domains", all_domains, default=all_domains)

        st.divider()

        # ── Context Layer ────────────────────────────────────────────
        st.subheader("Context Layer")
        enable_context = st.checkbox(
            "Enable Context-Aware Analysis",
            value=False,
            help="Pre-analyzes code structure (headers, constraints) "
                 "to enrich LLM prompts and reduce false positives.",
        )
        if enable_context:
            with st.expander("Context Options", expanded=False):
                ctx_header = st.checkbox("Header resolution (#include)", value=True,
                                         help="Resolve #include chains, parse enums/structs/macros/typedefs")
                ctx_gen_constraints = st.checkbox("Auto-generate constraints", value=False,
                                                   help="Scan codebase for enums/structs/macros and generate constraint rules")
                ctx_constraints_dir = st.text_input("Constraints directory", value="./constraints/",
                                                     help="Path to constraint .md files for LLM injection")
        else:
            ctx_header = True
            ctx_gen_constraints = False
            ctx_constraints_dir = "./constraints/"

        st.divider()

        # ── HITL Feedback ────────────────────────────────────────────
        st.subheader("HITL Feedback")
        enable_hitl = st.checkbox(
            "Enable Human-in-the-Loop",
            value=False,
            help="When enabled, past review decisions enrich findings via the RAG pipeline. "
                 "Feedback is stored in the PostgreSQL database.",
        )

        st.divider()

        # ── Advanced ────────────────────────────────────────────────
        with st.expander("Advanced Options"):
            max_files = st.number_input("Max files", value=10000, min_value=1, step=100)
            batch_size = st.number_input("Batch size", value=50, min_value=1, step=10)
            report_fmts = st.multiselect("Report formats", ["json", "excel", "html"], default=["json", "excel"])
            out_dir = st.text_input(
                "Output directory",
                key="browse_outdir",
            )
            _render_folder_browser(
                "browse_outdir", st.sidebar,
                start=out_dir if os.path.isdir(out_dir) else "",
            )

        st.divider()

        # ── Run button ──────────────────────────────────────────────
        run_disabled = st.session_state.get("audit_running", False)
        run_clicked = st.button(
            "Run Analysis" if not run_disabled else "Running...",
            type="primary",
            use_container_width=True,
            disabled=run_disabled,
        )

    return {
        "codebase": codebase,
        "input_mode": input_mode,
        "preset": preset,
        "custom_rules": custom_rules,
        "domains": selected_domains,
        "max_files": max_files,
        "batch_size": batch_size,
        "enable_hitl": enable_hitl,
        "enable_context": enable_context,
        "ctx_header": ctx_header,
        "ctx_gen_constraints": ctx_gen_constraints,
        "ctx_constraints_dir": ctx_constraints_dir,
        "report_fmts": report_fmts,
        "out_dir": out_dir,
        "run_clicked": run_clicked,
    }


# ═════════════════════════════════════════════════════════════════════════
#  Run Analysis
# ═════════════════════════════════════════════════════════════════════════

def _run_analysis(params: dict):
    """Execute the audit (and optionally LLM) pipeline."""
    st.session_state["audit_running"] = True
    st.session_state["fix_results"] = {}
    st.session_state["feedback"] = {}

    cfg = _load_cfg()
    rules = _load_rules(params["preset"], params["custom_rules"])
    st.session_state["rules"] = rules
    st.session_state["cfg"] = cfg

    codebase = params["codebase"]
    out_dir = params["out_dir"]
    os.makedirs(out_dir, exist_ok=True)

    progress = st.progress(0, text="Initializing...")

    # ── Phase 1: Static Analysis ────────────────────────────────────
    report = None
    mode = st.session_state["analysis_mode"]

    if mode in ("static", "both"):
        progress.progress(10, text="Phase 1/4 — Static analysis...")
        static_agent = ComplianceStaticAgent(rules=rules, config=cfg)
        report = static_agent.run_audit(
            codebase_path=codebase,
            output_dir=out_dir,
            domains=params["domains"],
        )

    # ── Phase 2: LLM Analysis (optional) ────────────────────────────
    if mode in ("llm", "both"):
        progress.progress(40, text="Phase 2/4 — LLM semantic analysis...")
        try:
            from utils.llm_tools import LLMClient
            from agents.compliance_audit_agent import ComplianceAuditAgent

            llm_cfg = cfg.get("llm", {})
            llm_client = LLMClient(llm_cfg if isinstance(llm_cfg, dict) else {})
            audit_agent = ComplianceAuditAgent(
                llm_client=llm_client, rules=rules, config=cfg,
                constraints_dir=params.get("ctx_constraints_dir", "./constraints"))
            llm_report = audit_agent.run_analysis(
                codebase_path=codebase, output_dir=out_dir, domains=params["domains"],
            )
            if report is None:
                report = llm_report
            else:
                report.findings.extend(llm_report.findings)
        except Exception as e:
            st.warning(f"LLM analysis unavailable: {e}")
            if report is None:
                # Fallback to static if LLM-only was chosen
                static_agent = ComplianceStaticAgent(rules=rules, config=cfg)
                report = static_agent.run_audit(
                    codebase_path=codebase, output_dir=out_dir, domains=params["domains"],
                )

    # ── Phase 3: Report generation ──────────────────────────────────
    progress.progress(70, text="Phase 3/4 — Generating reports...")
    _generate_reports_ui(report, out_dir, params["report_fmts"], rules)

    # ── Phase 4: HITL enrichment ────────────────────────────────────
    if params["enable_hitl"]:
        progress.progress(85, text="Phase 4/4 — HITL enrichment...")
        try:
            from hitl.feedback_store import FeedbackStore
            from hitl.rag_retriever import RAGRetriever
            hitl_cfg = cfg.get("hitl", {})
            store = FeedbackStore(hitl_cfg if isinstance(hitl_cfg, dict) else {})
            rag = RAGRetriever(store, config=hitl_cfg)
            for finding in report.findings:
                ctx = rag.retrieve_context(finding)
                if ctx.recommendation and hasattr(finding, 'suggestion'):
                    finding.suggestion = f"{finding.suggestion} [HITL: {ctx.recommendation}]"
            store.close()
        except Exception as e:
            logger.warning(f"HITL enrichment skipped: {e}")

    progress.progress(100, text="Complete!")
    time.sleep(0.3)
    progress.empty()

    st.session_state["report"] = report
    st.session_state["findings"] = report.findings if report else []
    st.session_state["audit_running"] = False

    # Save to history
    st.session_state["history"].append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "codebase": codebase,
        "mode": mode,
        "findings": len(report.findings) if report else 0,
        "grade": report.overall_grade if report else "?",
    })


def _generate_reports_ui(report, out_dir, formats, rules):
    """Generate reports (thin wrapper around main.py logic)."""
    if not report:
        return
    os.makedirs(out_dir, exist_ok=True)

    if "json" in formats:
        try:
            from agents.parsers.report_parser import JSONReportGenerator
            JSONReportGenerator().generate(report, os.path.join(out_dir, "compliance_report.json"))
        except Exception:
            pass

    if "excel" in formats:
        try:
            from agents.adapters.excel_report_adapter import ExcelReportAdapter
            ExcelReportAdapter(rules=rules, config={}).generate_report(
                report, os.path.join(out_dir, "compliance_review.xlsx"))
        except Exception:
            pass

    if "html" in formats:
        try:
            from agents.parsers.report_parser import HTMLDashboardGenerator
            HTMLDashboardGenerator().generate(report, os.path.join(out_dir, "compliance_dashboard.html"))
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════════════
#  Dashboard Rendering
# ═════════════════════════════════════════════════════════════════════════

def _render_dashboard():
    """Render the main dashboard area."""
    report = _ss("report")
    findings = _ss("findings", [])

    if report is None:
        _render_welcome()
        return

    # ── Header Metrics ──────────────────────────────────────────────
    st.markdown("## Audit Results")
    grade = report.overall_grade
    col_grade, col_files, col_findings, col_score, col_time = st.columns([1, 1, 1, 1, 1])

    with col_grade:
        st.markdown(
            f'<div class="stat-card"><div class="grade-badge grade-{grade}">{grade}</div>'
            f'<p style="margin-top:8px">Overall Grade</p></div>',
            unsafe_allow_html=True,
        )

    file_count = getattr(report, "file_count", 0) or len(set(_fg(f, "file_path") for f in findings))
    with col_files:
        st.markdown(f'<div class="stat-card"><h2>{file_count}</h2><p>Files Scanned</p></div>', unsafe_allow_html=True)

    with col_findings:
        st.markdown(f'<div class="stat-card"><h2>{len(findings)}</h2><p>Total Findings</p></div>', unsafe_allow_html=True)

    score_pct = report.scores.get("overall", 0) * 100 if hasattr(report, "scores") and report.scores else 0
    with col_score:
        st.markdown(f'<div class="stat-card"><h2>{score_pct:.0f}%</h2><p>Compliance Score</p></div>', unsafe_allow_html=True)

    elapsed = sum(report.timing.values()) if hasattr(report, "timing") and report.timing else 0
    with col_time:
        st.markdown(f'<div class="stat-card"><h2>{elapsed:.1f}s</h2><p>Elapsed Time</p></div>', unsafe_allow_html=True)

    st.divider()

    # ── Tabs ────────────────────────────────────────────────────────
    tab_findings, tab_domains, tab_fix, tab_feedback, tab_reports, tab_history = st.tabs([
        f"Findings ({len(findings)})",
        "Domain Breakdown",
        "Fix & Remediate",
        "User Feedback",
        "Reports & Export",
        "History",
    ])

    with tab_findings:
        _render_findings_tab(findings)

    with tab_domains:
        _render_domain_tab(report, findings)

    with tab_fix:
        _render_fix_tab(findings)

    with tab_feedback:
        _render_feedback_tab(findings)

    with tab_reports:
        _render_reports_tab()

    with tab_history:
        _render_history_tab()


# ═════════════════════════════════════════════════════════════════════════
#  Welcome Screen
# ═════════════════════════════════════════════════════════════════════════

def _render_welcome():
    st.markdown("## Welcome to ORCA")
    st.markdown(
        "Configure your analysis in the **sidebar** and click **Run Analysis** to start.\n\n"
        "ORCA will scan your C/C++ codebase for compliance issues across four domains: "
        "**coding style**, **license compliance**, **code structure**, and **patch format**."
    )
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("#### Static Analysis")
        st.markdown(
            "Fast regex/heuristic checks using 7 built-in analyzers and 41 rules. "
            "No API key required."
        )
    with col2:
        st.markdown("#### Context Analysis")
        st.markdown(
            "Pre-analyzes headers and auto-generates constraints "
            "to enrich LLM prompts and reduce false positives."
        )
    with col3:
        st.markdown("#### LLM Semantic Analysis")
        st.markdown(
            "Context-enriched reasoning powered by Claude, GPT, or QGenie. "
            "Catches issues that regex cannot."
        )
    with col4:
        st.markdown("#### Fixer Workflow")
        st.markdown(
            "3-mode HITL repair: Excel-driven fixes, single-patch, and batch-patch "
            "with auto-remediation and feedback learning."
        )


# ═════════════════════════════════════════════════════════════════════════
#  Findings Tab
# ═════════════════════════════════════════════════════════════════════════

def _render_findings_tab(findings: list):
    if not findings:
        st.info("No findings. Your code is fully compliant!")
        return

    # ── Filters ─────────────────────────────────────────────────────
    fc1, fc2, fc3, fc4 = st.columns(4)
    severities = sorted(set(_fg(f, "severity") for f in findings))
    categories = sorted(set(_fg(f, "category") for f in findings))
    files = sorted(set(_fg(f, "file_path") for f in findings))

    with fc1:
        sev_filter = st.multiselect("Severity", severities, default=severities, key="f_sev")
    with fc2:
        cat_filter = st.multiselect("Domain / Category", categories, default=categories, key="f_cat")
    with fc3:
        file_filter = st.multiselect("File", files, default=files, key="f_file")
    with fc4:
        search = st.text_input("Search", "", key="f_search", placeholder="rule ID, message...")

    filtered = [
        f for f in findings
        if _fg(f, "severity") in sev_filter
        and _fg(f, "category") in cat_filter
        and _fg(f, "file_path") in file_filter
        and (not search or search.lower() in (
            _fg(f, "rule_id") + _fg(f, "message") + _fg(f, "suggestion")
        ).lower())
    ]

    st.caption(f"Showing {len(filtered)} of {len(findings)} findings")

    # ── Findings list ───────────────────────────────────────────────
    for i, f in enumerate(filtered):
        sev = _fg(f, "severity")
        rule = _fg(f, "rule_id")
        msg = _fg(f, "message")
        fp = _fg(f, "file_path")
        ln = _fg(f, "line_number")
        suggestion = _fg(f, "suggestion")
        snippet = _fg(f, "code_snippet")
        conf = _fg(f, "confidence", 0)

        with st.expander(
            f'`{rule}` — {msg[:90]}{"..." if len(msg) > 90 else ""}',
            expanded=False,
        ):
            c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
            with c1:
                st.markdown(f"**File:** `{fp}`  **Line:** {ln}")
            with c2:
                st.markdown(f'<span class="sev-pill sev-{sev}">{sev}</span>', unsafe_allow_html=True)
            with c3:
                st.markdown(f"**Category:** {_fg(f, 'category')}")
            with c4:
                st.markdown(f"**Confidence:** {conf:.0%}" if isinstance(conf, (int, float)) else "")

            st.markdown(f"**Message:** {msg}")
            if suggestion:
                st.info(f"**Suggestion:** {suggestion}")
            if snippet:
                st.code(snippet, language="c")


# ═════════════════════════════════════════════════════════════════════════
#  Domain Breakdown Tab
# ═════════════════════════════════════════════════════════════════════════

def _render_domain_tab(report, findings):
    if not findings:
        st.info("No findings to display.")
        return

    # Group by category
    by_cat = defaultdict(list)
    for f in findings:
        by_cat[_fg(f, "category")].append(f)

    # Severity distribution
    st.markdown("### Severity Distribution")
    sev_counts = defaultdict(int)
    for f in findings:
        sev_counts[_fg(f, "severity")] += 1

    cols = st.columns(4)
    for i, sev in enumerate(["CRITICAL", "HIGH", "MEDIUM", "LOW"]):
        with cols[i]:
            count = sev_counts.get(sev, 0)
            st.metric(sev, count)

    st.divider()

    # Domain scores
    st.markdown("### Domain Scores")
    domain_scores = report.domain_scores if hasattr(report, "domain_scores") else {}

    if domain_scores:
        for domain, score in domain_scores.items():
            col_name, col_bar = st.columns([1, 3])
            with col_name:
                st.markdown(f"**{domain}**")
            with col_bar:
                st.progress(min(score, 1.0), text=f"{score:.0%}")
    else:
        # Build from findings
        for cat, cat_findings in sorted(by_cat.items()):
            sev_summary = defaultdict(int)
            for f in cat_findings:
                sev_summary[_fg(f, "severity")] += 1
            summary_str = " | ".join(f"{s}: {c}" for s, c in sorted(sev_summary.items()))
            st.markdown(f"**{cat}** — {len(cat_findings)} findings ({summary_str})")

    st.divider()

    # Files with most findings
    st.markdown("### Top Files by Finding Count")
    by_file = defaultdict(int)
    for f in findings:
        by_file[_fg(f, "file_path")] += 1
    top_files = sorted(by_file.items(), key=lambda x: -x[1])[:15]
    if top_files:
        import pandas as pd
        df = pd.DataFrame(top_files, columns=["File", "Findings"])
        st.bar_chart(df.set_index("File"))


# ═════════════════════════════════════════════════════════════════════════
#  Fix & Remediate Tab
# ═════════════════════════════════════════════════════════════════════════

def _render_fix_tab(findings: list):
    if not findings:
        st.info("No findings to fix.")
        return

    st.markdown("### Automated Fix Options")
    st.markdown(
        "ORCA can attempt to auto-fix certain compliance issues. "
        "Choose a domain and mode below."
    )

    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        fix_domain = st.selectbox("Fix domain", ["all", "style", "license", "structure", "patch"], key="fix_dom")
    with fc2:
        fix_mode = st.radio("Mode", ["Dry run (preview)", "Apply fixes"], horizontal=True, key="fix_mode")
    with fc3:
        fix_with_backup = st.checkbox("Create backups", value=True, key="fix_bk")

    dry_run = fix_mode == "Dry run (preview)"

    if st.button("Run Fixer", type="primary", key="fix_btn"):
        _run_fixer(findings, fix_domain, dry_run)

    # Display results
    fix_results = _ss("fix_results", {})
    if fix_results:
        st.divider()
        st.markdown("### Fix Results")

        total_fixed = sum(r.get("fixed_count", 0) for r in fix_results.values())
        total_remaining = sum(r.get("remaining_count", 0) for r in fix_results.values())

        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            st.metric("Files Processed", len(fix_results))
        with rc2:
            st.metric("Issues Fixed", total_fixed)
        with rc3:
            st.metric("Remaining", total_remaining)

        for fp, result in fix_results.items():
            status_class = "fix-applied" if result.get("applied") else "fix-dryrun"
            status_label = "APPLIED" if result.get("applied") else "DRY RUN"

            with st.expander(f"`{fp}` — {result.get('fixed_count', 0)} fixed"):
                st.markdown(f'Status: <span class="{status_class}">{status_label}</span>', unsafe_allow_html=True)

                if result.get("backup_path"):
                    st.caption(f"Backup: {result['backup_path']}")

                # Show diffs
                diffs = result.get("diffs", [])
                if diffs:
                    st.markdown("**Diff:**")
                    st.code("\n".join(diffs), language="diff")

                # Show audit trail
                trail = result.get("audit_trail", [])
                if trail:
                    st.markdown("**Audit Trail:**")
                    for entry in trail:
                        st.caption(f"  {entry}")


def _run_fixer(findings, domain, dry_run):
    """Execute the fixer agent."""
    from agents.compliance_fixer_agent import ComplianceFixerAgent
    cfg = _ss("cfg", {})

    fixer = ComplianceFixerAgent(config=cfg)

    findings_by_file = defaultdict(list)
    for f in findings:
        fp = _fg(f, "file_path")
        findings_by_file[fp].append(f)

    results = {}
    progress = st.progress(0, text="Fixing...")
    total = len(findings_by_file)

    for idx, (fp, file_findings) in enumerate(findings_by_file.items()):
        progress.progress((idx + 1) / max(total, 1), text=f"Fixing {os.path.basename(fp)}...")
        try:
            result = fixer.apply_fixes(
                file_path=fp,
                findings=file_findings,
                solutions={},
                dry_run=dry_run,
                domain_filter=domain if domain != "all" else None,
            )
            results[fp] = result.to_dict()
        except Exception as e:
            results[fp] = {"error": str(e), "fixed_count": 0, "remaining_count": len(file_findings)}

    progress.empty()
    st.session_state["fix_results"] = results


# ═════════════════════════════════════════════════════════════════════════
#  User Feedback Tab
# ═════════════════════════════════════════════════════════════════════════

def _render_feedback_tab(findings: list):
    if not findings:
        st.info("No findings to review.")
        return

    st.markdown("### Provide Feedback on Findings")
    st.markdown(
        "Your decisions are stored in the HITL feedback database and used to improve "
        "future audits via the RAG pipeline."
    )

    feedback = st.session_state.get("feedback", {})
    decision_options = ["— Select —", "FIX", "SKIP", "WAIVE", "NEEDS_REVIEW", "UPSTREAM_EXCEPTION"]

    # Summary
    decided = len([v for v in feedback.values() if v != "— Select —"])
    st.progress(decided / max(len(findings), 1), text=f"{decided}/{len(findings)} reviewed")

    st.divider()

    # Paginate
    page_size = 20
    total_pages = max(1, (len(findings) + page_size - 1) // page_size)
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, key="fb_page")
    start = (page - 1) * page_size
    page_findings = findings[start : start + page_size]

    for f in page_findings:
        key = _finding_key(f)
        sev = _fg(f, "severity")
        rule = _fg(f, "rule_id")
        msg = _fg(f, "message")
        fp = _fg(f, "file_path")
        ln = _fg(f, "line_number")
        current = feedback.get(key, "— Select —")

        col_info, col_decision = st.columns([3, 1])
        with col_info:
            st.markdown(
                f'<span class="sev-pill sev-{sev}">{sev}</span> '
                f'`{rule}` — {msg[:80]}  \n'
                f'<small>`{fp}:{ln}`</small>',
                unsafe_allow_html=True,
            )
        with col_decision:
            choice = st.selectbox(
                "Decision",
                decision_options,
                index=decision_options.index(current) if current in decision_options else 0,
                key=f"fb_{key}",
                label_visibility="collapsed",
            )
            feedback[key] = choice

    st.session_state["feedback"] = feedback

    st.divider()

    # Save feedback
    if st.button("Save Feedback to HITL Database", type="primary", key="fb_save"):
        _save_feedback(findings, feedback)


def _save_feedback(findings, feedback):
    """Persist feedback to the HITL PostgreSQL store."""
    try:
        from hitl.feedback_store import FeedbackStore
        cfg = _ss("cfg", {})
        hitl_cfg = cfg.get("hitl", {})
        store = FeedbackStore(hitl_cfg if isinstance(hitl_cfg, dict) else {})

        saved = 0
        for f in findings:
            key = _finding_key(f)
            decision = feedback.get(key, "— Select —")
            if decision == "— Select —":
                continue
            store.record_decision(
                project="orca-ui",
                file_path=_fg(f, "file_path"),
                rule_id=_fg(f, "rule_id"),
                violation_text=_fg(f, "message"),
                decision=decision,
                constraints=None,
                confidence=_fg(f, "confidence", 0.5),
            )
            saved += 1

        store.close()
        db_name = hitl_cfg.get("db_name", "orca_feedback")
        st.success(f"Saved {saved} decisions to PostgreSQL (`{db_name}`)")
    except Exception as e:
        st.error(f"Failed to save feedback: {e}")


# ═════════════════════════════════════════════════════════════════════════
#  Reports Tab
# ═════════════════════════════════════════════════════════════════════════

def _render_reports_tab():
    report = _ss("report")
    if not report:
        st.info("Run an analysis first to generate reports.")
        return

    out_dir = "./out"
    st.markdown("### Generated Reports")

    report_files = {
        "JSON":  os.path.join(out_dir, "compliance_report.json"),
        "Excel": os.path.join(out_dir, "compliance_review.xlsx"),
        "HTML":  os.path.join(out_dir, "compliance_dashboard.html"),
    }

    for label, path in report_files.items():
        if os.path.isfile(path):
            size_kb = os.path.getsize(path) / 1024
            col_name, col_dl = st.columns([3, 1])
            with col_name:
                st.markdown(f"**{label}** — `{path}` ({size_kb:.1f} KB)")
            with col_dl:
                with open(path, "rb") as fh:
                    st.download_button(
                        f"Download {label}",
                        data=fh.read(),
                        file_name=os.path.basename(path),
                        key=f"dl_{label}",
                    )

    st.divider()

    # JSON preview
    json_path = report_files["JSON"]
    if os.path.isfile(json_path):
        with st.expander("Preview JSON report"):
            with open(json_path) as fh:
                data = json.load(fh)
            st.json(data)

    # Re-generate
    st.divider()
    st.markdown("### Re-generate Reports")
    regen_fmts = st.multiselect("Formats", ["json", "excel", "html"], default=["json", "excel", "html"], key="regen_fmts")
    if st.button("Re-generate", key="regen_btn"):
        rules = _ss("rules", {})
        _generate_reports_ui(report, out_dir, regen_fmts, rules)
        st.success("Reports regenerated!")
        st.rerun()


# ═════════════════════════════════════════════════════════════════════════
#  History Tab
# ═════════════════════════════════════════════════════════════════════════

def _render_history_tab():
    history = _ss("history", [])
    if not history:
        st.info("No audit history yet. Run an analysis to see results here.")
        return

    st.markdown("### Past Audits")
    for entry in reversed(history):
        col_ts, col_cb, col_mode, col_grade, col_count = st.columns([2, 2, 1, 1, 1])
        with col_ts:
            st.caption(entry["timestamp"])
        with col_cb:
            st.markdown(f"`{entry['codebase']}`")
        with col_mode:
            st.markdown(entry["mode"])
        with col_grade:
            g = entry["grade"]
            st.markdown(f'<span class="grade-badge grade-{g}" style="font-size:1.2rem;width:36px;height:36px;line-height:36px">{g}</span>', unsafe_allow_html=True)
        with col_count:
            st.markdown(f"{entry['findings']} findings")


# ═════════════════════════════════════════════════════════════════════════
#  Main
# ═════════════════════════════════════════════════════════════════════════

def main():
    params = _sidebar()

    if params["run_clicked"]:
        _run_analysis(params)
        st.rerun()

    _render_dashboard()


if __name__ == "__main__":
    main()
