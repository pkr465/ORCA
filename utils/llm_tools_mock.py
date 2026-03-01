"""
ORCA — Mock LLM backend.

Offline-only provider for testing and development.  No API calls are made.
Generates plausible compliance-analysis responses based on prompt keywords.

Usage (via router — preferred):
    # Set llm.provider = "mock" in config.yaml
    from utils.llm_tools import LLMTools

Usage (direct):
    from utils.llm_tools_mock import LLMTools
    tools = LLMTools()
    print(tools.llm_call("Analyze style violations..."))
"""

from __future__ import annotations

import abc
import json
import logging
import re
import time
import random
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("orca.llm.mock")


# ═══════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class LLMConfig:
    """Configuration for mock LLM provider."""

    raw_model: str = "mock::orca-test"
    coding_model: str = "mock::orca-test"
    api_key: str = ""
    qgenie_api_key: str = ""
    max_tokens: int = 8192
    temperature: float = 0.1
    timeout: int = 10
    max_retries: int = 0
    intent_max_tokens: int = 4096
    intent_temperature: float = 0.0
    max_prompt_tokens: int = 100_000
    mock_mode: bool = True

    @property
    def provider(self) -> str:
        return "mock"

    @property
    def model(self) -> str:
        if "::" in self.raw_model:
            return self.raw_model.split("::", 1)[1].strip()
        return self.raw_model

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls()


# ═══════════════════════════════════════════════════════════════════════════
# Exceptions  (identical signatures for import compat)
# ═══════════════════════════════════════════════════════════════════════════

class LLMError(Exception):
    """Base error for LLM operations."""

class LLMProviderError(LLMError):
    """Error communicating with the LLM provider."""

class LLMResponseError(LLMError):
    """Error parsing or validating an LLM response."""

class IntentExtractionError(LLMError):
    """Failed to extract structured intent from a prompt."""

class ProviderNotAvailableError(LLMError):
    """Required provider SDK is not installed or configured."""


# ═══════════════════════════════════════════════════════════════════════════
# Provider Abstraction
# ═══════════════════════════════════════════════════════════════════════════

class BaseLLMProvider(abc.ABC):
    def __init__(self, config: LLMConfig):
        self.config = config

    @abc.abstractmethod
    def complete(self, messages, system=None, max_tokens=None, temperature=None) -> str:
        ...

    def complete_with_tools(self, messages, tools, system=None, tool_choice=None, max_tokens=None):
        text = self.complete(messages=messages, system=system, max_tokens=max_tokens)
        return {"text": text, "tool_calls": [], "stop_reason": "end_turn"}


# ---------------------------------------------------------------------------
# Mock Provider
# ---------------------------------------------------------------------------

# Domain-keyed mock response templates
_MOCK_RESPONSES: Dict[str, Dict] = {
    "style": {
        "violations": [
            {"line": 42, "rule": "line_length", "message": "Line exceeds 80 characters", "severity": "warning"},
            {"line": 128, "rule": "naming_convention", "message": "Variable should be snake_case", "severity": "warning"},
        ],
        "summary": "Found 2 style violations",
    },
    "license": {
        "violations": [
            {"file": "src/main.c", "issue": "Missing SPDX license header", "severity": "error"},
        ],
        "summary": "License compliance check complete",
    },
    "structure": {
        "issues": [
            {"path": "src/utils", "issue": "Non-standard directory layout", "suggestion": "Use standard layout"},
        ],
        "summary": "Structure analysis complete",
    },
    "patch": {
        "violations": [],
        "summary": "Patch format looks good",
    },
    "security": {
        "violations": [
            {"line": 55, "rule": "buffer_overflow", "message": "Potential buffer overflow in memcpy", "severity": "critical"},
        ],
        "summary": "Found 1 security issue",
    },
}


