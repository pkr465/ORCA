"""
ORCA — Anthropic Claude LLM backend.

Drop-in provider module exposing the standard ORCA LLM API:
    LLMConfig, LLMTools, BaseLLMProvider, AnthropicProvider,
    create_provider, and all exception classes.

Usage (via router — preferred):
    from utils.llm_tools import LLMTools   # auto-selects provider

Usage (direct):
    from utils.llm_tools_anthropic import LLMTools
    tools = LLMTools()
    response = tools.llm_call("Analyze this code for security issues...")
"""

from __future__ import annotations

import abc
import json
import logging
import os
import re
import time
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("orca.llm.anthropic")


# ═══════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class LLMConfig:
    """Configuration for Anthropic Claude LLM provider."""

    # Model identifiers
    raw_model: str = "anthropic::claude-sonnet-4-20250514"
    coding_model: str = "anthropic::claude-sonnet-4-20250514"

    # API key — resolved from config → LLM_API_KEY → ANTHROPIC_API_KEY
    api_key: str = ""

    # Request defaults
    max_tokens: int = 8192
    temperature: float = 0.1
    timeout: int = 120
    max_retries: int = 3

    # Intent extraction
    intent_max_tokens: int = 4096
    intent_temperature: float = 0.0

    # Token budget (for prompt truncation)
    max_prompt_tokens: int = 100_000

    # Mock fallback
    mock_mode: bool = False

    @property
    def provider(self) -> str:
        return "anthropic"

    @property
    def model(self) -> str:
        """Extract bare model name from raw_model string."""
        if "::" in self.raw_model:
            return self.raw_model.split("::", 1)[1].strip()
        return self.raw_model

    @property
    def coding_model_name(self) -> str:
        if "::" in self.coding_model:
            return self.coding_model.split("::", 1)[1].strip()
        return self.coding_model

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Build config from global_config.yaml via ORCA's config_parser."""
        try:
            from utils.config_parser import load_config
            cfg_path = _find_config()
            if cfg_path:
                gc = load_config(cfg_path)
                api_key = (
                    gc.llm.api_key
                    or os.environ.get("LLM_API_KEY", "")
                    or os.environ.get("ANTHROPIC_API_KEY", "")
                )
                return cls(
                    raw_model=gc.llm.model or "anthropic::claude-sonnet-4-20250514",
                    coding_model=gc.llm.model or "anthropic::claude-sonnet-4-20250514",
                    api_key=api_key,
                    max_tokens=gc.llm.max_tokens,
                    temperature=gc.llm.temperature,
                    timeout=gc.llm.timeout,
                    max_retries=gc.llm.max_retries,
                    mock_mode=gc.llm.mock_mode,
                )
        except Exception as e:
            logger.warning("Failed to load config: %s — using defaults", e)

        # Fallback: env-only
        return cls(
            api_key=os.environ.get("LLM_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", ""),
        )


def _find_config() -> Optional[str]:
    """Locate the ORCA config file."""
    root = Path(__file__).resolve().parent.parent
    for name in ("config.yaml", "global_config.yaml"):
        p = root / name
        if p.is_file():
            return str(p)
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Exceptions
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
# Provider Abstraction Layer
# ═══════════════════════════════════════════════════════════════════════════

