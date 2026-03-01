#!/bin/bash
set -euo pipefail

# ORCA Launch Script
# Opens ORCA — Open-source Rules Compliance Auditor
# C/C++ Compliance Analysis Dashboard

# Color definitions
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default values
PORT=8501
OPEN_WEBSITE=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Functions
print_banner() {
    echo -e "${CYAN}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║                                                            ║"
    echo "║  ORCA — Open-source Rules Compliance Auditor               ║"
    echo "║  C/C++ Compliance Analysis Dashboard                       ║"
    echo "║                                                            ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_help() {
    cat << EOF
Usage: ./launch.sh [OPTIONS]

Options:
  --port PORT         Specify the port to run the dashboard on (default: 8501)
  --website           Also open index.html in the browser
  --help              Display this help message

Examples:
  ./launch.sh                    # Launch on default port 8501
  ./launch.sh --port 8502        # Launch on port 8502
  ./launch.sh --website          # Launch and open website in browser
  ./launch.sh --port 9000 --website

EOF
}

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --port)
                PORT="$2"
                shift 2
                ;;
            --website)
                OPEN_WEBSITE=true
                shift
                ;;
            --help)
                print_help
                exit 0
                ;;
            *)
                echo -e "${RED}Unknown option: $1${NC}"
                print_help
                exit 1
                ;;
        esac
    done
}

activate_venv() {
    echo -e "${CYAN}Step 1: Checking virtual environment...${NC}"

    if [[ -z "${VIRTUAL_ENV:-}" ]]; then
        if [[ -f "$SCRIPT_DIR/.venv/bin/activate" ]]; then
            echo -e "${GREEN}✓ Found .venv${NC}"
            source "$SCRIPT_DIR/.venv/bin/activate"
            echo -e "${GREEN}✓ Virtual environment activated${NC}"
        else
            echo -e "${RED}✗ Virtual environment not found at $SCRIPT_DIR/.venv${NC}"
            echo "Please run: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
            exit 1
        fi
    else
        echo -e "${GREEN}✓ Virtual environment already active: ${VIRTUAL_ENV}${NC}"
    fi
}

check_dependencies() {
    echo -e "${CYAN}Step 2: Checking dependencies...${NC}"

    local missing_deps=()

    # Check streamlit
    if ! python -c "import streamlit" 2>/dev/null; then
        missing_deps+=("streamlit")
    else
        echo -e "${GREEN}✓ streamlit${NC}"
    fi

    # Check pyyaml
    if ! python -c "import yaml" 2>/dev/null; then
        missing_deps+=("pyyaml")
    else
        echo -e "${GREEN}✓ pyyaml${NC}"
    fi

    # Check openpyxl
    if ! python -c "import openpyxl" 2>/dev/null; then
        missing_deps+=("openpyxl")
    else
        echo -e "${GREEN}✓ openpyxl${NC}"
    fi

    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        echo -e "${RED}✗ Missing dependencies: ${missing_deps[*]}${NC}"
        echo "Install them with: pip install ${missing_deps[*]}"
        exit 1
    fi

    echo -e "${GREEN}✓ All dependencies satisfied${NC}"
}

resolve_urls() {
    echo -e "${CYAN}Step 3: Resolving URLs...${NC}"

    # Get local IP
    if [[ "$OSTYPE" == "darwin"* ]]; then
        LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "localhost")
    else
        LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
    fi

    LOCAL_URL="http://localhost:${PORT}"
    NETWORK_URL="http://${LOCAL_IP}:${PORT}"

    echo -e "${GREEN}✓ Local URL:   $LOCAL_URL${NC}"
    echo -e "${GREEN}✓ Network URL: $NETWORK_URL${NC}"
}

open_browser() {
    local url=$1

    if [[ "$OSTYPE" == "darwin"* ]]; then
        open "$url"
    elif command -v wslview &> /dev/null; then
        wslview "$url"
    elif command -v xdg-open &> /dev/null; then
        xdg-open "$url"
    else
        echo -e "${YELLOW}⚠ Could not detect browser. Please open manually: $url${NC}"
    fi
}

launch_streamlit() {
    echo -e "${CYAN}Step 4: Launching Streamlit dashboard...${NC}"
    echo -e "${GREEN}Starting on port $PORT${NC}"
    echo ""
    echo -e "${YELLOW}Dashboard will be available at:${NC}"
    echo -e "  ${GREEN}$LOCAL_URL${NC}"
    echo ""

    if [[ $OPEN_WEBSITE == true ]]; then
        echo -e "${YELLOW}Opening website in browser...${NC}"
        sleep 1
        if [[ -f "$SCRIPT_DIR/index.html" ]]; then
            open_browser "file://$SCRIPT_DIR/index.html"
        else
            echo -e "${YELLOW}⚠ index.html not found at $SCRIPT_DIR/index.html${NC}"
        fi
        sleep 1
        open_browser "$LOCAL_URL"
    else
        echo -e "${YELLOW}To open in your browser, visit the URL above.${NC}"
    fi

    echo ""
    echo -e "${CYAN}Press Ctrl+C to stop the server${NC}"
    echo ""

    cd "$SCRIPT_DIR"
    streamlit run ui/app.py \
        --logger.level=info \
        --server.port="$PORT" \
        --server.headless=true \
        --browser.gatherUsageStats=false
}

# Main execution
main() {
    print_banner
    parse_arguments "$@"
    activate_venv
    check_dependencies
    resolve_urls
    launch_streamlit
}

main "$@"
