#!/bin/bash

################################################################################
# ORCA Installer Script
# Open-source Rules Compliance Auditor
# C/C++ Compliance Analysis Pipeline
################################################################################

set -euo pipefail

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
VENV_DIR="${PROJECT_ROOT}/.venv"
REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements.txt"
ENV_EXAMPLE_FILE="${PROJECT_ROOT}/env.example"
ENV_FILE="${PROJECT_ROOT}/.env"
CONFIG_FILE="${PROJECT_ROOT}/config.yaml"

################################################################################
# Helper Functions
################################################################################

print_banner() {
    echo -e "${CYAN}${BOLD}"
    cat << "EOF"
╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║                          ORCA Installer v1.0                              ║
║        Open-source Rules Compliance Auditor                               ║
║        C/C++ Compliance Analysis Pipeline                                 ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
}

log_step() {
    echo -e "${CYAN}[STEP $1]${NC} ${BOLD}$2${NC}"
}

log_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

log_error() {
    echo -e "${RED}✗ $1${NC}"
}

exit_error() {
    log_error "$1"
    exit 1
}

################################################################################
# Step 1: Detect OS and Package Manager
################################################################################

detect_os_and_pm() {
    log_step "1" "Detecting OS and package manager..."

    OS_TYPE=""
    PACKAGE_MANAGER=""
    INSTALL_CMD=""

    # Detect WSL
    if grep -qi microsoft /proc/version 2>/dev/null || grep -qi wsl /proc/version 2>/dev/null; then
        log_warning "Windows Subsystem for Linux detected"
        IS_WSL=true
    else
        IS_WSL=false
    fi

    # Detect OS and package manager
    if [[ "$OSTYPE" == "darwin"* ]]; then
        OS_TYPE="macOS"
        PACKAGE_MANAGER="brew"
        INSTALL_CMD="brew install"
        log_success "Detected macOS with Homebrew"
    elif command -v apt-get &> /dev/null; then
        OS_TYPE="Debian/Ubuntu"
        PACKAGE_MANAGER="apt"
        INSTALL_CMD="sudo apt-get install -y"
        log_success "Detected Debian/Ubuntu with apt"
    elif command -v dnf &> /dev/null; then
        OS_TYPE="RHEL/Fedora"
        PACKAGE_MANAGER="dnf"
        INSTALL_CMD="sudo dnf install -y"
        log_success "Detected RHEL/Fedora with dnf"
    elif command -v yum &> /dev/null; then
        OS_TYPE="RHEL/CentOS"
        PACKAGE_MANAGER="yum"
        INSTALL_CMD="sudo yum install -y"
        log_success "Detected RHEL/CentOS with yum"
    elif command -v pacman &> /dev/null; then
        OS_TYPE="Arch Linux"
        PACKAGE_MANAGER="pacman"
        INSTALL_CMD="sudo pacman -S --noconfirm"
        log_success "Detected Arch Linux with pacman"
    else
        exit_error "Unable to detect OS or package manager. Supported: macOS, Debian, RHEL, Arch, WSL"
    fi

    if [[ "$IS_WSL" == true ]]; then
        log_warning "Running on WSL - ensure Windows integration is configured"
    fi
}

################################################################################
# Step 2: Install Python 3.9+ if Missing
################################################################################

install_python() {
    log_step "2" "Checking Python 3.9+ installation..."

    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
        log_success "Python $PYTHON_VERSION found"

        # Check if version is 3.9 or higher
        MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
        MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

        if [[ $MAJOR -lt 3 ]] || [[ $MAJOR -eq 3 && $MINOR -lt 9 ]]; then
            log_warning "Python version is $PYTHON_VERSION, but 3.9+ is required"
            install_python_version
        fi
    else
        log_warning "Python not found, installing..."
        install_python_version
    fi
}

install_python_version() {
    case "$PACKAGE_MANAGER" in
        brew)
            $INSTALL_CMD python@3.11
            ;;
        apt)
            sudo apt-get update
            $INSTALL_CMD python3.11 python3.11-venv python3.11-dev
            ;;
        dnf)
            $INSTALL_CMD python3.11 python3.11-devel
            ;;
        yum)
            $INSTALL_CMD python3.11 python3.11-devel
            ;;
        pacman)
            $INSTALL_CMD python
            ;;
        *)
            exit_error "Unable to install Python with package manager: $PACKAGE_MANAGER"
            ;;
    esac
    log_success "Python 3.11 installed"
}

################################################################################
# Step 3: Create Virtual Environment
################################################################################

