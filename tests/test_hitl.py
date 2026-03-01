"""Tests for ORCA HITL pipeline (PostgreSQL-backed).

These tests require a running PostgreSQL instance.  If psycopg2 is not
installed or the database is unreachable the tests are automatically
skipped so they never break a CI pipeline that lacks a PG service.

Configure via environment variables:
    ORCA_PG_HOST      (default: localhost)
    ORCA_PG_PORT      (default: 5432)
    ORCA_PG_USER      (default: orca)
    ORCA_PG_PASSWORD   (default: empty)
    ORCA_PG_DATABASE  (default: orca_feedback)
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Skip guard ────────────────────────────────────────────────────────────
try:
    import psycopg2

    _TEST_CFG = {
        "db_host": os.environ.get("ORCA_PG_HOST", "localhost"),
        "db_port": int(os.environ.get("ORCA_PG_PORT", "5432")),
        "db_user": os.environ.get("ORCA_PG_USER", "orca"),
        "db_password": os.environ.get("ORCA_PG_PASSWORD", ""),
        "db_name": os.environ.get("ORCA_PG_DATABASE", "orca_feedback"),
    }

    # Quick connectivity check
    _conn = psycopg2.connect(
        host=_TEST_CFG["db_host"],
        port=_TEST_CFG["db_port"],
        user=_TEST_CFG["db_user"],
        password=_TEST_CFG["db_password"],
        dbname=_TEST_CFG["db_name"],
    )
    _conn.close()
    PG_AVAILABLE = True
except Exception:
    PG_AVAILABLE = False
    _TEST_CFG = {}


def _cleanup_test_rows(store, project="__test__"):
    """Delete rows inserted by tests so the DB stays clean."""
    try:
        cur = store._cursor()
        cur.execute(
            "DELETE FROM orca.compliance_decisions WHERE project = %s",
            (project,),
        )
        cur.close()
    except Exception:
        pass


@unittest.skipUnless(PG_AVAILABLE, "PostgreSQL not available — skipping HITL tests")
class TestFeedbackStore(unittest.TestCase):
    def setUp(self):
        from hitl.feedback_store import FeedbackStore
        self.store = FeedbackStore(_TEST_CFG)
        _cleanup_test_rows(self.store)

    def tearDown(self):
        _cleanup_test_rows(self.store)
        self.store.close()

    def test_record_and_query(self):
        self.store.record_decision(
            project="__test__", file_path="test.c", rule_id="style_001",
            violation_text="Test violation", decision="FIX",
        )
        results = self.store.query_by_rule("style_001", project="__test__")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].decision, "FIX")

    def test_decision_stats(self):
        self.store.record_decision("__test__", "a.c", "r1", "v1", "FIX")
        self.store.record_decision("__test__", "b.c", "r1", "v2", "SKIP")
        self.store.record_decision("__test__", "c.c", "r1", "v3", "FIX")
        stats = self.store.get_decision_stats("r1")
        self.assertGreaterEqual(stats.get("FIX", 0), 2)
        self.assertGreaterEqual(stats.get("SKIP", 0), 1)

    def test_export_import(self):
        self.store.record_decision("__test__", "a.c", "r_exp", "v1", "WAIVE")
        export_path = tempfile.mktemp(suffix=".json")
        self.store.export_to_json(export_path)

        with open(export_path) as f:
            data = json.load(f)
        self.assertGreater(len(data), 0)

        # Import into the same store (idempotent — new row)
        count = self.store.import_from_json(export_path)
        self.assertGreater(count, 0)

        os.unlink(export_path)

    def test_sqlite_path_raises(self):
        """Passing an old SQLite path should raise a clear error."""
        from hitl.feedback_store import FeedbackStore
        with self.assertRaises(ValueError):
            FeedbackStore("./orca_feedback.db")
        with self.assertRaises(ValueError):
            FeedbackStore(":memory:")


@unittest.skipUnless(PG_AVAILABLE, "PostgreSQL not available — skipping HITL tests")
class TestRAGRetriever(unittest.TestCase):
    def setUp(self):
        from hitl.feedback_store import FeedbackStore
        from hitl.rag_retriever import RAGRetriever
        self.store = FeedbackStore(_TEST_CFG)
        _cleanup_test_rows(self.store)
        self.retriever = RAGRetriever(self.store)

    def tearDown(self):
        _cleanup_test_rows(self.store)
        self.store.close()

    def test_retrieves_context(self):
        from agents.analyzers.base_analyzer import Finding
        self.store.record_decision(
            "__test__", "a.c", "style_001", "violation", "FIX", reviewer="alice",
        )

        finding = Finding("b.c", 10, 1, "medium", "style", "style_001",
                          "same rule", "", "", 0.9, "test")
        context = self.retriever.retrieve_context(finding)
        self.assertGreater(len(context.past_decisions), 0)


if __name__ == "__main__":
    unittest.main()
