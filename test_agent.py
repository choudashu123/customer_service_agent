"""
Automated checks for the deterministic core: the policy engine, the RAG index,
the agent tools, and the REST API. These need no LLM key — the chat agent
(LangGraph ReAct over the same tools) is exercised manually.

Run:  .venv/bin/python -m pytest -q
"""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import policy
import rag


def _now():
    return datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def _in_days(d):
    return (_now() + timedelta(days=d)).isoformat()


# --------------------------------------------------------------------------- #
# policy.evaluate                                                             #
# --------------------------------------------------------------------------- #
def test_flex_full_refund():
    r = policy.evaluate(rate_plan="FLEX", check_in=_in_days(10), nights=3,
                        nightly_rate=150.0, taxes_fees=0.0, amount_paid=450.0,
                        now=_now())
    assert r["refund_amount"] == 450.00
    assert r["refund_pct"] == 100.0


def test_semi_partial_refund():
    r = policy.evaluate(rate_plan="SEMI", check_in=_in_days(3), nights=4,
                        nightly_rate=100.0, taxes_fees=0.0, amount_paid=400.0,
                        now=_now())
    assert r["refund_amount"] == 200.00


def test_nonref_tax_only():
    r = policy.evaluate(rate_plan="NONREF", check_in=_in_days(15), nights=3,
                        nightly_rate=100.0, taxes_fees=35.0, amount_paid=335.0,
                        now=_now())
    assert r["refund_amount"] == 35.00


def test_flex_one_night_penalty_inside_48h():
    r = policy.evaluate(rate_plan="FLEX", check_in=_in_days(1), nights=3,
                        nightly_rate=200.0, taxes_fees=0.0, amount_paid=600.0,
                        now=_now())
    assert r["refund_amount"] == 400.00


def test_boundary_exactly_48h_is_full():
    r = policy.evaluate(rate_plan="FLEX", check_in=(_now() + timedelta(hours=48)).isoformat(),
                        nights=2, nightly_rate=100.0, taxes_fees=0.0,
                        amount_paid=200.0, now=_now())
    assert r["refund_amount"] == 200.00


def test_semi_boundary_exactly_7_days_is_full():
    r = policy.evaluate(rate_plan="SEMI", check_in=(_now() + timedelta(days=7)).isoformat(),
                        nights=2, nightly_rate=100.0, taxes_fees=10.0,
                        amount_paid=210.0, now=_now())
    assert r["refund_amount"] == 210.00


def test_parse_accepts_z_suffix():
    r = policy.evaluate(rate_plan="FLEX", check_in="2026-09-21T15:00:00.000Z",
                        nights=2, nightly_rate=100.0, taxes_fees=0.0,
                        amount_paid=200.0, now=_now())
    assert r["ok"] and r["refund_amount"] == 200.00


# --------------------------------------------------------------------------- #
# RAG index                                                                    #
# --------------------------------------------------------------------------- #
def test_rag_finds_nonrefundable_for_promo_question():
    hits = rag.search("Is the promo rate refundable if I cancel?", k=3)
    assert hits
    assert hits[0]["source"] == "non-refundable-rate.md"


def test_rag_empty_query_returns_nothing():
    assert rag.search("", k=3) == []


# --------------------------------------------------------------------------- #
# Agent tools (the layer the LangGraph agent calls into)                      #
# --------------------------------------------------------------------------- #
def _fresh_db(tmp_path):
    import db as db_mod
    db_mod.DB_PATH = tmp_path / "test.db"
    importlib.reload(db_mod)
    db_mod.init_db(force=True)
    return db_mod


def test_tool_lookup_rejects_wrong_surname(tmp_path):
    db = _fresh_db(tmp_path)
    assert db.lookup_booking("HTL-101", "Nope")["found"] is False
    assert db.lookup_booking("HTL-101", "Davis")["found"] is True


def test_tool_cancellation_flow_is_two_phase(tmp_path):
    db = _fresh_db(tmp_path)

    quote = db.evaluate_cancellation_policy("HTL-101")
    assert quote["ok"] and quote["refund_amount"] == 450.00

    preview = db.cancel_booking("HTL-101", confirm=False)
    assert preview["needs_confirmation"] is True
    assert db.get_booking("HTL-101")["status"] == "CONFIRMED"

    done = db.cancel_booking("HTL-101", confirm=True, reason="guest confirmed")
    assert done["ok"] and done["refund_amount"] == 450.00
    assert done["refund_code"].startswith("RF-")
    assert db.get_booking("HTL-101")["status"] == "CANCELLED"

    again = db.cancel_booking("HTL-101", confirm=True)
    assert again["ok"] and again.get("already_cancelled")


def test_tool_search_policy_logs_and_returns_matches(tmp_path):
    db = _fresh_db(tmp_path)
    out = db.search_policy("non-refundable promo rate refund")
    assert out["matches"]
    assert db.TOOL_LOG[-1]["tool"] == "search_policy"


# --------------------------------------------------------------------------- #
# REST API (no chat — the agent needs an LLM key)                             #
# --------------------------------------------------------------------------- #
def _client(tmp_path):
    import db as db_mod
    db_mod.DB_PATH = tmp_path / "test.db"
    import app as app_mod
    importlib.reload(app_mod)
    return app_mod, TestClient(app_mod.app)


def test_seed_and_reset(tmp_path):
    app_mod, client = _client(tmp_path)

    r = client.get("/api/bookings").json()
    assert len(r["bookings"]) == 4
    assert all(b["status"] == "CONFIRMED" for b in r["bookings"])
    assert r["agent_mode"] == "llm"

    app_mod.db.cancel_booking("HTL-101", confirm=True)
    assert client.get("/api/bookings").json()["bookings"][0]["status"] == "CANCELLED"

    rr = client.post("/api/reset").json()
    assert all(b["status"] == "CONFIRMED" for b in rr["bookings"])


def test_hotel_catalog_and_booking_flow(tmp_path):
    _app_mod, client = _client(tmp_path)

    hotels = client.get("/api/hotels").json()["hotels"]
    assert len(hotels) == 4
    hotel_id = hotels[0]["hotel_id"]

    body = {
        "hotel_id": hotel_id, "rate_plan": "FLEX",
        "check_in": (datetime.now(timezone.utc) + timedelta(days=20)).isoformat(),
        "nights": 2, "guest_name": "Test Guest", "last_name": "Guest",
        "email": "guest@example.com",
    }
    r = client.post("/api/bookings", json=body)
    assert r.status_code == 201
    booking = r.json()["booking"]
    assert booking["booking_id"] not in ("HTL-101", "HTL-102", "HTL-103", "HTL-104")
    assert booking["status"] == "CONFIRMED"

    mine = client.get("/api/bookings", params={"email": "guest@example.com"}).json()
    assert len(mine["bookings"]) == 1
    assert mine["bookings"][0]["booking_id"] == booking["booking_id"]

    bad = client.post("/api/bookings", json={**body, "hotel_id": "NOPE"})
    assert bad.status_code == 400


if __name__ == "__main__":
    import subprocess, sys
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))
