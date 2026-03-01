"""Configuration parser for ORCA with YAML support and environment variable interpolation."""

import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import yaml


class DictMixin:
    """Mixin to provide dict-like access on dataclasses."""
    def get(self, key, default=None):
        return getattr(self, key, default)
    def __getitem__(self, key):
        return getattr(self, key)
    def __contains__(self, key):
        return hasattr(self, key)


@dataclass
class PathsConfig(DictMixin):
    """Configuration for file and directory paths."""
    codebase: str = "."
    output: str = "./out"
    rules: str = "./rules/linux_kernel.yaml"
    exclude_patterns: List[str] = field(default_factory=lambda: [
        "build/",
        ".git/",
        "third_party/",
        "vendor/",
        "*.generated.*"
    ])


@dataclass
class LLMConfig(DictMixin):
    """Configuration for LLM provider and model settings."""
    provider: str = "mock"
    model: str = "anthropic::claude-sonnet-4-20250514"
    api_key: str = ""
    qgenie_api_key: str = ""
    qgenie_base_url: str = "https://api.qgenie.io/v1"
    timeout: int = 60
    max_retries: int = 3
    max_tokens: int = 8192
    temperature: float = 0.1
    mock_mode: bool = True


@dataclass
class ComplianceConfig(DictMixin):
    """Configuration for compliance checking domains and thresholds."""
    enabled_domains: List[str] = field(default_factory=lambda: [
        "style",
        "license",
        "structure",
        "patch"
    ])
    severity_threshold: str = "low"
    auto_fix_threshold: str = "high"
    max_files: int = 10000
    batch_size: int = 50


@dataclass
class AdaptersConfig(DictMixin):
    """Configuration for external tool adapters."""
    checkpatch_path: str = ""
    scancode_path: str = ""
    gitlint_config: str = ".gitlint"


@dataclass
class HITLConfig(DictMixin):
    """Configuration for Human-in-the-Loop system."""
    enabled: bool = False
    db_url: str = ""
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "orca_feedback"
    db_user: str = "orca"
    db_password: str = ""
    db_schema: str = "orca"
    feedback_excel: str = "./out/compliance_review.xlsx"
    constraints_dir: str = "./constraints/"
    rag_top_k: int = 5
    similarity_threshold: float = 0.3


@dataclass
class ExcelConfig(DictMixin):
    """Configuration for Excel output formatting."""
    header_fill: str = "1B3A5C"
    header_font_color: str = "FFFFFF"
    alternating_fill: str = "EBF2FA"
    accent_color: str = "2E75B6"


@dataclass
class ReportingConfig(DictMixin):
    """Configuration for reporting output."""
    formats: List[str] = field(default_factory=lambda: ["excel", "json"])
    html_template: str = "default"
    include_code_snippets: bool = True
    max_snippet_lines: int = 10
    verbose: bool = False


