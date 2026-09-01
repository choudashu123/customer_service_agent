"""
The customer-service agent.

A single path: a LangGraph prebuilt ReAct agent driving four tools — RAG policy
search, booking lookup, refund evaluation, and the two-phase cancel. The chat
model is provider-agnostic: whichever of OPENAI_API_KEY, GOOGLE_API_KEY, or
ANTHROPIC_API_KEY is present picks the provider (LangChain's `init_chat_model`
handles the rest). No keyword matching, no deterministic fallback.
"""
from __future__ import annotations

import os

from langchain.chat_models import init_chat_model
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.prebuilt import create_react_agent

# Hard ceiling on model<->tool hops per user turn. A normal answer needs 1-3
# (decide -> call a tool -> answer); anything past this is a loop, so stop.
_RECURSION_LIMIT = 12

import db
import rag
from policy import RATE_PLANS

# (env var, init_chat_model provider, default model) — first key wins.
# Model names are rolling aliases where the provider offers one, so a retired
# snapshot never breaks the default. Override per provider with $LLM_MODEL.
_PROVIDERS = [
    ("OPENAI_API_KEY", "openai", "gpt-4o-mini"),
    ("GOOGLE_API_KEY", "google_genai", "gemini-flash-latest"),
    ("ANTHROPIC_API_KEY", "anthropic", "claude-sonnet-5"),
]

_POLICY_SUMMARY = "\n".join(
    f"- {v['label']} ({k}): {v['summary']}" for k, v in RATE_PLANS.items()
)

SYSTEM_PROMPT = f"""You are the customer-service agent for a hotel booking site. \
You help guests with three things: understanding cancellation/refund policy, \
looking up their booking, and cancelling a booking.

You have a knowledge base of policy documents. For ANY question about rules, \
refund amounts in general, timelines, no-shows, date changes, force majeure, \
check-in times, etc., call `search_policy` and answer strictly from what it \
returns. Quote the rate plan by name. If the documents do not cover it, say so.

Rate plans, for orientation only:
{_POLICY_SUMMARY}

Tools:
- search_policy(query): retrieve passages from the policy knowledge base.
- lookup_booking(booking_id, last_name): needs BOTH the reference (e.g. HTL-101) \
and the surname. Ask for whatever is missing before calling.
- evaluate_cancellation_policy(booking_id): returns the exact refund figure for \
one real booking. Call this before stating any booking-specific refund number.
- cancel_booking(booking_id, confirm, reason): confirm=false returns a quote and \
changes nothing; confirm=true performs the cancellation.

Hard rules:
1. Never invent a refund number. Booking-specific numbers come only from \
evaluate_cancellation_policy; general rules come only from search_policy.
2. Before offering to cancel, show the guest the refund amount, the rule \
applied, and hours until check-in.
3. Call cancel_booking with confirm=true ONLY after the guest has clearly said \
yes to that specific cancellation in their latest message. Otherwise use \
confirm=false or ask.
4. After a successful cancellation, give the refund amount and the refund code.
5. Keep replies short and plain. Ask one question at a time."""


# --------------------------------------------------------------------------- #
# Tools — thin wrappers so LangChain gets a schema; the real work is in db.py #
# --------------------------------------------------------------------------- #
@tool
def search_policy(query: str) -> dict:
    """Search the hotel cancellation/refund policy knowledge base and return the
    most relevant passages."""
    return db.search_policy(query)


@tool
def lookup_booking(booking_id: str, last_name: str) -> dict:
    """Look up a booking by its reference (e.g. HTL-101) and the guest surname.
    Both are required."""
    return db.lookup_booking(booking_id, last_name)


@tool
def evaluate_cancellation_policy(booking_id: str) -> dict:
    """Compute the exact refund for one booking without cancelling it."""
    return db.evaluate_cancellation_policy(booking_id)


@tool
def cancel_booking(booking_id: str, confirm: bool = False, reason: str = "") -> dict:
    """Cancel a booking. confirm=false previews the refund quote and changes
    nothing; confirm=true performs the cancellation — only after the guest has
    explicitly agreed to this specific cancellation."""
    return db.cancel_booking(booking_id, confirm=confirm, reason=reason)


TOOLS = [search_policy, lookup_booking, evaluate_cancellation_policy, cancel_booking]


def _select_provider() -> tuple[str, str]:
    for env_key, provider, default_model in _PROVIDERS:
        if os.environ.get(env_key):
            return provider, os.environ.get("LLM_MODEL", default_model)
    raise RuntimeError(
        "No LLM API key found. Set one of OPENAI_API_KEY, GOOGLE_API_KEY, or "
        "ANTHROPIC_API_KEY (in the environment or a .env file)."
    )


class Agent:
    """Provider-agnostic ReAct agent with per-session memory."""

    mode = "llm"

    def __init__(self) -> None:
        provider, model = _select_provider()
        self.provider = provider
        # max_retries=1: fail fast instead of a 60s exponential-backoff storm
        # when the provider returns 429 (e.g. Gemini free-tier: 5 req/min).
        self._model = init_chat_model(
            model, model_provider=provider, temperature=0, max_retries=1
        )
        self._build_graph()

    def _build_graph(self) -> None:
        self._graph = create_react_agent(
            self._model, TOOLS, prompt=SYSTEM_PROMPT, checkpointer=MemorySaver()
        )

    def reset(self) -> None:
        self._build_graph()  # a fresh MemorySaver drops every session's history

    def reply(self, session_id: str, message: str) -> dict:
        log_start = len(db.TOOL_LOG)
        try:
            state = self._graph.invoke(
                {"messages": [{"role": "user", "content": message}]},
                config={"configurable": {"thread_id": session_id},
                        "recursion_limit": _RECURSION_LIMIT},
            )
            final = state["messages"][-1].content if state["messages"] else ""
        except GraphRecursionError:
            final = ("Sorry, I couldn't work that out. Could you rephrase, or give "
                     "me the booking reference and surname again?")
        if isinstance(final, list):  # some providers return content blocks
            final = "".join(
                b.get("text", "") for b in final if isinstance(b, dict)
            )
        return {
            "reply": (final or "").strip() or "…",
            "tools_called": [e["tool"] for e in db.TOOL_LOG[log_start:]],
        }


def build_agent() -> Agent:
    rag.get_index()  # warm the policy index at startup
    return Agent()
