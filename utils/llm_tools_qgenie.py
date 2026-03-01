"""
ORCA — QGenie LLM backend.

Drop-in provider module exposing the standard ORCA LLM API:
    LLMConfig, LLMTools, BaseLLMProvider, QGenieProvider,
    create_provider, and all exception classes.

QGenie uses its own SDK (``qgenie.integrations.langchain.QGenieChat``).
If the SDK is not installed, a lightweight HTTP fallback is used instead.

Usage (via router — preferred):
    from utils.llm_tools import LLMTools   # auto-selects provider

Usage (direct):
    from utils.llm_tools_qgenie import LLMTools
    tools = LLMTools()
    response = tools.llm_call("Analyze this code...")
"""

from __future__ import annotations

import abc
import json
import logging
import os
import re
import time
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("orca.llm.qgenie")


# ═══════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class LLMConfig:
    """Configuration for QGenie LLM provider."""

    # Model identifiers
    raw_model: str = "qgenie::qwen2.5-14b-1m"
    coding_model: str = "qgenie::qwen2.5-14b-1m"

    # QGenie API key
    qgenie_api_key: str = ""

    # QGenie endpoint (SDK or HTTP fallback)
    qgenie_endpoint: str = ""
    qgenie_base_url: str = "https://api.qgenie.io/v1"

    # Request defaults
    max_tokens: int = 8192
    temperature: float = 0.1
    timeout: int = 120
    max_retries: int = 2

    # Intent extraction
    intent_max_tokens: int = 4096
    intent_temperature: float = 0.0

    # Token budget
    max_prompt_tokens: int = 100_000

    # Mock fallback
    mock_mode: bool = False

    @property
    def provider(self) -> str:
        return "qgenie"

    @property
    def model(self) -> str:
        if "::" in self.raw_model:
            return self.raw_model.split("::", 1)[1].strip()
        return self.raw_model

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Build config from global_config.yaml via ORCA's config_parser."""
        try:
            from utils.config_parser import load_config
            cfg_path = _find_config()
            if cfg_path:
                gc = load_config(cfg_path)
                api_key = (
                    getattr(gc.llm, "qgenie_api_key", "")
                    or os.environ.get("QGENIE_API_KEY", "")
                )
                return cls(
                    raw_model=gc.llm.model or "qgenie::qwen2.5-14b-1m",
                    coding_model=gc.llm.model or "qgenie::qwen2.5-14b-1m",
                    qgenie_api_key=api_key,
                    qgenie_base_url=getattr(gc.llm, "qgenie_base_url", "") or "https://api.qgenie.io/v1",
                    max_tokens=gc.llm.max_tokens,
                    temperature=gc.llm.temperature,
                    timeout=gc.llm.timeout,
                    max_retries=gc.llm.max_retries,
                    mock_mode=gc.llm.mock_mode,
                )
        except Exception as e:
            logger.warning("Failed to load config: %s — using defaults", e)

        return cls(
            qgenie_api_key=os.environ.get("QGENIE_API_KEY", ""),
        )


def _find_config() -> Optional[str]:
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
        ...

    def complete_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        system: Optional[str] = None,
        tool_choice: Optional[Dict] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        text = self.complete(messages=messages, system=system, max_tokens=max_tokens)
        return {"text": text, "tool_calls": [], "stop_reason": "end_turn"}


# ---------------------------------------------------------------------------
# QGenie Provider
# ---------------------------------------------------------------------------