create_venv() {
    log_step "3" "Creating Python virtual environment..."

    if [[ -d "$VENV_DIR" ]]; then
        log_warning "Virtual environment already exists at $VENV_DIR"
        read -p "Remove and recreate? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$VENV_DIR"
            python3 -m venv "$VENV_DIR"
            log_success "Virtual environment created at $VENV_DIR"
        fi
    else
        python3 -m venv "$VENV_DIR"
        log_success "Virtual environment created at $VENV_DIR"
    fi

    # Source the virtual environment
    source "${VENV_DIR}/bin/activate"
    log_success "Virtual environment activated"
}

################################################################################
# Step 4: Install pip Dependencies
################################################################################

install_dependencies() {
    log_step "4" "Installing pip dependencies from requirements.txt..."

    if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
        log_warning "requirements.txt not found at $REQUIREMENTS_FILE"
        log_warning "Skipping pip dependency installation"
        return
    fi

    # Upgrade pip, setuptools, and wheel
    pip install --upgrade pip setuptools wheel

    # Install requirements
    pip install -r "$REQUIREMENTS_FILE"
    log_success "Dependencies installed successfully"
}

################################################################################
# Step 5: Install System Tools
################################################################################

install_system_tools() {
    log_step "5" "Installing system tools for ORCA..."

    # Always install git
    if ! command -v git &> /dev/null; then
        log_warning "git not found, installing..."
        case "$PACKAGE_MANAGER" in
            brew)
                $INSTALL_CMD git
                ;;
            apt)
                sudo apt-get update
                $INSTALL_CMD git
                ;;
            dnf)
                $INSTALL_CMD git
                ;;
            yum)
                $INSTALL_CMD git
                ;;
            pacman)
                $INSTALL_CMD git
                ;;
        esac
        log_success "git installed"
    else
        log_success "git already installed"
    fi

    # Install checkpatch.pl (optional)
    log_warning "checkpatch.pl is optional for C/C++ style checking"

    if ! command -v checkpatch.pl &> /dev/null; then
        read -p "Install checkpatch.pl for code style analysis? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            case "$PACKAGE_MANAGER" in
                brew)
                    log_warning "checkpatch.pl not available in Homebrew - manual installation recommended"
                    ;;
                apt)
                    sudo apt-get update
                    $INSTALL_CMD linux-source-*
                    log_success "checkpatch.pl installation initiated"
                    ;;
                dnf)
                    $INSTALL_CMD kernel-devel
                    log_success "checkpatch.pl installation initiated"
                    ;;
                yum)
                    $INSTALL_CMD kernel-devel
                    log_success "checkpatch.pl installation initiated"
                    ;;
                pacman)
                    log_warning "checkpatch.pl not available in Arch repos - manual installation recommended"
                    ;;
            esac
        else
            log_warning "Skipping checkpatch.pl installation (optional)"
        fi
    else
        log_success "checkpatch.pl already installed"
    fi
}

################################################################################
# Step 6: Set Up .env Configuration
################################################################################

setup_env() {
    log_step "6" "Setting up environment configuration..."

    if [[ -f "$ENV_FILE" ]]; then
        log_success "Environment file already exists at $ENV_FILE"
    elif [[ -f "$ENV_EXAMPLE_FILE" ]]; then
        cp "$ENV_EXAMPLE_FILE" "$ENV_FILE"
        log_success "Created .env from env.example"
    else
        log_warning "env.example not found, creating minimal .env"
        cat > "$ENV_FILE" << 'EOF'
# ORCA Environment — API Keys Only
# All other configuration lives in global_config.yaml

# Generic LLM API Key (for anthropic / openai providers)
LLM_API_KEY=""

# QGenie API Key (only when llm.provider is "qgenie")
QGENIE_API_KEY=""
EOF
        log_success "Created minimal .env file"
    fi

    # Warn about API keys
    echo
    log_warning "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_warning "IMPORTANT: API Key Configuration Required"
    log_warning "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${YELLOW}Please configure your API keys in ${ENV_FILE}:${NC}"
    echo -e "  ${BOLD}LLM_API_KEY${NC}    - For Anthropic/OpenAI API access"
    echo -e "  ${BOLD}QGENIE_API_KEY${NC} - For QGenie API access (if applicable)"
    echo
    echo -e "${YELLOW}Get your API keys from:${NC}"
    echo -e "  Anthropic: https://console.anthropic.com/account/keys"
    echo -e "  OpenAI:    https://platform.openai.com/account/api-keys"
    echo -e "  QGenie:    Contact your QGenie administrator"
    echo
    log_warning "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo
}

