#!/usr/bin/env bash
# ============================================================================
# ORCA — Open-source Rules Compliance Auditor
# One-step installer for macOS, Linux, and Windows (WSL)
#
# Usage:
#   chmod +x install.sh
#   ./install.sh
#
# What this script does:
#   1. Detects OS and package manager
#   2. Installs Python 3.9+ (if needed)
#   3. Creates a virtual environment (.venv)
#   4. Installs all Python dependencies
#   5. Installs system tools (git, checkpatch.pl)
#   6. Installs ORCA as a CLI tool (pip install -e .)
#   7. Sets up .env from env.example (if not present)
#   8. Bootstraps PostgreSQL (via db/bootstrap_db.py)
#   9. Validates the installation
#  10. Prints launch instructions
#
# Environment variable overrides:
#   ORCA_PYTHON=python3.11    Override Python binary
#   ORCA_SKIP_DB=1            Skip PostgreSQL bootstrap
#   ORCA_SKIP_TOOLS=1         Skip system tool installation (git, checkpatch)
#   ORCA_VENV_DIR=.venv       Override virtual environment path
# ============================================================================

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── Logging ─────────────────────────────────────────────────────────────────
info()    { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
err()     { echo -e "${RED}[✗]${NC} $*"; }
step()    { echo -e "\n${CYAN}${BOLD}── $* ──${NC}"; }
substep() { echo -e "  ${BLUE}→${NC} $*"; }

# ── Project root ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Configurable ────────────────────────────────────────────────────────────
VENV_DIR="${ORCA_VENV_DIR:-.venv}"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=9

# ── Helper: check if command exists ─────────────────────────────────────────
has_cmd() { command -v "$1" &>/dev/null; }

# ── Helper: install a system package ────────────────────────────────────────
pkg_install() {
    local pkg_name="$1"
    local brew_name="${2:-$1}"
    local apt_name="${3:-$1}"

    substep "Installing ${pkg_name}..."
    case "$PKG_MANAGER" in
        brew)   brew install "$brew_name" 2>/dev/null || true ;;
        apt)    sudo apt-get install -y -qq "$apt_name" 2>/dev/null || true ;;
        dnf)    sudo dnf install -y "$apt_name" 2>/dev/null || true ;;
        yum)    sudo yum install -y "$apt_name" 2>/dev/null || true ;;
        pacman) sudo pacman -S --noconfirm "$apt_name" 2>/dev/null || true ;;
        *)      warn "Cannot auto-install ${pkg_name}. Please install manually." ;;
    esac
}

# ============================================================================
# Banner
# ============================================================================
echo -e "${CYAN}${BOLD}"
cat << 'BANNER'

   ██████╗ ██████╗  ██████╗ █████╗
  ██╔═══██╗██╔══██╗██╔════╝██╔══██╗
  ██║   ██║██████╔╝██║     ███████║
  ██║   ██║██╔══██╗██║     ██╔══██║
  ╚██████╔╝██║  ██║╚██████╗██║  ██║
   ╚═════╝ ╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝
  Open-source Rules Compliance Auditor
  C/C++ Compliance Analysis Pipeline

BANNER
echo -e "${NC}"

# ============================================================================
# Step 0: Detect OS & Package Manager
# ============================================================================
step "Detecting environment"

OS_TYPE="unknown"
PKG_MANAGER="unknown"
IS_WSL=false

case "$(uname -s)" in
    Darwin)
        OS_TYPE="macos"
        if ! has_cmd brew; then
            for _brew_candidate in /opt/homebrew/bin/brew /usr/local/bin/brew /home/linuxbrew/.linuxbrew/bin/brew; do
                if [[ -x "$_brew_candidate" ]]; then
                    eval "$("$_brew_candidate" shellenv)"
                    break
                fi
            done
        fi
        if has_cmd brew; then
            PKG_MANAGER="brew"
        else
            err "Homebrew is required on macOS but was not found."
            err 'Install it:  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
            exit 1
        fi
        ;;
    Linux)
        OS_TYPE="linux"
        if grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null; then
            IS_WSL=true
            info "Windows Subsystem for Linux (WSL) detected"
        fi
        if   has_cmd apt-get; then PKG_MANAGER="apt"
        elif has_cmd dnf;     then PKG_MANAGER="dnf"
        elif has_cmd yum;     then PKG_MANAGER="yum"
        elif has_cmd pacman;  then PKG_MANAGER="pacman"
        else
            warn "No supported package manager found. Some tools may need manual installation."
            PKG_MANAGER="none"
        fi
        ;;
    MINGW*|MSYS*|CYGWIN*)
        err "Native Windows detected. Please use WSL (Windows Subsystem for Linux)."
        err "Install WSL:  wsl --install"
        exit 1
        ;;
    *)
        warn "Unknown OS: $(uname -s). Proceeding with best effort..."
        OS_TYPE="linux"
        PKG_MANAGER="none"
        ;;
