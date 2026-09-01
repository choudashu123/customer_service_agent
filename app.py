"""
Travel Customer Service Agent — prototype
========================================

FastAPI backend for a demo hotel-booking site with an embedded LLM + RAG
customer-service chat widget:

  * Booking site API — browse hotels, create a booking, list "my bookings".
  * Chat agent — a LangGraph ReAct agent over search_policy (RAG),
    lookup_booking, evaluate_cancellation_policy, cancel_booking. The provider
    is whichever of OPENAI_API_KEY / GOOGLE_API_KEY / ANTHROPIC_API_KEY is set.

    ./run.sh          # or:  python3 app.py     (honours $PORT, default 8000)
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv()

import agent  # noqa: E402  (must follow _load_dotenv so the key is visible)
import db  # noqa: E402

db.init_db()

# Built on the first chat request so the REST endpoints (and tests) run without
# an LLM key; the chat agent still requires one.
_AGENT: "agent.Agent | None" = None


def get_agent() -> "agent.Agent":
    global _AGENT
    if _AGENT is None:
        _AGENT = agent.build_agent()
    return _AGENT


app = FastAPI(title="Travel Customer Service Agent")


class ChatIn(BaseModel):
    message: str
    session_id: Optional[str] = None


class BookingIn(BaseModel):
    hotel_id: str
    rate_plan: str
    check_in: str
    nights: int
    guest_name: str
    last_name: str
    email: str


def _chat_error(sid: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"session_id": sid, "reply": f"⚠️ {message}",
                         "tools_called": [], "agent_mode": "llm",
                         "bookings": db.all_bookings(), "logs": db.TOOL_LOG[-30:]},
                        status_code=status)


@app.post("/api/chat")
def chat(body: ChatIn) -> JSONResponse:
    sid = body.session_id or ("sess-" + uuid.uuid4().hex[:12])
    try:
        result = get_agent().reply(sid, (body.message or "").strip())
    except RuntimeError as exc:  # no LLM key configured
        return _chat_error(sid, str(exc), 503)
    except Exception as exc:  # provider/model/network failure — keep it JSON
        return _chat_error(sid, f"LLM call failed: {type(exc).__name__}: {exc}", 502)
    return JSONResponse({
        "session_id": sid,
        "reply": result["reply"],
        "tools_called": result["tools_called"],
        "agent_mode": "llm",
        "bookings": db.all_bookings(),
        "logs": db.TOOL_LOG[-30:],
    })


@app.get("/api/hotels")
def hotels() -> dict:
    return {"hotels": db.all_hotels()}


@app.post("/api/bookings")
def create_booking(body: BookingIn) -> JSONResponse:
    out = db.create_booking(**body.model_dump())
    return JSONResponse(out, status_code=201 if out.get("ok") else 400)


@app.get("/api/bookings")
def bookings(email: Optional[str] = Query(default=None)) -> dict:
    from policy import RATE_PLANS

    return {"bookings": db.all_bookings(email=email), "rate_plans": RATE_PLANS,
            "agent_mode": "llm"}


@app.get("/api/logs")
def logs() -> dict:
    return {"logs": db.TOOL_LOG}


@app.post("/api/reset")
def reset() -> dict:
    db.init_db(force=True)
    db.TOOL_LOG.clear()
    if _AGENT is not None:
        _AGENT.reset()
    return {"ok": True, "bookings": db.all_bookings()}


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