class BaseLLMProvider(abc.ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: LLMConfig):
        self.config = config

    @abc.abstractmethod
    def complete(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Send a completion request and return the text response."""
        ...

    def complete_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        system: Optional[str] = None,
        tool_choice: Optional[Dict] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Completion with tool definitions (function calling)."""
        text = self.complete(messages=messages, system=system, max_tokens=max_tokens)
        return {"text": text, "tool_calls": [], "stop_reason": "end_turn"}


# ---------------------------------------------------------------------------
# Anthropic Claude Provider
# ---------------------------------------------------------------------------

_MODEL_MAX_OUTPUT = {
    "claude-sonnet": 64000,
    "claude-haiku": 64000,
    "claude-opus": 32000,
}
_DEFAULT_MAX_OUTPUT = 16384


def _clamp_max_tokens(model: str, requested: int) -> int:
    """Clamp max_tokens to the model's output limit."""
    limit = _DEFAULT_MAX_OUTPUT
    for prefix, cap in _MODEL_MAX_OUTPUT.items():
        if prefix in model.lower():
            limit = cap
            break
    return min(requested, limit)


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider using the official SDK."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = None

        if not config.api_key:
            logger.warning(
                "Anthropic API key missing. Set LLM_API_KEY in .env or global_config.yaml."
            )

    @property
    def client(self):
        """Lazy-initialise the Anthropic client."""
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise ProviderNotAvailableError(
                    "The 'anthropic' package is required. "
                    "Install it with: pip install anthropic"
                )
            init_kw: Dict[str, Any] = {}
            if self.config.api_key:
                init_kw["api_key"] = self.config.api_key
            if self.config.timeout:
                init_kw["timeout"] = float(self.config.timeout)
            if self.config.max_retries:
                init_kw["max_retries"] = self.config.max_retries
            self._client = anthropic.Anthropic(**init_kw)
        return self._client

    def complete(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Call Anthropic Claude Messages API."""
        api_messages = []
        resolved_system = system
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                resolved_system = (resolved_system + "\n\n" + content) if resolved_system else content
            else:
                api_messages.append({"role": role, "content": content})

        if not api_messages:
            api_messages = [{"role": "user", "content": ""}]

        safe_max = _clamp_max_tokens(self.config.model, max_tokens or self.config.max_tokens)

        create_kw: Dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": safe_max,
            "messages": api_messages,
            "temperature": temperature if temperature is not None else self.config.temperature,
        }
        if resolved_system:
            create_kw["system"] = resolved_system

        try:
            start = time.monotonic()
            response = self.client.messages.create(**create_kw)
            elapsed = time.monotonic() - start
            logger.debug(
                "Anthropic API: model=%s elapsed=%.2fs tokens=%d+%d",
                self.config.model, elapsed,
                response.usage.input_tokens, response.usage.output_tokens,
            )
            return response.content[0].text
        except Exception as e:
            logger.error("Anthropic API error: %s", e)
            raise LLMProviderError(f"Anthropic API call failed: {e}") from e

    def complete_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        system: Optional[str] = None,
        tool_choice: Optional[Dict] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Call Anthropic Claude Messages API with tool use."""
        api_messages = []
        resolved_system = system
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                resolved_system = (resolved_system + "\n\n" + content) if resolved_system else content
            else:
                api_messages.append({"role": role, "content": content})

        if not api_messages:
            api_messages = [{"role": "user", "content": ""}]

        create_kw: Dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": max_tokens or self.config.max_tokens,
            "messages": api_messages,
            "tools": tools,
        }
        if resolved_system:
            create_kw["system"] = resolved_system
        if tool_choice:
            create_kw["tool_choice"] = tool_choice

        try:
            response = self.client.messages.create(**create_kw)
            text_parts, tool_calls = [], []
            for block in response.content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)
                elif hasattr(block, "type") and block.type == "tool_use":
                    tool_calls.append({"id": block.id, "name": block.name, "input": block.input})
            return {"text": "\n".join(text_parts), "tool_calls": tool_calls, "stop_reason": response.stop_reason}
        except Exception as e:
            logger.error("Anthropic API error (tools): %s", e)
            raise LLMProviderError(f"Anthropic tool call failed: {e}") from e


def create_provider(config: LLMConfig) -> BaseLLMProvider:
    """Factory: create the Anthropic provider."""
    logger.info("LLM provider: Anthropic, model: %s", config.model)
    return AnthropicProvider(config)


# ═══════════════════════════════════════════════════════════════════════════
# LLMTools — high-level toolkit
# ═══════════════════════════════════════════════════════════════════════════

