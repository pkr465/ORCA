#!/usr/bin/env bash
# ============================================================================
# ORCA — Open-source Rules Compliance Auditor
# Launch script — opens the ORCA website (index.html) and starts the
# Streamlit dashboard in the background.
#
# Flow:
#   1. Activates virtual environment & loads .env
#   2. Starts Streamlit dashboard (headless) on the configured port
#   3. Opens index.html in the default browser
#   4. User clicks "Start Analysis" on the website → navigates to dashboard
#
# Usage:
#   ./launch.sh              # Launch website + dashboard
#   ./launch.sh --no-site    # Launch dashboard only (open Streamlit directly)
#   ./launch.sh --port 8502  # Custom port
#   ./launch.sh --help       # Show help
#
# Environment:
#   STREAMLIT_PORT=8501      Override default port
#   ORCA_NO_BROWSER=1        Don't auto-open any browser window
# ============================================================================

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────────────────────
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

# ── Project root ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Defaults ────────────────────────────────────────────────────────────────
PORT="${STREAMLIT_PORT:-8501}"
OPEN_SITE=true
VENV_DIR=".venv"

# ── Parse args ──────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-site|--dashboard-only)  OPEN_SITE=false; shift ;;
        --port|-p)                   PORT="$2"; shift 2 ;;
        --website)                   OPEN_SITE=true; shift ;;
        --help|-h)
            echo "ORCA Launch Script"
            echo ""
            echo "Usage: ./launch.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --no-site          Skip opening the website; open Streamlit directly"
            echo "  --port, -p PORT    Set Streamlit port (default: 8501)"
            echo "  --website          Also open index.html in the browser"
            echo "  --help, -h         Show this help"
            echo ""
            echo "Environment:"
            echo "  STREAMLIT_PORT     Override default port"
            echo "  ORCA_NO_BROWSER    Set to 1 to skip auto-opening any browser window"
            exit 0
            ;;
        *) echo "Unknown option: $1. Use --help for usage."; exit 1 ;;
    esac
done

# ── Banner ──────────────────────────────────────────────────────────────────
echo -e "${CYAN}${BOLD}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║  ORCA — Open-source Rules Compliance Auditor ║"
echo "  ║  C/C++ Compliance Analysis Dashboard         ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"

# ── Activate virtual environment ────────────────────────────────────────────
if [[ -f "${VENV_DIR}/bin/activate" ]]; then
    source "${VENV_DIR}/bin/activate"
    echo -e "${GREEN}[✓]${NC} Virtual environment activated"
else
    echo -e "${YELLOW}[!]${NC} No virtual environment found at ${VENV_DIR}. Using system Python."
    echo -e "    Run ${CYAN}./install.sh${NC} first for a clean setup."
fi

# ── Load .env file (if present) ─────────────────────────────────────────────
if [[ -f ".env" ]]; then
    set -a
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%$'\r'}"
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
        eval "export $line" 2>/dev/null || true
    done < .env
    set +a
    echo -e "${GREEN}[✓]${NC} Loaded environment from .env"
fi

# ── Check Streamlit ─────────────────────────────────────────────────────────
if ! python -c "import streamlit" 2>/dev/null; then
    echo -e "${RED}[✗]${NC} Streamlit is not installed."
    echo -e "    Run: ${CYAN}pip install -r requirements.txt${NC}"
    exit 1
fi

# ── Check app.py ────────────────────────────────────────────────────────────
APP_PATH="ui/app.py"
if [[ ! -f "$APP_PATH" ]]; then
    echo -e "${RED}[✗]${NC} Cannot find ${APP_PATH}. Run from the project root."
    exit 1
fi

# ── Get local IP for network access ─────────────────────────────────────────
LOCAL_IP="$(python -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(('10.255.255.255', 1))
    print(s.getsockname()[0])
except: print('localhost')
finally: s.close()
" 2>/dev/null || echo "localhost")"

# ── Print access info ──────────────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}URLs:${NC}"
if [[ "$OPEN_SITE" == "true" && -f "index.html" ]]; then
    echo -e "    Website:   ${CYAN}file://${SCRIPT_DIR}/index.html${NC}"
fi
echo -e "    Dashboard: ${CYAN}http://localhost:${PORT}${NC}"
echo -e "    Network:   ${CYAN}http://${LOCAL_IP}:${PORT}${NC}"
echo ""

# ── Open browser ───────────────────────────────────────────────────────────
if [[ "${ORCA_NO_BROWSER:-0}" != "1" ]]; then
    if [[ "$OPEN_SITE" == "true" && -f "index.html" ]]; then
        echo -e "${GREEN}[✓]${NC} Opening ORCA website in browser..."
        case "$(uname -s)" in
            Darwin)  open "index.html" 2>/dev/null || true ;;
            Linux)   xdg-open "index.html" 2>/dev/null || true ;;
        esac
    else
        echo -e "${GREEN}[✓]${NC} Opening dashboard in browser (after startup)..."
        (sleep 3 && case "$(uname -s)" in
            Darwin)  open "http://localhost:${PORT}" 2>/dev/null || true ;;
            Linux)   xdg-open "http://localhost:${PORT}" 2>/dev/null || true ;;
        esac) &
    fi
fi

# ── Launch Streamlit (headless — browser handled above) ────────────────────
echo -e "${GREEN}[✓]${NC} Starting Streamlit dashboard on port ${PORT}..."
echo -e "    Press ${BOLD}Ctrl+C${NC} to stop"
echo ""

export STREAMLIT_PORT="$PORT"

exec python -m streamlit run "$APP_PATH" \
    --server.port "$PORT" \
    --server.headless true \
    --browser.gatherUsageStats false
