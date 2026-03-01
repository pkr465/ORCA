"""
Conversational compliance analysis chat agent for ORCA.

Provides a multi-turn conversational interface for querying compliance analysis results
using LLM + optional VectorDB retrieval. Implements session state management, intent extraction,
and custom VectorDB query building with metric/code-level biasing.

Modeled after CURE CodebaseAnalysisOrchestration pattern with conversational capabilities.

Features:
- Multi-turn conversation session state management
- Intent extraction from user queries (retrieve, compare, aggregate)
- Custom VectorDB query building with metric/code-level biasing
- Metric field awareness (complexity, dependencies, documentation, etc.)
- Code-detail detection for file/line/snippet queries
- Multi-turn chain execution with optional recursion for clarification
- Flattening and metadata extraction from retrieved documents
- Leverages utils.llm_tools.LLMTools for LLM operations
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

try:
    from utils.llm_tools import LLMTools
except ImportError:
    LLMTools = None  # type: ignore

try:
    from db.vectordb_wrapper import VectorDB
except ImportError:
    VectorDB = None  # type: ignore

try:
    from utils.config_parser import load_config
except ImportError:
    load_config = None  # type: ignore

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Session State
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ComplianceAnalysisSessionState:
    """Session state for multi-turn compliance analysis conversations."""

    # Input and output
    user_input: str = ""
    retrieved_docs: List[Dict[str, Any]] = field(default_factory=list)
    records: List[Dict[str, Any]] = field(default_factory=list)
    prompt: str = ""
    llm_response: str = ""
    formatted_response: str = ""

    # Extracted intent
    intent: str = "retrieve"  # retrieve, compare, aggregate
    criteria: Dict[str, Any] = field(default_factory=dict)
    fields_to_extract: List[str] = field(default_factory=list)
    output_format: str = "summary"  # summary, table, list, json
    vectordb_query: Dict[str, Any] = field(default_factory=dict)

    # Conversation context
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    turn_count: int = 0
    session_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert session state to dictionary for serialization."""
        return {
            "user_input": self.user_input,
            "intent": self.intent,
            "criteria": self.criteria,
            "fields_to_extract": self.fields_to_extract,
            "output_format": self.output_format,
            "llm_response": self.llm_response,
            "formatted_response": self.formatted_response,
            "turn_count": self.turn_count,
            "session_id": self.session_id,
            "records_count": len(self.records),
            "docs_count": len(self.retrieved_docs),
        }


# ═══════════════════════════════════════════════════════════════════════════
# Main Orchestration Class
# ═══════════════════════════════════════════════════════════════════════════