class LLMTools:
    """
    Anthropic-backed LLM toolkit for ORCA compliance analysis.

    Provides:
      - llm_call(prompt) — simple one-shot call
      - chat_completion(messages, ...) — OpenAI-style message list call
      - extract_json() — JSON extraction from LLM responses
      - extract_intent_from_prompt() — structured intent parsing
      - format_llm_response() — response normalisation

    Usage:
        tools = LLMTools()                           # auto-loads config
        tools = LLMTools(model="anthropic::claude-sonnet-4-20250514")
        print(tools.llm_call("Explain this code..."))
    """

    def __init__(
        self,
        config=None,
        model: Optional[str] = None,
        vectordb=None,
        intent_prompt_builder: Optional[Callable[[str], str]] = None,
    ):
        if isinstance(config, dict):
            config = _dict_to_llmconfig(config)
        self.config = config or LLMConfig.from_env()
        if model:
            self.config.raw_model = model
            self.config.coding_model = model
        self.provider_instance = create_provider(self.config)
        self.vectordb = vectordb
        self._intent_prompt_builder = intent_prompt_builder or self._default_intent_prompt
        self.logger = logger

    @classmethod
    def from_env(cls, **kwargs) -> "LLMTools":
        """Factory: build LLMTools from environment configuration."""
        return cls(config=LLMConfig.from_env(), **kwargs)

    # ── Core calls ───────────────────────────────────────────────────────

    def llm_call(self, prompt: str, model: Optional[str] = None) -> str:
        """Simple one-shot LLM call. Returns response text."""
        messages = [{"role": "user", "content": prompt}]
        try:
            return self.provider_instance.complete(
                messages=messages,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )
        except Exception as e:
            logger.error("llm_call failed: %s", e)
            return f"LLM invocation failed: {e}"

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
    ) -> "LLMResponse":
        """OpenAI-style chat completion (backward compat with LLMClient API)."""
        start = time.time()
        try:
            content = self.provider_instance.complete(
                messages=messages,
                system=system,
                max_tokens=max_tokens or self.config.max_tokens,
                temperature=temperature if temperature is not None else self.config.temperature,
            )
            return LLMResponse(
                content=content,
                model=model or self.config.model,
                tokens_used=0,
                latency_ms=(time.time() - start) * 1000,
                provider="anthropic",
                is_mock=False,
            )
        except Exception as e:
            logger.error("chat_completion failed: %s — falling back to mock", e)
            return _mock_response(messages, model or self.config.model, start)

    # ── Intent extraction ────────────────────────────────────────────────

    def extract_intent_from_prompt(self, user_input: str) -> Dict[str, Any]:
        """Parse natural language prompt into structured intent."""
        system_prompt = self._intent_prompt_builder(user_input)
        raw = self.llm_call(prompt=system_prompt)
        json_str = self.extract_json_from_llm_response(raw)
        try:
            obj = json.loads(json_str)
            if not isinstance(obj, dict):
                raise ValueError(f"Expected dict, got {type(obj)}")
            obj.setdefault("intent", "retrieve")
            return obj
        except (json.JSONDecodeError, ValueError) as e:
            raise IntentExtractionError(f"Intent parse failed: {e}") from e

    @staticmethod
    def _default_intent_prompt(user_input: str) -> str:
        return (
            "You are an expert codebase analysis assistant.\n\n"
            "Parse the user's query and return a JSON object with:\n"
            '- "intent": "retrieve" | "compare" | "aggregate"\n'
            '- "criteria": filter object (or {} for all)\n'
            '- "fields_to_extract": list of requested info types\n'
            '- "output_format": "summary" | "table" | "list" | "json"\n\n'
            "Only return the JSON object.\n\n"
            f"User prompt: {user_input}\n"
        )

    # ── Response parsing ─────────────────────────────────────────────────

    @staticmethod
    def extract_json(response: str) -> Optional[Dict[str, Any]]:
        """Extract JSON dict from LLM response text."""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        m = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        depth, start = 0, None
        for i, ch in enumerate(response):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        return json.loads(response[start:i + 1])
                    except json.JSONDecodeError:
                        start = None
        return None

    @staticmethod
    def extract_json_from_llm_response(response: str) -> str:
        """Extract JSON string from LLM response (CURE-compatible)."""
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
        """Normalise various LLM response formats into a plain string."""
        if agent_response is None:
            return "No response."
        if isinstance(agent_response, str):
            return agent_response
        if hasattr(agent_response, "content"):
            content = agent_response.content
            if isinstance(content, list):
                parts = [
                    (b.text if hasattr(b, "text") else b.get("text", str(b)) if isinstance(b, dict) else str(b))
                    for b in content
                ]
                return "\n".join(parts) or "No text content."
            return str(content)
        if isinstance(agent_response, list) and agent_response:
            for msg in reversed(agent_response):
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    return msg.get("content", "No content.")
            last = agent_response[-1]
            return last.get("content", str(last)) if isinstance(last, dict) else str(last)
        return str(agent_response)

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def count_tokens_approx(text: str) -> int:
        return len(text) // 4

    def truncate_to_token_budget(self, text: str, max_tokens: Optional[int] = None) -> str:
        budget = max_tokens or self.config.max_prompt_tokens
        if self.count_tokens_approx(text) <= budget:
            return text
        return text[: budget * 4] + "\n\n[... truncated ...]"

    # ── Provider info ────────────────────────────────────────────────────

    def get_provider_info(self) -> Dict[str, str]:
        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "raw_model": self.config.raw_model,
            "provider_class": type(self.provider_instance).__name__,
        }

    def switch_model(self, model: str) -> None:
        self.config.raw_model = model
        self.provider_instance = create_provider(self.config)
        logger.info("Switched to: %s", self.config.model)

    def __repr__(self) -> str:
        return f"LLMTools(provider='anthropic', model='{self.config.model}')"


