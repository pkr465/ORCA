"""PostgreSQL-backed decision persistence for HITL feedback memory.

Uses psycopg2 for PostgreSQL connectivity.  Connection parameters are
resolved from an explicit ``db_url`` (DSN string) **or** individual
``db_host / db_port / db_name / db_user / db_password`` keys, **or**
environment variables (``ORCA_PG_*``).

Backward-compatibility: if ``store_path`` is the *only* key provided and
it ends with ``.db`` (i.e. an old SQLite path), a clear error is raised
telling the operator to run ``db/setup_db.py --migrate-from``.
"""

import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

DECISION_TYPES = [
    "FIX", "SKIP", "WAIVE", "FIX_WITH_CONSTRAINTS",
    "NEEDS_REVIEW", "UPSTREAM_EXCEPTION",
]

SCHEMA = "orca"


# ── Data Model ────────────────────────────────────────────────────────────

@dataclass
class ComplianceDecision:
    """Represents a single compliance decision record."""
    id: Optional[int] = None
    project: str = ""
    file_path: str = ""
    rule_id: str = ""
    violation_text: str = ""
    decision: str = ""
    constraints: Optional[str] = None
    reviewer: Optional[str] = None
    timestamp: str = ""
    confidence: float = 1.0

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


# ── Connection Helpers ────────────────────────────────────────────────────

def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _resolve_dsn(cfg: dict) -> str:
    """Build a PostgreSQL DSN from config dict or env vars.

    Priority: cfg["db_url"] > individual cfg keys > ORCA_PG_* env vars.
    """
    if cfg.get("db_url"):
        return cfg["db_url"]

    host = cfg.get("db_host") or _env("ORCA_PG_HOST", "localhost")
    port = cfg.get("db_port") or _env("ORCA_PG_PORT", "5432")
    user = cfg.get("db_user") or _env("ORCA_PG_USER", "orca")
    password = cfg.get("db_password") or _env("ORCA_PG_PASSWORD", "")
    dbname = cfg.get("db_name") or _env("ORCA_PG_DATABASE", "orca_feedback")

    parts = [f"host={host}", f"port={port}", f"dbname={dbname}", f"user={user}"]
    if password:
        parts.append(f"password={password}")
    return " ".join(parts)


# ── FeedbackStore ─────────────────────────────────────────────────────────