@dataclass
class GlobalConfig:
    """Root configuration container."""
    paths: PathsConfig = field(default_factory=PathsConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    compliance: ComplianceConfig = field(default_factory=ComplianceConfig)
    adapters: AdaptersConfig = field(default_factory=AdaptersConfig)
    hitl: HITLConfig = field(default_factory=HITLConfig)
    excel: ExcelConfig = field(default_factory=ExcelConfig)
    reporting: ReportingConfig = field(default_factory=ReportingConfig)

    def get(self, key, default=None):
        """Dict-like get for backward compatibility with code expecting dicts."""
        return getattr(self, key, default)

    def to_dict(self):
        """Convert to plain dict recursively."""
        return asdict(self)


def interpolate_env_vars(value: Any) -> Any:
    """
    Interpolate environment variables in configuration values.
    
    Supports pattern: ${VAR:-default}
    
    Args:
        value: Configuration value that may contain env var references
        
    Returns:
        Interpolated value with env vars replaced
    """
    if isinstance(value, str):
        # Pattern: ${VAR:-default} or ${VAR}
        def replace_env_var(match):
            var_name = match.group(1)
            default_value = match.group(2) if match.group(2) is not None else ""
            return os.environ.get(var_name, default_value)
        
        return re.sub(r'\$\{([^:}]+)(?::-([^}]*))?\}', replace_env_var, value)
    
    elif isinstance(value, dict):
        return {k: interpolate_env_vars(v) for k, v in value.items()}
    
    elif isinstance(value, list):
        return [interpolate_env_vars(item) for item in value]
    
    return value


def _dict_to_dataclass(data: Dict[str, Any], dataclass_type) -> Any:
    """
    Convert a dictionary to a dataclass instance.
    
    Args:
        data: Dictionary of values
        dataclass_type: The dataclass type to convert to
        
    Returns:
        Instance of the dataclass
    """
    if data is None:
        return dataclass_type()
    
    # Get the fields from the dataclass
    field_names = {f.name for f in dataclass_type.__dataclass_fields__.values()}
    
    # Filter data to only include known fields
    filtered_data = {k: v for k, v in data.items() if k in field_names}
    
    return dataclass_type(**filtered_data)


def load_config(path: str) -> GlobalConfig:
    """
    Load configuration from YAML file with environment variable interpolation.
    
    Args:
        path: Path to YAML configuration file
        
    Returns:
        GlobalConfig instance with loaded and interpolated values
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If YAML is invalid
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Configuration file not found: {path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        raw_config = yaml.safe_load(f) or {}
    
    # Interpolate environment variables
    config_dict = interpolate_env_vars(raw_config)
    
    # Build nested dataclasses
    config = GlobalConfig(
        paths=_dict_to_dataclass(config_dict.get('paths', {}), PathsConfig),
        llm=_dict_to_dataclass(config_dict.get('llm', {}), LLMConfig),
        compliance=_dict_to_dataclass(config_dict.get('compliance', {}), ComplianceConfig),
        adapters=_dict_to_dataclass(config_dict.get('adapters', {}), AdaptersConfig),
        hitl=_dict_to_dataclass(config_dict.get('hitl', {}), HITLConfig),
        excel=_dict_to_dataclass(config_dict.get('excel', {}), ExcelConfig),
        reporting=_dict_to_dataclass(config_dict.get('reporting', {}), ReportingConfig),
    )
    
    return config


def merge_cli_overrides(config: GlobalConfig, cli_args: Optional[Dict[str, Any]]) -> GlobalConfig:
    """
    Merge CLI argument overrides into loaded configuration.
    
    Args:
        config: Loaded GlobalConfig instance
        cli_args: Dictionary of CLI arguments to override config
        
    Returns:
        Updated GlobalConfig with CLI overrides applied
    """
    if not cli_args:
        return config
    
    # Convert config to dict
    config_dict = asdict(config)
    
    # Handle dotted keys like "paths.codebase" -> config.paths.codebase
    for key, value in cli_args.items():
        if value is None:
            continue
        
        if '.' in key:
            # Nested key like "paths.codebase"
            parts = key.split('.')
            current = config_dict
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        else:
            # Top-level key
            config_dict[key] = value
    
    # Rebuild GlobalConfig from updated dict
    config = GlobalConfig(
        paths=_dict_to_dataclass(config_dict.get('paths', {}), PathsConfig),
        llm=_dict_to_dataclass(config_dict.get('llm', {}), LLMConfig),
        compliance=_dict_to_dataclass(config_dict.get('compliance', {}), ComplianceConfig),
        adapters=_dict_to_dataclass(config_dict.get('adapters', {}), AdaptersConfig),
        hitl=_dict_to_dataclass(config_dict.get('hitl', {}), HITLConfig),
        excel=_dict_to_dataclass(config_dict.get('excel', {}), ExcelConfig),
        reporting=_dict_to_dataclass(config_dict.get('reporting', {}), ReportingConfig),
    )
    
    return config