class ComplianceAnalysisOrchestration:
    """
    Conversational orchestration for compliance analysis queries.

    Combines LLM intent extraction with optional VectorDB retrieval to provide
    a flexible multi-turn interface for analyzing compliance data. Supports
    metric-aware queries, code-detail drilling, and result aggregation.
    """

    # Metric fields for query biasing
    METRIC_FIELDS = {
        "complexity",
        "dependencies",
        "documentation_coverage",
        "maintainability",
        "quality",
        "code_smells",
        "security_issues",
        "vulnerabilities",
        "testability",
        "technical_debt",
        "style_compliance",
        "lint_issues",
        "test_coverage",
    }

    # Code-detail cues for detection
    CODE_DETAIL_CUES = {"line", "file", "snippet", "function", "method", "class"}

    # VectorDB section biasing keys
    VECTORDB_SECTIONS = {
        "dependency_graph",
        "documentation",
        "metrics",
        "code_quality",
        "test_reports",
        "security_reports",
        "file_index",
        "definitions",
        "code_snippet",
    }

    def __init__(
        self,
        vectordb: Optional[Any] = None,
        llm_tools: Optional[LLMTools] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the compliance analysis orchestration.

        Args:
            vectordb: Optional VectorDB instance for document retrieval
            llm_tools: Optional LLMTools instance (auto-initialized if None)
            config: Optional configuration dictionary
        """
        self.vectordb = vectordb
        self.llm_tools = llm_tools or self._init_llm_tools()
        self.config = config or self._init_config()

        # Try to initialize VectorDB if not provided
        if not self.vectordb and VectorDB:
            self.vectordb = self._init_vectordb()

        logger.info(
            "ComplianceAnalysisOrchestration initialized "
            f"(LLM: {type(self.llm_tools).__name__}, "
            f"VectorDB: {type(self.vectordb).__name__ if self.vectordb else 'None'})"
        )

    def _init_llm_tools(self) -> Any:
        """Initialize LLMTools with fallback to mock."""
        if LLMTools is None:
            logger.warning("LLMTools not available, operations will be limited")
            return None
        try:
            return LLMTools()
        except Exception as e:
            logger.warning(f"Failed to initialize LLMTools: {e}")
            return None

    def _init_vectordb(self) -> Optional[Any]:
        """Initialize VectorDB with fallback handling."""
        if VectorDB is None:
            logger.debug("VectorDB not available")
            return None
        try:
            return VectorDB()
        except Exception as e:
            logger.debug(f"Failed to initialize VectorDB: {e}")
            return None

    def _init_config(self) -> Dict[str, Any]:
        """Load configuration from ORCA config files."""
        if load_config is None:
            return {}
        try:
            root = Path(__file__).resolve().parent.parent
            for name in ("config.yaml", "global_config.yaml"):
                p = root / name
                if p.is_file():
                    cfg_obj = load_config(str(p))
                    return self._config_to_dict(cfg_obj)
        except Exception as e:
            logger.debug(f"Failed to load config: {e}")
        return {}

    @staticmethod
    def _config_to_dict(cfg_obj: Any) -> Dict[str, Any]:
        """Convert config object to dictionary."""
        if isinstance(cfg_obj, dict):
            return cfg_obj
        if hasattr(cfg_obj, "__dict__"):
            return cfg_obj.__dict__
        return {}

    # ─────────────────────────────────────────────────────────────────────

    def flatten_docs(self, retrieved_docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Flatten retrieved documents for analysis.

        Removes nesting, extracts core fields, and normalizes structure.

        Args:
            retrieved_docs: Raw documents from VectorDB

        Returns:
            Flattened list of documents
        """
        flattened = []
        for doc in retrieved_docs:
            flat = {
                "id": doc.get("id", ""),
                "text": doc.get("text", doc.get("content", "")),
                "metadata": self.safe_metadata(doc),
                "score": doc.get("score", 0.0),
            }
            flattened.append(flat)
        logger.debug(f"Flattened {len(retrieved_docs)} documents")
        return flattened

    def safe_metadata(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Safely extract and normalize metadata from a document.

        Args:
            doc: Document dictionary

        Returns:
            Normalized metadata dictionary
        """
        metadata = doc.get("metadata", {})
        if isinstance(metadata, dict):
            return metadata
        return {}

    # ─────────────────────────────────────────────────────────────────────

    def format_and_extract_intent_and_query(
        self, user_query: str
    ) -> Dict[str, Any]:
        """
        Extract intent, criteria, and VectorDB query from user query.

        Uses LLM to parse natural language into structured intent.

        Args:
            user_query: User's natural language query

        Returns:
            Dictionary with intent, criteria, fields_to_extract, output_format, vectordb_query
        """
        if not self.llm_tools:
            logger.warning("LLMTools not available, returning default intent")
            return {
                "intent": "retrieve",
                "criteria": {},
                "fields_to_extract": [],
                "output_format": "summary",
                "vectordb_query": {"text": user_query},
            }

        try:
            intent_obj = self.llm_tools.extract_intent_from_prompt(user_query)
        except Exception as e:
            logger.warning(f"Intent extraction failed: {e}, using default")
            intent_obj = {}

        # Extract or default each field
        intent = intent_obj.get("intent", "retrieve")
        criteria = intent_obj.get("criteria", {})
        fields_to_extract = intent_obj.get("fields_to_extract", [])
        output_format = intent_obj.get("output_format", "summary")

        # Build custom VectorDB query with metric/code biasing
        vectordb_query = self._build_vectordb_query(
            user_query, criteria, fields_to_extract
        )

        result = {
            "intent": intent,
            "criteria": criteria,
            "fields_to_extract": fields_to_extract,
            "output_format": output_format,
            "vectordb_query": vectordb_query,
        }

        logger.debug(
            f"Intent extraction: intent={intent}, "
            f"fields={len(fields_to_extract)}, format={output_format}"
        )

        return result

    def _build_vectordb_query(
        self,
        user_query: str,
        criteria: Dict[str, Any],
        fields_to_extract: List[str],
    ) -> Dict[str, Any]:
        """
        Build a custom VectorDB query with metric and section biasing.

        Args:
            user_query: Original user query
            criteria: Filter criteria
            fields_to_extract: Fields the user wants

        Returns:
            VectorDB query dictionary
        """
        # Detect metric fields in user query and requested fields
        detected_metrics = self._detect_metrics(user_query, fields_to_extract)
        detected_sections = self._detect_sections(user_query)
        has_code_detail = self._detect_code_detail(user_query)

        # Build query with biasing
        query = {
            "text": user_query,
            "criteria": criteria,
            "metric_bias": detected_metrics,
            "section_bias": detected_sections,
            "code_detail": has_code_detail,
            "filters": {},
        }

        # Add metric field filters if present
        if detected_metrics:
            for metric in detected_metrics:
                if metric in criteria:
                    query["filters"][metric] = criteria[metric]

        logger.debug(
            f"VectorDB query built: metrics={len(detected_metrics)}, "
            f"sections={len(detected_sections)}, code_detail={has_code_detail}"
        )

        return query

    def _detect_metrics(
        self, user_query: str, fields_to_extract: List[str]
    ) -> List[str]:
        """Detect requested metric fields."""
        query_lower = user_query.lower()
        detected = []

        for metric in self.METRIC_FIELDS:
            if metric.replace("_", " ") in query_lower or metric.replace("_", "-") in query_lower:
                detected.append(metric)

        detected.extend([f for f in fields_to_extract if f in self.METRIC_FIELDS])

        return list(set(detected))

    def _detect_sections(self, user_query: str) -> List[str]:
        """Detect requested VectorDB sections."""
        query_lower = user_query.lower()
        detected = []

        for section in self.VECTORDB_SECTIONS:
            if section.replace("_", " ") in query_lower or section.replace("_", "-") in query_lower:
                detected.append(section)

        return detected

    def _detect_code_detail(self, user_query: str) -> bool:
        """Detect if query is asking for code-level details."""
        query_lower = user_query.lower()
        return any(cue in query_lower for cue in self.CODE_DETAIL_CUES)

    # ─────────────────────────────────────────────────────────────────────

    def run_multiturn_chain(
        self, state: ComplianceAnalysisSessionState, recursion_limit: int = 0
    ) -> ComplianceAnalysisSessionState:
        """
        Execute multi-turn chain with optional recursion for clarification.

        Orchestrates:
        1. Intent extraction
        2. VectorDB retrieval (if available)
        3. LLM analysis
        4. Formatting and response generation
        5. Optional clarification recursion

        Args:
            state: Session state to update
            recursion_limit: Maximum recursion depth (0=no recursion)

        Returns:
            Updated session state
        """
        state.turn_count += 1
        logger.info(f"Turn {state.turn_count}: Processing '{state.user_input[:60]}...'")

        try:
            # Step 1: Extract intent and build query
            intent_result = self.format_and_extract_intent_and_query(state.user_input)
            state.intent = intent_result["intent"]
            state.criteria = intent_result["criteria"]
            state.fields_to_extract = intent_result["fields_to_extract"]
            state.output_format = intent_result["output_format"]
            state.vectordb_query = intent_result["vectordb_query"]

            # Step 2: Retrieve documents (if VectorDB available)
            if self.vectordb and state.vectordb_query:
                try:
                    state.retrieved_docs = self._retrieve_documents(state.vectordb_query)
                    state.records = self.flatten_docs(state.retrieved_docs)
                except Exception as e:
                    logger.warning(f"VectorDB retrieval failed: {e}")
                    state.records = []

            # Step 3: Call LLM for analysis
            state.prompt = self._build_llm_prompt(state)
            state.llm_response = self._call_llm(state.prompt)

            # Step 4: Format response
            state.formatted_response = self._format_response(
                state.llm_response, state.output_format
            )

            # Step 5: Check if follow-up needed and recurse if allowed
            if recursion_limit > 0 and self.needs_followup(state.llm_response):
                clarification = self.generate_clarification_question(state.llm_response)
                state.conversation_history.append(
                    {"role": "assistant", "content": state.formatted_response}
                )
                state.conversation_history.append(
                    {"role": "assistant", "content": clarification}
                )
                state.user_input = clarification
                state = self.run_multiturn_chain(state, recursion_limit - 1)

            # Add to conversation history
            state.conversation_history.append(
                {"role": "user", "content": state.user_input}
            )
            state.conversation_history.append(
                {"role": "assistant", "content": state.formatted_response}
            )

            logger.info(f"Turn {state.turn_count} complete: {len(state.records)} records")

        except Exception as e:
            logger.error(f"Error in multi-turn chain: {e}", exc_info=True)
            state.formatted_response = f"Error processing query: {e}"

        return state

    def _retrieve_documents(self, query_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Retrieve documents from VectorDB."""
        if not self.vectordb:
            return []

        try:
            text_query = query_dict.get("text", "")
            filters = query_dict.get("filters", {})
            metric_bias = query_dict.get("metric_bias", [])
            section_bias = query_dict.get("section_bias", [])

            # Build VectorDB-specific query
            vdb_query = {"query": text_query, "limit": 10}

            if filters:
                vdb_query["filters"] = filters
            if metric_bias:
                vdb_query["boost_fields"] = metric_bias
            if section_bias:
                vdb_query["section_filter"] = section_bias

            # Query VectorDB (signature varies by implementation)
            if hasattr(self.vectordb, "search"):
                results = self.vectordb.search(**vdb_query)
            elif hasattr(self.vectordb, "query"):
                results = self.vectordb.query(**vdb_query)
            else:
                results = []

            return results if isinstance(results, list) else [results]

        except Exception as e:
            logger.warning(f"VectorDB retrieval error: {e}")
            return []

    def _build_llm_prompt(self, state: ComplianceAnalysisSessionState) -> str:
        """Build LLM prompt from session state and retrieved documents."""
        parts = [
            "# Compliance Analysis Query",
            f"## User Query\n{state.user_input}",
            f"## Intent: {state.intent.upper()}",
        ]

        if state.records:
            parts.append(f"## Retrieved Records ({len(state.records)})")
            for i, record in enumerate(state.records[:5], 1):  # Top 5 records
                text_snippet = record.get("text", "")[:200]
                parts.append(f"### Record {i}\n{text_snippet}...")

        if state.conversation_history:
            parts.append("## Conversation Context")
            for msg in state.conversation_history[-4:]:  # Last 4 messages
                role = msg.get("role", "").upper()
                content = msg.get("content", "")[:150]
                parts.append(f"{role}: {content}")

        parts.extend(
            [
                f"## Output Format: {state.output_format.upper()}",
                "## Task",
                "Analyze the user's query and provide a structured response based on the intent and retrieved documents.",
            ]
        )

        return "\n\n".join(parts)

    def _call_llm(self, prompt: str) -> str:
        """Call LLM with prompt."""
        if not self.llm_tools:
            return "LLM tools not available"

        try:
            return self.llm_tools.llm_call(prompt)
        except Exception as e:
            logger.warning(f"LLM call failed: {e}")
            return f"Error: {e}"

    def _format_response(self, response: str, output_format: str) -> str:
        """Format LLM response according to requested format."""
        if output_format == "json":
            try:
                obj = json.loads(response)
                return json.dumps(obj, indent=2)
            except json.JSONDecodeError:
                return response

        elif output_format == "table":
            # Simple ASCII table formatting
            lines = response.split("\n")
            return "\n".join([f"  {line}" for line in lines])

        elif output_format == "list":
            lines = response.split("\n")
            return "\n".join([f"- {line.strip()}" for line in lines if line.strip()])

        else:  # summary
            return response

    # ─────────────────────────────────────────────────────────────────────

    def needs_followup(self, response: str) -> bool:
        """Detect if response needs clarification follow-up."""
        unclear_phrases = {
            "unclear",
            "ambiguous",
            "need more information",
            "cannot determine",
            "requires clarification",
        }
        response_lower = response.lower()
        return any(phrase in response_lower for phrase in unclear_phrases)

    def generate_clarification_question(self, last_response: str) -> str:
        """Generate a clarification question based on last response."""
        if not self.llm_tools:
            return "Could you provide more details?"

        try:
            prompt = (
                "Based on this response, generate a brief clarification question "
                "to better understand the user's needs:\n\n"
                f"{last_response[:500]}"
            )
            return self.llm_tools.llm_call(prompt)
        except Exception as e:
            logger.warning(f"Clarification generation failed: {e}")
            return "Could you provide more details?"

    # ─────────────────────────────────────────────────────────────────────

    def run_simple_query(self, user_query: str) -> str:
        """
        Run a simple single-turn query and return formatted response.

        Convenience method for simple use cases without session management.

        Args:
            user_query: User's query string

        Returns:
            Formatted response string
        """
        state = ComplianceAnalysisSessionState(
            user_input=user_query,
            session_id=f"simple_{os.urandom(4).hex()}",
        )

        state = self.run_multiturn_chain(state)
        return state.formatted_response


# ═══════════════════════════════════════════════════════════════════════════
# Convenience Exports
# ═══════════════════════════════════════════════════════════════════════════

__all__ = [
    "ComplianceAnalysisSessionState",
    "ComplianceAnalysisOrchestration",
]