class FeedbackStore:
    """Manages persistent storage of compliance decisions using PostgreSQL."""

    def __init__(self, dsn_or_cfg=None, **kwargs):
        """Initialize feedback store.

        Args:
            dsn_or_cfg: One of:
                - A PostgreSQL DSN string (``host=... dbname=...``)
                - A ``dict`` with connection keys (``db_host``, ``db_port``, …)
                - ``None`` — falls back to env vars
            **kwargs: Extra keys forwarded to ``_resolve_dsn``.
        """
        if isinstance(dsn_or_cfg, dict):
            cfg = {**dsn_or_cfg, **kwargs}
            self.dsn = _resolve_dsn(cfg)
        elif isinstance(dsn_or_cfg, str):
            # Catch old SQLite paths that callers might still pass
            if dsn_or_cfg.endswith(".db") or dsn_or_cfg == ":memory:":
                raise ValueError(
                    f"SQLite path detected ('{dsn_or_cfg}'). "
                    "ORCA now uses PostgreSQL for HITL storage. "
                    "Run: python db/setup_db.py --migrate-from <sqlite-path> "
                    "and update config.yaml with PostgreSQL settings."
                )
            self.dsn = dsn_or_cfg
        else:
            self.dsn = _resolve_dsn(kwargs)

        self.connection = None
        self._connect()

    # ── Connection management ─────────────────────────────────────────

    def _connect(self):
        """Establish a PostgreSQL connection."""
        import psycopg2
        self.connection = psycopg2.connect(self.dsn)
        self.connection.autocommit = True
        logger.info("Connected to PostgreSQL")

    def _ensure_connection(self):
        """Reconnect if the connection was dropped."""
        if self.connection is None or self.connection.closed:
            self._connect()

    def _cursor(self):
        self._ensure_connection()
        return self.connection.cursor()

    # ── CRUD ──────────────────────────────────────────────────────────

    def record_decision(
        self,
        project: str,
        file_path: str,
        rule_id: str,
        violation_text: str,
        decision: str,
        constraints: Optional[str] = None,
        reviewer: Optional[str] = None,
        confidence: float = 1.0,
    ) -> int:
        """Record a compliance decision.

        Returns:
            ID of the recorded decision.
        """
        if decision not in DECISION_TYPES:
            raise ValueError(
                f"Invalid decision type: {decision}. Must be one of {DECISION_TYPES}"
            )

        timestamp = datetime.now().isoformat()

        cur = self._cursor()
        cur.execute(f"""
            INSERT INTO {SCHEMA}.compliance_decisions
                (project, file_path, rule_id, violation_text,
                 decision, constraints, reviewer, timestamp, confidence)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (project, file_path, rule_id, violation_text,
              decision, constraints, reviewer, timestamp, confidence))

        decision_id = cur.fetchone()[0]
        cur.close()
        logger.info(f"Recorded decision {decision_id}: {rule_id} -> {decision} for {file_path}")
        return decision_id

    def query_by_rule(
        self, rule_id: str, project: Optional[str] = None, limit: int = 10,
    ) -> List[ComplianceDecision]:
        """Query decisions by rule ID."""
        cur = self._cursor()

        if project:
            cur.execute(f"""
                SELECT id, project, file_path, rule_id, violation_text, decision,
                       constraints, reviewer, timestamp, confidence
                FROM {SCHEMA}.compliance_decisions
                WHERE rule_id = %s AND project = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """, (rule_id, project, limit))
        else:
            cur.execute(f"""
                SELECT id, project, file_path, rule_id, violation_text, decision,
                       constraints, reviewer, timestamp, confidence
                FROM {SCHEMA}.compliance_decisions
                WHERE rule_id = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """, (rule_id, limit))

        rows = cur.fetchall()
        cur.close()
        return [ComplianceDecision(*row) for row in rows]

    def query_by_file(self, file_path: str, limit: int = 10) -> List[ComplianceDecision]:
        """Query decisions by file path."""
        cur = self._cursor()
        cur.execute(f"""
            SELECT id, project, file_path, rule_id, violation_text, decision,
                   constraints, reviewer, timestamp, confidence
            FROM {SCHEMA}.compliance_decisions
            WHERE file_path = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """, (file_path, limit))

        rows = cur.fetchall()
        cur.close()
        return [ComplianceDecision(*row) for row in rows]

    def query_similar(
        self,
        rule_id: str,
        file_path: Optional[str] = None,
        project: Optional[str] = None,
        limit: int = 5,
    ) -> List[ComplianceDecision]:
        """Query similar decisions using multiple criteria."""
        cur = self._cursor()

        query = f"""
            SELECT id, project, file_path, rule_id, violation_text, decision,
                   constraints, reviewer, timestamp, confidence
            FROM {SCHEMA}.compliance_decisions
            WHERE rule_id = %s
        """
        params: list = [rule_id]

        if project:
            query += " AND project = %s"
            params.append(project)
        if file_path:
            query += " AND file_path = %s"
            params.append(file_path)

        query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)

        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        return [ComplianceDecision(*row) for row in rows]

    def get_decision_stats(self, rule_id: Optional[str] = None) -> Dict[str, int]:
        """Get statistics on decision types."""
        cur = self._cursor()

        if rule_id:
            cur.execute(f"""
                SELECT decision, COUNT(*) AS count
                FROM {SCHEMA}.compliance_decisions
                WHERE rule_id = %s
                GROUP BY decision
            """, (rule_id,))
        else:
            cur.execute(f"""
                SELECT decision, COUNT(*) AS count
                FROM {SCHEMA}.compliance_decisions
                GROUP BY decision
            """)

        stats = {d: 0 for d in DECISION_TYPES}
        for decision, count in cur.fetchall():
            stats[decision] = count

        cur.close()
        return stats

    def get_all_decisions(
        self, project: Optional[str] = None, limit: int = 100,
    ) -> List[ComplianceDecision]:
        """Get all decisions, optionally filtered by project."""
        cur = self._cursor()

        if project:
            cur.execute(f"""
                SELECT id, project, file_path, rule_id, violation_text, decision,
                       constraints, reviewer, timestamp, confidence
                FROM {SCHEMA}.compliance_decisions
                WHERE project = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """, (project, limit))
        else:
            cur.execute(f"""
                SELECT id, project, file_path, rule_id, violation_text, decision,
                       constraints, reviewer, timestamp, confidence
                FROM {SCHEMA}.compliance_decisions
                ORDER BY timestamp DESC
                LIMIT %s
            """, (limit,))

        rows = cur.fetchall()
        cur.close()
        return [ComplianceDecision(*row) for row in rows]

    def delete_decision(self, decision_id: int) -> bool:
        """Delete a decision by ID."""
        cur = self._cursor()
        cur.execute(
            f"DELETE FROM {SCHEMA}.compliance_decisions WHERE id = %s",
            (decision_id,),
        )
        deleted = cur.rowcount > 0
        cur.close()
        if deleted:
            logger.info(f"Deleted decision {decision_id}")
        return deleted

    # ── Import / Export ───────────────────────────────────────────────

    def export_to_json(self, output_path: str) -> None:
        """Export all decisions to JSON file."""
        cur = self._cursor()
        cur.execute(f"""
            SELECT id, project, file_path, rule_id, violation_text, decision,
                   constraints, reviewer, timestamp, confidence
            FROM {SCHEMA}.compliance_decisions
            ORDER BY timestamp DESC
        """)

        rows = cur.fetchall()
        cur.close()
        decisions_list = [ComplianceDecision(*row).to_dict() for row in rows]

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w") as f:
            json.dump(decisions_list, f, indent=2, default=str)

        logger.info(f"Exported {len(decisions_list)} decisions to {output_path}")

    def import_from_json(self, input_path: str) -> int:
        """Import decisions from JSON file."""
        with open(input_path, "r") as f:
            decisions_list = json.load(f)

        count = 0
        for item in decisions_list:
            self.record_decision(
                project=item.get("project", ""),
                file_path=item.get("file_path", ""),
                rule_id=item.get("rule_id", ""),
                violation_text=item.get("violation_text", ""),
                decision=item.get("decision", ""),
                constraints=item.get("constraints"),
                reviewer=item.get("reviewer"),
                confidence=item.get("confidence", 1.0),
            )
            count += 1

        logger.info(f"Imported {count} decisions from {input_path}")
        return count

    # ── Lifecycle ─────────────────────────────────────────────────────

    def close(self) -> None:
        """Close database connection."""
        if self.connection and not self.connection.closed:
            self.connection.close()
            logger.info("Closed PostgreSQL connection")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
