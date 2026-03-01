"""
ORCA — LLM Tools Router

Thin wrapper that reads ``llm.provider`` from the ORCA config files and
re-exports the matching provider module.  All existing imports like::

    from utils.llm_tools import LLMTools, LLMClient, LLMResponse

continue to work unchanged — they simply resolve to the provider chosen
in config.yaml / global_config.yaml.

Supported providers:
    "anthropic" → utils.llm_tools_anthropic  (Anthropic Claude SDK)
    "openai"    → utils.llm_tools_anthropic  (shares Anthropic module w/ key swap)
    "qgenie"    → utils.llm_tools_qgenie     (QGenie SDK / HTTP)
    "mock"      → utils.llm_tools_mock        (offline mock, default)

API keys are resolved from the environment (.env):
    LLM_API_KEY      — generic key for anthropic / openai
    QGENIE_API_KEY   — key for QGenie provider
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("orca.llm")

# ── Determine the active provider ────────────────────────────────────────

_PROVIDER = "mock"  # safe default

try:
    from utils.config_parser import load_config as _load_config

    def _find_cfg() -> str | None:
        root = Path(__file__).resolve().parent.parent
        for name in ("config.yaml", "global_config.yaml"):
            p = root / name
            if p.is_file():
                return str(p)
        return None

    _cfg_path = _find_cfg()
    if _cfg_path:
        _gc = _load_config(_cfg_path)
        _PROVIDER = (_gc.llm.provider or "mock").strip().lower()
except Exception:
    _PROVIDER = os.environ.get("ORCA_LLM_PROVIDER", "mock").strip().lower()

logger.info("llm_tools router: active provider = %s", _PROVIDER)

# ── Import everything from the chosen backend ────────────────────────────
#
# We re-export every public name so callers can do:
#   from utils.llm_tools import LLMTools, LLMClient, LLMConfig, LLMResponse, ...

if _PROVIDER == "anthropic" or _PROVIDER == "openai":
    from utils.llm_tools_anthropic import (       # noqa: F401
        LLMConfig,
        LLMTools,
        LLMClient,
        LLMResponse,
        BaseLLMProvider,
        AnthropicProvider,
        create_provider,
        LLMError,
        LLMProviderError,
        LLMResponseError,
        IntentExtractionError,
        ProviderNotAvailableError,
    )
    # Alias so code referencing QGenieProvider / MockProvider doesn't break
    QGenieProvider = None   # type: ignore[assignment]
    MockProvider = None     # type: ignore[assignment]

elif _PROVIDER == "qgenie":
    from utils.llm_tools_qgenie import (          # noqa: F401
        LLMConfig,
        LLMTools,
        LLMClient,
        LLMResponse,
        BaseLLMProvider,
        QGenieProvider,
        create_provider,
        LLMError,
        LLMProviderError,
        LLMResponseError,
        IntentExtractionError,
        ProviderNotAvailableError,
    )
    AnthropicProvider = None  # type: ignore[assignment]
    MockProvider = None       # type: ignore[assignment]

else:
    # Default: mock
    from utils.llm_tools_mock import (             # noqa: F401
        LLMConfig,
        LLMTools,
        LLMClient,
        LLMResponse,
        BaseLLMProvider,
        MockProvider,
        create_provider,
        LLMError,
        LLMProviderError,
        LLMResponseError,
        IntentExtractionError,
        ProviderNotAvailableError,
    )
    AnthropicProvider = None  # type: ignore[assignment]
    QGenieProvider = None     # type: ignore[assignment]


def get_active_provider() -> str:
    """Return the name of the currently active LLM provider."""
    return _PROVIDER


__all__ = [
    # Core classes (always available regardless of provider)
    "LLMTools",
    "LLMClient",
    "LLMConfig",
    "LLMResponse",
    "BaseLLMProvider",
    "create_provider",
    # Provider-specific (one will be the real class, others None)
    "AnthropicProvider",
    "QGenieProvider",
    "MockProvider",
    # Exceptions
    "LLMError",
    "LLMProviderError",
    "LLMResponseError",
    "IntentExtractionError",
    "ProviderNotAvailableError",
    # Helper
    "get_active_provider",
]