esac

info "OS: ${OS_TYPE}$(${IS_WSL} && echo ' (WSL)' || echo '')  |  Package manager: ${PKG_MANAGER}"

# ============================================================================
# Step 1: Python
# ============================================================================
step "Checking Python"

find_python() {
    if [[ -n "${ORCA_PYTHON:-}" ]] && has_cmd "$ORCA_PYTHON"; then
        echo "$ORCA_PYTHON"
        return
    fi
    for py in python3.12 python3.11 python3.10 python3.9 python3 python; do
        if has_cmd "$py"; then
            local ver
            ver="$($py -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")"
            local major="${ver%%.*}" minor="${ver#*.}"
            if [[ $(( major * 100 + minor )) -ge $(( MIN_PYTHON_MAJOR * 100 + MIN_PYTHON_MINOR )) ]]; then
                echo "$py"
                return
            fi
        fi
    done
    echo ""
}

PYTHON_BIN="$(find_python)"

if [[ -z "$PYTHON_BIN" ]]; then
    warn "Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ not found. Installing..."
    case "$PKG_MANAGER" in
        brew)   brew install python@3.11 2>/dev/null || true ;;
        apt)
            sudo apt-get update -qq
            if ! sudo apt-get install -y -qq python3.11 python3.11-venv python3-pip 2>/dev/null; then
                sudo apt-get install -y -qq python3 python3-venv python3-pip 2>/dev/null || true
            fi
            ;;
        dnf)    sudo dnf install -y python3.11 python3-pip 2>/dev/null || \
                sudo dnf install -y python3 python3-pip 2>/dev/null || true ;;
        yum)    sudo yum install -y python3 python3-pip 2>/dev/null || true ;;
        pacman) sudo pacman -S --noconfirm python python-pip 2>/dev/null || true ;;
        *)      err "Please install Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ manually."; exit 1 ;;
    esac
    PYTHON_BIN="$(find_python)"
fi

if [[ -z "$PYTHON_BIN" ]]; then
    err "Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ is required but could not be found or installed."
    exit 1
fi

PY_VERSION="$($PYTHON_BIN --version 2>&1)"
info "Using: ${PY_VERSION} ($(which $PYTHON_BIN))"

# ============================================================================
# Step 2: Virtual Environment
# ============================================================================
step "Setting up virtual environment"

if [[ -d "$VENV_DIR" ]]; then
    info "Virtual environment already exists at ${VENV_DIR}"
else
    substep "Creating virtual environment..."
    $PYTHON_BIN -m venv "$VENV_DIR"
    info "Created virtual environment at ${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"
info "Activated virtual environment"

substep "Upgrading pip..."
pip install --upgrade pip setuptools wheel --quiet 2>/dev/null

# ============================================================================
# Step 3: Python Dependencies
# ============================================================================
step "Installing Python dependencies"