class MockProvider(BaseLLMProvider):
    """Offline mock provider — no network calls."""

    def complete(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        # Simulate small latency
        time.sleep(random.uniform(0.01, 0.05))

        # Find last user message
        last = ""
        for msg in reversed(messages or []):
            if msg.get("role") == "user":
                last = msg.get("content", "")
                break

        # Match domain keyword
        lower = last.lower()
        for domain, resp in _MOCK_RESPONSES.items():
            if domain in lower:
                return json.dumps(resp)

        # Default response
        return json.dumps(_MOCK_RESPONSES["style"])


def create_provider(config: LLMConfig) -> BaseLLMProvider:
    logger.info("LLM provider: Mock (offline)")
    return MockProvider(config)


# ═══════════════════════════════════════════════════════════════════════════
# LLMTools
# ═══════════════════════════════════════════════════════════════════════════

class LLMTools:
    """Mock LLM toolkit — generates plausible offline responses."""

    def __init__(
        self,
        config=None,
        model: Optional[str] = None,
        vectordb=None,
        intent_prompt_builder: Optional[Callable[[str], str]] = None,
    ):
        if isinstance(config, dict):
            config = LLMConfig()  # mock ignores dict values
        self.config = config or LLMConfig()
        if model:
            self.config.raw_model = model
        self.provider_instance = create_provider(self.config)
        self.vectordb = vectordb
        self._intent_prompt_builder = intent_prompt_builder or self._default_intent_prompt
        self.logger = logger

    @classmethod
    def from_env(cls, **kwargs) -> "LLMTools":
        return cls(**kwargs)

    # ── Core calls ───────────────────────────────────────────────────────

    def llm_call(self, prompt: str, model: Optional[str] = None) -> str:
        return self.provider_instance.complete(
            messages=[{"role": "user", "content": prompt}],
        )

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
    ) -> "LLMResponse":
        start = time.time()
        content = self.provider_instance.complete(messages=messages, system=system)
        return LLMResponse(
            content=content,
            model=model or self.config.model,
            tokens_used=random.randint(100, 500),
            latency_ms=(time.time() - start) * 1000 + random.randint(10, 200),
            provider="mock",
            is_mock=True,
        )

    # ── Intent extraction ────────────────────────────────────────────────

    def extract_intent_from_prompt(self, user_input: str) -> Dict[str, Any]:
        return {"intent": "retrieve", "criteria": {}, "fields_to_extract": [], "output_format": "summary"}

    @staticmethod
    def _default_intent_prompt(user_input: str) -> str:
        return f"Parse intent: {user_input}"

    # ── Response parsing ─────────────────────────────────────────────────

    @staticmethod
    def extract_json(response: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(response)
        except (json.JSONDecodeError, TypeError):
            pass
        m = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        bs, be = response.find("{"), response.rfind("}")
        if bs != -1 and be > bs:
            try:
                return json.loads(response[bs:be + 1])
            except json.JSONDecodeError:
                pass
        return None

    @staticmethod
    def extract_json_from_llm_response(response: str) -> str:
        if not isinstance(response, str):
            return str(response)
        response = response.strip()
        m = re.search(r"```(?:json)?\s*([\s\S]+?)```", response)
        if m:
            return m.group(1).strip()
        bs, be = response.find("{"), response.rfind("}")
        if bs != -1 and be > bs:
            return response[bs:be + 1]
        return response

    @staticmethod
    def format_llm_response(agent_response: Any) -> str:
        if agent_response is None:
            return "No response."
        if isinstance(agent_response, str):
            return agent_response
        if hasattr(agent_response, "content"):
            return str(agent_response.content)
        return str(agent_response)

    @staticmethod
    def count_tokens_approx(text: str) -> int:
        return len(text) // 4

    def truncate_to_token_budget(self, text: str, max_tokens: Optional[int] = None) -> str:
        budget = max_tokens or self.config.max_prompt_tokens
        if self.count_tokens_approx(text) <= budget:
            return text
        return text[: budget * 4] + "\n\n[... truncated ...]"

    def get_provider_info(self) -> Dict[str, str]:
        return {"provider": "mock", "model": self.config.model, "raw_model": self.config.raw_model, "provider_class": "MockProvider"}

    def switch_model(self, model: str) -> None:
        self.config.raw_model = model
        logger.info("Mock: switched model to %s (no-op)", model)

    def __repr__(self) -> str:
        return f"LLMTools(provider='mock', model='{self.config.model}')"


# ═══════════════════════════════════════════════════════════════════════════
# LLMResponse
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class LLMResponse:
    content: str
    model: str
    tokens_used: int
    latency_ms: float
    provider: str = "mock"
    is_mock: bool = True


LLMClient = LLMTools

__all__ = [
    "LLMConfig", "LLMTools", "LLMClient", "LLMResponse",
    "BaseLLMProvider", "MockProvider", "create_provider",
    "LLMError", "LLMProviderError", "LLMResponseError",
    "IntentExtractionError", "ProviderNotAvailableError",
]