# ═══════════════════════════════════════════════════════════════════════════
# LLMResponse dataclass  (backward compat with old LLMClient API)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class LLMResponse:
    """Response from an LLM API call."""
    content: str
    model: str
    tokens_used: int
    latency_ms: float
    provider: str = "anthropic"
    is_mock: bool = False


def _mock_response(messages, model, start_time) -> LLMResponse:
    return LLMResponse(
        content=json.dumps({"violations": [], "summary": "Mock fallback"}),
        model=model,
        tokens_used=random.randint(100, 500),
        latency_ms=(time.time() - start_time) * 1000 + random.randint(10, 200),
        provider="mock",
        is_mock=True,
    )


# ── Backward-compat alias ────────────────────────────────────────────────
def _dict_to_llmconfig(d: dict) -> LLMConfig:
    """Convert a plain dict (from YAML config) to an LLMConfig dataclass."""
    return LLMConfig(
        raw_model=d.get("model", "anthropic::claude-sonnet-4-20250514"),
        coding_model=d.get("model", "anthropic::claude-sonnet-4-20250514"),
        api_key=d.get("api_key", "") or os.environ.get("LLM_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", ""),
        max_tokens=int(d.get("max_tokens", 8192)),
        temperature=float(d.get("temperature", 0.1)),
        timeout=int(d.get("timeout", 120)),
        max_retries=int(d.get("max_retries", 3)),
        mock_mode=bool(d.get("mock_mode", False)),
    )


LLMClient = LLMTools

__all__ = [
    "LLMConfig", "LLMTools", "LLMClient", "LLMResponse",
    "BaseLLMProvider", "AnthropicProvider", "create_provider",
    "LLMError", "LLMProviderError", "LLMResponseError",
    "IntentExtractionError", "ProviderNotAvailableError",
]