################################################################################
# Step 7: Create Output Directories
################################################################################

create_output_dirs() {
    log_step "7" "Creating output directories..."

    mkdir -p "${PROJECT_ROOT}/out"
    mkdir -p "${PROJECT_ROOT}/out/reports"

    log_success "Output directories created:"
    echo -e "  ${CYAN}${PROJECT_ROOT}/out${NC}"
    echo -e "  ${CYAN}${PROJECT_ROOT}/out/reports${NC}"
}

################################################################################
# Step 8: Validate Installation
################################################################################

validate_installation() {
    log_step "8" "Validating installation..."

    VALIDATION_PASSED=true

    # Check Python modules
    REQUIRED_MODULES=("yaml" "openpyxl" "streamlit" "psycopg2")

    for module in "${REQUIRED_MODULES[@]}"; do
        if python3 -c "import ${module}" 2>/dev/null; then
            log_success "Module ${module} is available"
        else
            log_warning "Module ${module} not found - some features may not work"
            VALIDATION_PASSED=false
        fi
    done

    # Validate main.py
    if [[ -f "${PROJECT_ROOT}/main.py" ]]; then
        if python3 -m py_compile "${PROJECT_ROOT}/main.py" 2>/dev/null; then
            log_success "main.py syntax validation passed"
        else
            log_warning "main.py has syntax errors"
            VALIDATION_PASSED=false
        fi
    else
        log_warning "main.py not found"
    fi

    # Validate ui/app.py
    if [[ -f "${PROJECT_ROOT}/ui/app.py" ]]; then
        if python3 -m py_compile "${PROJECT_ROOT}/ui/app.py" 2>/dev/null; then
            log_success "ui/app.py syntax validation passed"
        else
            log_warning "ui/app.py has syntax errors"
            VALIDATION_PASSED=false
        fi
    else
        log_warning "ui/app.py not found"
    fi

    # Check for config.yaml
    if [[ -f "$CONFIG_FILE" ]]; then
        log_success "Configuration file found: $CONFIG_FILE"
    else
        log_warning "Configuration file not found: $CONFIG_FILE"
        log_warning "Default configuration will be used"
    fi

    echo
    if [[ "$VALIDATION_PASSED" == true ]]; then
        log_success "All validations passed!"
    else
        log_warning "Some validations had warnings - see above"
    fi
}

################################################################################
# Step 9: Print Launch Instructions
################################################################################

print_launch_instructions() {
    log_step "9" "Installation complete!"

    echo
    log_success "ORCA has been successfully installed!"
    echo

    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}${BOLD}Getting Started with ORCA${NC}"
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo

    # Activate venv instruction
    echo -e "${BOLD}1. Activate the Virtual Environment${NC}"
    echo -e "   ${CYAN}source ${VENV_DIR}/bin/activate${NC}"
    echo

    # Launch dashboard
    echo -e "${BOLD}2. Launch the Web Dashboard${NC}"
    if [[ -f "${PROJECT_ROOT}/launch.sh" ]]; then
        echo -e "   ${CYAN}./launch.sh${NC}"
    else
        echo -e "   ${CYAN}streamlit run ui/app.py${NC}"
    fi
    echo

    # CLI usage
    echo -e "${BOLD}3. Run ORCA from Command Line${NC}"
    echo -e "   ${CYAN}python main.py --codebase-path /path/to/your/code${NC}"
    echo

    # Configuration
    echo -e "${BOLD}4. Configure ORCA${NC}"
    echo -e "   Edit your configuration in: ${CYAN}${CONFIG_FILE}${NC}"
    echo -e "   Or environment variables in: ${CYAN}${ENV_FILE}${NC}"
    echo

    # Documentation
    echo -e "${BOLD}5. View Output and Reports${NC}"
    echo -e "   Analysis results: ${CYAN}${PROJECT_ROOT}/out/reports${NC}"
    echo

    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo

    echo -e "${GREEN}${BOLD}✓ ORCA is ready to use!${NC}"
    echo
}

################################################################################
# Main Installation Flow
################################################################################

main() {
    print_banner

    # Run installation steps
    detect_os_and_pm
    echo

    install_python
    echo

    create_venv
    echo

    install_dependencies
    echo

    install_system_tools
    echo

    setup_env
    echo

    create_output_dirs
    echo

    validate_installation
    echo

    print_launch_instructions
}

# Run main function
main