if [[ -f "requirements.txt" ]]; then
    substep "Installing from requirements.txt..."
    pip install -r requirements.txt --quiet 2>&1 | tail -5 || {
        warn "Some packages failed. Trying individually..."
        while IFS= read -r line; do
            [[ "$line" =~ ^[[:space:]]*# ]] && continue
            [[ -z "${line// /}" ]] && continue
            pip install "$line" --quiet 2>/dev/null || warn "Failed to install: $line"
        done < requirements.txt
    }
    info "Python dependencies installed"
else
    err "requirements.txt not found!"
    exit 1
fi

# ============================================================================
# Step 4: System Tools
# ============================================================================
if [[ "${ORCA_SKIP_TOOLS:-0}" != "1" ]]; then
    step "Installing system tools"

    # ── git ─────────────────────────────────────────────────────────────────
    if has_cmd git; then
        info "git already installed"
    else
        pkg_install "git" "git" "git"
    fi

    # ── checkpatch.pl (optional) ────────────────────────────────────────────
    if has_cmd checkpatch.pl; then
        info "checkpatch.pl already installed"
    else
        warn "checkpatch.pl not found (optional — for Linux kernel style checking)"
        warn "Install manually from the Linux kernel source tree if needed."
    fi

    # Summary
    echo ""
    substep "Tool Summary:"
    for tool in git checkpatch.pl; do
        if has_cmd "$tool"; then
            echo -e "    ${GREEN}✓${NC} $tool"
        else
            echo -e "    ${YELLOW}○${NC} $tool (not found — optional)"
        fi
    done
else
    step "Skipping system tools (ORCA_SKIP_TOOLS=1)"
fi

# ============================================================================
# Step 5: Install ORCA CLI
# ============================================================================
step "Installing ORCA CLI tool"

if [[ -f "setup.py" ]]; then
    substep "Running pip install -e ..."
    pip install -e . --quiet 2>/dev/null
    info "ORCA CLI installed — use 'orca' instead of 'python main.py'"
else
    warn "setup.py not found — skipping CLI install"
fi

# ============================================================================
# Step 6: Environment Configuration
# ============================================================================
step "Setting up environment"

if [[ ! -f ".env" ]]; then
    if [[ -f "env.example" ]]; then
        cp env.example .env
        info "Created .env from env.example"
        warn "Edit .env to add your API keys (LLM_API_KEY, QGENIE_API_KEY)"
    else
        warn "No env.example found. Create a .env file with your API keys."
    fi
else
    info ".env file already exists"
fi

mkdir -p out out/reports
info "Output directories ready (./out, ./out/reports)"

# ============================================================================
# Step 7: PostgreSQL (optional)
# ============================================================================
if [[ "${ORCA_SKIP_DB:-0}" != "1" ]]; then
    step "Database setup"
    if [[ -f "db/bootstrap_db.py" ]]; then
        info "PostgreSQL bootstrap script found (db/bootstrap_db.py)"
        info "Run it separately when you're ready to set up the database:"
        echo -e "    ${CYAN}python db/bootstrap_db.py${NC}"
        echo ""
        info "DB credentials are configured in config.yaml (or via ORCA_PG_* env vars)"
        info "The database is optional — core static analysis works without it."
        info "It's needed for: HITL feedback persistence and RAG-powered audits."
    else
        warn "db/bootstrap_db.py not found. Database setup must be done manually."
    fi
else
    step "Skipping database setup (ORCA_SKIP_DB=1)"
fi

# ============================================================================
# Step 8: Validation
# ============================================================================
step "Validating installation"

ERRORS=0

# Python packages
substep "Checking Python packages..."
for pkg in yaml openpyxl streamlit psycopg2; do
    if python -c "import $pkg" 2>/dev/null; then
        echo -e "    ${GREEN}✓${NC} $pkg"
    else
        echo -e "    ${RED}✗${NC} $pkg"
        ERRORS=$((ERRORS + 1))
    fi
done

# Core files
substep "Checking project files..."
for f in main.py fixer_workflow.py ui/app.py config.yaml requirements.txt; do
    if [[ -f "$f" ]]; then
        echo -e "    ${GREEN}✓${NC} $f"
    else
        echo -e "    ${RED}✗${NC} $f (missing)"
        ERRORS=$((ERRORS + 1))
    fi
done

# Syntax validation
substep "Validating Python syntax..."
for f in main.py fixer_workflow.py ui/app.py; do
    if [[ -f "$f" ]]; then
        if python -c "import ast; ast.parse(open('$f').read())" 2>/dev/null; then
            echo -e "    ${GREEN}✓${NC} $f"
        else
            echo -e "    ${RED}✗${NC} $f (syntax error)"
            ERRORS=$((ERRORS + 1))
        fi
    fi
done

# ============================================================================
# Step 9: Summary & Launch Instructions
# ============================================================================
echo ""
echo -e "${CYAN}${BOLD}════════════════════════════════════════════════════════════${NC}"

if [[ "$ERRORS" -eq 0 ]]; then
    echo -e "${GREEN}${BOLD}  ✓ ORCA installation complete!${NC}"
else
    echo -e "${YELLOW}${BOLD}  ! ORCA installed with ${ERRORS} warning(s)${NC}"
fi

echo -e "${CYAN}${BOLD}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BOLD}Quick Start:${NC}"
echo ""
echo -e "    ${CYAN}# 1. Activate the environment${NC}"
echo -e "    source ${VENV_DIR}/bin/activate"
echo ""
echo -e "    ${CYAN}# 2. Add your API key${NC}"
echo -e "    export LLM_API_KEY=\"sk-...\""
echo -e "    ${CYAN}# (or edit .env)${NC}"
echo ""
echo -e "    ${CYAN}# 3. Launch the dashboard${NC}"
echo -e "    ./launch.sh"
echo ""
echo -e "    ${CYAN}# 4. Run CLI analysis${NC}"
echo -e "    orca audit --codebase-path ./src"
echo -e "    ${CYAN}# or: python main.py audit --codebase-path ./src${NC}"
echo ""
echo -e "  ${BOLD}Optional:${NC}"
echo -e "    python db/bootstrap_db.py           ${CYAN}# Set up PostgreSQL${NC}"
echo -e "    orca pipeline --codebase-path ./src  ${CYAN}# Full audit → fix → report${NC}"
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo ""
