"""Shared test helpers for ORCA test suite."""
import os
import sys
import tempfile
import shutil

# Ensure project root is in path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def get_fixtures_dir():
    """Return path to test fixtures directory."""
    return FIXTURES_DIR


def load_sample_good_c():
    """Return content of sample_good.c."""
    with open(os.path.join(FIXTURES_DIR, "sample_good.c")) as f:
        return f.read()


def load_sample_bad_c():
    """Return content of sample_bad.c."""
    with open(os.path.join(FIXTURES_DIR, "sample_bad.c")) as f:
        return f.read()


def load_sample_good_h():
    """Return content of sample_good.h."""
    with open(os.path.join(FIXTURES_DIR, "sample_good.h")) as f:
        return f.read()


def load_sample_bad_h():
    """Return content of sample_bad.h."""
    with open(os.path.join(FIXTURES_DIR, "sample_bad.h")) as f:
        return f.read()


def load_kernel_rules():
    """Load Linux kernel rules."""
    import yaml
    rules_path = os.path.join(PROJECT_ROOT, "rules", "linux_kernel.yaml")
    with open(rules_path) as f:
        return yaml.safe_load(f)


def get_default_config():
    """Return default config dict."""
    return {
        "paths": {"codebase": ".", "output": "./out"},
        "llm": {"provider": "mock", "mock_mode": True},
        "compliance": {"enabled_domains": ["style", "license", "structure", "patch"]},
        "hitl": {"enabled": False, "db_host": "localhost", "db_name": "orca_feedback"},
    }


def create_temp_dir():
    """Create and return a temporary directory."""
    return tempfile.mkdtemp(prefix="orca_test_")


def cleanup_temp_dir(d):
    """Clean up a temporary directory."""
    shutil.rmtree(d, ignore_errors=True)


def create_temp_codebase(temp_dir):
    """Create a temp codebase with fixture files for integration testing."""
    src_dir = os.path.join(temp_dir, "src")
    os.makedirs(src_dir)
    # Copy fixtures
    for fname in os.listdir(FIXTURES_DIR):
        src = os.path.join(FIXTURES_DIR, fname)
        dst = os.path.join(src_dir, fname)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
    return src_dir
