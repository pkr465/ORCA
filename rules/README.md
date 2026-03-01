# ORCA Project Rules

This directory contains comprehensive YAML rule definitions for various embedded systems and Linux projects. Each file defines coding standards, licensing requirements, patch submission formats, and project-specific constraints.

## Files Overview

### 1. linux_kernel.yaml (187 lines)
**Linux Kernel Coding Style Rules**

Comprehensive rules for Linux kernel contribution compliance based on the official kernel documentation.

Key sections:
- **Style**: Tabs (8 spaces), 80-char line limit, K&R braces, snake_case naming
- **License**: GPL-2.0 primary, SPDX required, copyright enforcement
- **Structure**: Include guards, include ordering, no extern in .c files
- **Patch**: Signed-off-by required, imperative mood, DCO requirement
- **Severity Overrides**: Customized severity levels for different violation types

Reference: https://kernel.org/doc/html/latest/process/coding-style.html

### 2. uboot.yaml (217 lines)
**Das U-Boot Bootloader Rules**

Rules for U-Boot bootloader contributions with architecture-specific requirements.

Key features:
- **Inherits kernel style** with relaxations for bootloader needs
- **Typedefs**: Allowed for opaque pointers
- **Line Length**: 80 char hard limit, 120 warning
- **Architecture-Specific Rules**: ARM, ARM64, x86, PowerPC support
- **Board Configuration**: Required macro enforcement, no magic numbers
- **Assembly Support**: .S files allowed in source extensions

Reference: https://source.denx.de/u-boot/u-boot

### 3. yocto.yaml (246 lines)
**Yocto Project / OpenEmbedded Rules**

Comprehensive rules for Yocto and OpenEmbedded project contributions.

Key features:
- **Style**: Spaces (4-width), 200-char limit, both C and C++ comments allowed
- **Typedefs**: Fully allowed (more permissive than kernel)
- **Recipe-Specific Rules**: BitBake variable conventions, required variables
- **Variable Ordering**: SUMMARY, DESCRIPTION, LICENSE, LIC_FILES_CHKSUM, etc.
- **Layer Structure**: Layer naming, required files, compatibility tracking
- **BitBake Syntax**: Shell safety, variable expansion safeguards

Reference: https://wiki.yoctoproject.org/wiki/Contribution_Guidelines

### 4. custom.yaml (309 lines)
**Fully Documented Template for User Customization**

A comprehensive template file that documents all possible ORCA rule configurations with detailed comments and examples.

Key sections:
- **Project Metadata**: Basic project information
- **Coding Style**: 14 customizable style parameters with explanations
- **License Compliance**: SPDX, copyright, and header format rules
- **Code Structure**: Include guards, naming, extensions
- **Patch Format**: Subject, body, trailers, and DCO rules
- **Custom Rules**: Project-specific rule definitions
- **Severity Overrides**: Customizable violation severity levels
- **Development Tools**: Pre-commit, formatter, linter configuration
- **Documentation**: Function docs, parameter docs requirements
- **Testing Requirements**: Unit tests, coverage, test naming
- **Performance Rules**: Complexity limits, memory leak detection
- **Security Rules**: Unsafe function lists, secret detection
- **File Templates**: C source and header templates
- **Integration Settings**: GitHub Actions, GitLab CI, pre-commit framework

## Usage

### Using Predefined Rules
To use predefined rules, reference them in your ORCA configuration:

```yaml
rules_profile: "linux_kernel"
rules_file: "rules/linux_kernel.yaml"
```

### Creating Custom Rules
1. Copy `custom.yaml` to a new file
2. Modify project metadata and rule sections
3. Reference in your ORCA configuration

## Severity Levels

- **critical**: Blocks code review/merge
- **high**: Must be fixed before merge
- **medium**: Should be fixed
- **low**: Informational, not blocking
- **ignored**: Rule violation suppressed

## References

- Linux Kernel: https://kernel.org/doc/html/latest/process/coding-style.html
- U-Boot: https://source.denx.de/u-boot/u-boot
- Yocto: https://wiki.yoctoproject.org/wiki/Contribution_Guidelines
- SPDX: https://spdx.org/
- DCO: https://developercertificate.org/