class QGenieProvider(BaseLLMProvider):
    """
    QGenie model provider.

    Tries the QGenie SDK (``qgenie.integrations.langchain.QGenieChat``)
    first; falls back to a plain HTTP POST to the OpenAI-compatible
    ``/chat/completions`` endpoint when the SDK is not installed.
    """

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._sdk_model = None
        self._use_sdk: Optional[bool] = None  # None = not yet probed

        if not config.qgenie_api_key:
            logger.warning(
                "QGenie API key missing. Set QGENIE_API_KEY in .env or global_config.yaml."
            )

    # ── SDK lazy init ────────────────────────────────────────────────────

    def _try_sdk(self):
        """Attempt to initialise the QGenie LangChain SDK."""
        if self._use_sdk is not None:
            return
        try:
            from qgenie.integrations.langchain import QGenieChat
            init_kw: Dict[str, Any] = {
                "model": self.config.model,
                "timeout": self.config.timeout,
            }
            if self.config.qgenie_api_key:
                init_kw["api_key"] = self.config.qgenie_api_key
            if self.config.qgenie_endpoint:
                init_kw["endpoint"] = self.config.qgenie_endpoint
            self._sdk_model = QGenieChat(**init_kw)
            self._use_sdk = True
            logger.info("QGenie SDK initialised (model=%s)", self.config.model)
        except ImportError:
            self._use_sdk = False
            logger.info("QGenie SDK not installed — using HTTP fallback")

    # ── Completions ──────────────────────────────────────────────────────

    def complete(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        self._try_sdk()

        if self._use_sdk:
            return self._complete_sdk(messages, system, max_tokens, temperature)
        return self._complete_http(messages, system, max_tokens, temperature)

    # ── SDK path ─────────────────────────────────────────────────────────

    def _complete_sdk(self, messages, system, max_tokens, temperature) -> str:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
        except ImportError:
            raise ProviderNotAvailableError(
                "langchain_core is required for QGenie SDK. "
                "Install: pip install langchain-core"
            )

        lc_msgs: list = []
        if system:
            lc_msgs.append(SystemMessage(content=system))
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                lc_msgs.append(HumanMessage(content=content))
            elif role == "system":
                lc_msgs.append(SystemMessage(content=content))

        try:
            start = time.monotonic()
            result = self._sdk_model.invoke(
                lc_msgs,
                max_tokens=max_tokens or self.config.max_tokens,
                temperature=temperature if temperature is not None else self.config.temperature,
                repetition_penalty=1.1,
                top_k=50,
                top_p=0.95,
            )
            logger.debug("QGenie SDK: elapsed=%.2fs", time.monotonic() - start)
            return result.content
        except Exception as e:
            logger.error("QGenie SDK error: %s", e)
            raise LLMProviderError(f"QGenie SDK call failed: {e}") from e

    # ── HTTP fallback ────────────────────────────────────────────────────

    def _complete_http(self, messages, system, max_tokens, temperature) -> str:
        import urllib.request
        import urllib.error

        url = f"{self.config.qgenie_base_url}/chat/completions"

        all_msgs = []
        if system:
            all_msgs.append({"role": "system", "content": system})
        all_msgs.extend(messages)

        payload = json.dumps({
            "model": self.config.model,
            "messages": all_msgs,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
        }).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.qgenie_api_key}",
        }

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            start = time.monotonic()
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            logger.debug("QGenie HTTP: elapsed=%.2fs", time.monotonic() - start)
            return body["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error("QGenie HTTP error: %s", e)
            raise LLMProviderError(f"QGenie HTTP call failed: {e}") from e


def create_provider(config: LLMConfig) -> BaseLLMProvider:
    """Factory: create the QGenie provider."""
    logger.info("LLM provider: QGenie, model: %s", config.model)
    return QGenieProvider(config)


# ═══════════════════════════════════════════════════════════════════════════
# LLMTools — high-level toolkit
# ═══════════════════════════════════════════════════════════════════════════

class LLMTools:
    """
    QGenie-backed LLM toolkit for ORCA compliance analysis.

    API-compatible with the Anthropic LLMTools in llm_tools_anthropic.py.
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
        return cls(config=LLMConfig.from_env(), **kwargs)

    # ── Core calls ───────────────────────────────────────────────────────

    def llm_call(self, prompt: str, model: Optional[str] = None) -> str:
        """Simple one-shot LLM call."""
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
        """OpenAI-style chat completion (backward compat)."""
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
                provider="qgenie",
                is_mock=False,
            )
        except Exception as e:
            logger.error("chat_completion failed: %s — mock fallback", e)
            return _mock_response(messages, model or self.config.model, start)

    # ── Intent extraction ────────────────────────────────────────────────

    def extract_intent_from_prompt(self, user_input: str) -> Dict[str, Any]:
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
        return f"LLMTools(provider='qgenie', model='{self.config.model}')"


# ═══════════════════════════════════════════════════════════════════════════
# LLMResponse  (backward compat with old LLMClient)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class LLMResponse:
    content: str
    model: str
    tokens_used: int
    latency_ms: float
    provider: str = "qgenie"
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


def _dict_to_llmconfig(d: dict) -> LLMConfig:
    """Convert a plain dict (from YAML config) to an LLMConfig dataclass."""
    return LLMConfig(
        raw_model=d.get("model", "qgenie::qwen2.5-14b-1m"),
        coding_model=d.get("model", "qgenie::qwen2.5-14b-1m"),
        qgenie_api_key=d.get("qgenie_api_key", "") or os.environ.get("QGENIE_API_KEY", ""),
        qgenie_base_url=d.get("qgenie_base_url", "https://api.qgenie.io/v1"),
        max_tokens=int(d.get("max_tokens", 8192)),
        temperature=float(d.get("temperature", 0.1)),
        timeout=int(d.get("timeout", 120)),
        max_retries=int(d.get("max_retries", 2)),
        mock_mode=bool(d.get("mock_mode", False)),
    )


LLMClient = LLMTools

__all__ = [
    "LLMConfig", "LLMTools", "LLMClient", "LLMResponse",
    "BaseLLMProvider", "QGenieProvider", "create_provider",
    "LLMError", "LLMProviderError", "LLMResponseError",
    "IntentExtractionError", "ProviderNotAvailableError",
]
