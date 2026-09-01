"""
SQLite storage (hotels + bookings) and the agent tools — the only code allowed
to touch the database, run refund maths, or query the policy corpus.
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import policy
import rag

DB_PATH = Path(__file__).resolve().parent / "bookings.db"

# Rate plans priced relative to the hotel's Flexible nightly rate.
RATE_MULTIPLIER = {"FLEX": 1.00, "SEMI": 0.90, "NONREF": 0.80}
TAX_RATE = 0.12


# --------------------------------------------------------------------------- #
# Connection / schema / seed                                                  #
# --------------------------------------------------------------------------- #
def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _seed_hotels() -> list[dict]:
    return [
        dict(hotel_id="H1", name="Harbour View Hotel", city="Sydney",
             nightly_rate=150.0,
             blurb="Rooms over Circular Quay, walk to the Opera House."),
        dict(hotel_id="H2", name="Alpine Lodge", city="Queenstown",
             nightly_rate=100.0,
             blurb="Timber chalet on the lake, ski shuttle at the door."),
        dict(hotel_id="H3", name="City Central Inn", city="Melbourne",
             nightly_rate=100.0,
             blurb="Compact rooms in the laneways district, tram stop outside."),
        dict(hotel_id="H4", name="Seaside Resort", city="Gold Coast",
             nightly_rate=200.0,
             blurb="Beachfront suites, two pools, surfboard hire included."),
    ]


def _seed_bookings() -> list[dict]:
    """Four canonical demo bookings, dated relative to now."""
    now = datetime.now(timezone.utc)

    def check_in(days_out: int) -> str:
        return _iso((now + timedelta(days=days_out)).replace(
            hour=15, minute=0, second=0, microsecond=0))

    common = dict(status="CONFIRMED", refund_amount=0.0, refund_code=None,
                  cancelled_at=None, currency="USD", email="demo@example.com")
    return [
        dict(booking_id="HTL-101", last_name="Davis", guest_name="Jordan Davis",
             hotel="Harbour View Hotel, Sydney", rate_plan="FLEX",
             check_in=check_in(10), nights=3, nightly_rate=150.0, taxes_fees=0.0,
             amount_paid=450.0, **common),
        dict(booking_id="HTL-102", last_name="Miller", guest_name="Sam Miller",
             hotel="Alpine Lodge, Queenstown", rate_plan="SEMI",
             check_in=check_in(3), nights=4, nightly_rate=100.0, taxes_fees=0.0,
             amount_paid=400.0, **common),
        dict(booking_id="HTL-103", last_name="Smith", guest_name="Riley Smith",
             hotel="City Central Inn, Melbourne", rate_plan="NONREF",
             check_in=check_in(15), nights=3, nightly_rate=100.0, taxes_fees=35.0,
             amount_paid=335.0, **common),
        dict(booking_id="HTL-104", last_name="Wilson", guest_name="Alex Wilson",
             hotel="Seaside Resort, Gold Coast", rate_plan="FLEX",
             check_in=check_in(1), nights=3, nightly_rate=200.0, taxes_fees=0.0,
             amount_paid=600.0, **common),
    ]


_BOOKING_COLS = list(_seed_bookings()[0].keys())
_HOTEL_COLS = list(_seed_hotels()[0].keys())


def init_db(force: bool = False) -> None:
    fresh = force or not DB_PATH.exists()
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS hotels (
                hotel_id     TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                city         TEXT NOT NULL,
                nightly_rate REAL NOT NULL,
                blurb        TEXT NOT NULL
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                booking_id    TEXT PRIMARY KEY,
                last_name     TEXT NOT NULL,
                guest_name    TEXT NOT NULL,
                email         TEXT NOT NULL,
                hotel         TEXT NOT NULL,
                rate_plan     TEXT NOT NULL,
                check_in      TEXT NOT NULL,
                nights        INTEGER NOT NULL,
                nightly_rate  REAL NOT NULL,
                taxes_fees    REAL NOT NULL,
                amount_paid   REAL NOT NULL,
                currency      TEXT NOT NULL,
                status        TEXT NOT NULL,
                refund_amount REAL NOT NULL DEFAULT 0,
                refund_code   TEXT,
                cancelled_at  TEXT
            )""")
        if fresh:
            c.execute("DELETE FROM hotels")
            c.execute("DELETE FROM bookings")
            c.executemany(
                f"INSERT INTO hotels ({','.join(_HOTEL_COLS)}) "
                f"VALUES ({','.join('?' for _ in _HOTEL_COLS)})",
                [tuple(r[k] for k in _HOTEL_COLS) for r in _seed_hotels()])
            c.executemany(
                f"INSERT INTO bookings ({','.join(_BOOKING_COLS)}) "
                f"VALUES ({','.join('?' for _ in _BOOKING_COLS)})",
                [tuple(r[k] for k in _BOOKING_COLS) for r in _seed_bookings()])


# --------------------------------------------------------------------------- #
# Reads                                                                       #
# --------------------------------------------------------------------------- #
def all_hotels() -> list[dict]:
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM hotels ORDER BY hotel_id")]


def get_hotel(hotel_id: str) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM hotels WHERE hotel_id = ?",
                      (hotel_id.strip().upper(),)).fetchone()
    return dict(r) if r else None


def get_booking(booking_id: str) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM bookings WHERE booking_id = ?",
                      (booking_id.strip().upper(),)).fetchone()
    return dict(r) if r else None


def all_bookings(email: str | None = None) -> list[dict]:
    with _conn() as c:
        if email:
            rows = c.execute("SELECT * FROM bookings WHERE lower(email) = ? "
                             "ORDER BY booking_id", (email.strip().lower(),))
        else:
            rows = c.execute("SELECT * FROM bookings ORDER BY booking_id")
        return [dict(r) for r in rows]


def _next_booking_id() -> str:
    with _conn() as c:
        rows = c.execute("SELECT booking_id FROM bookings").fetchall()
    nums = [int(r["booking_id"].split("-")[1]) for r in rows
            if r["booking_id"].startswith("HTL-")]
    return f"HTL-{(max(nums) + 1) if nums else 101}"


def create_booking(*, hotel_id: str, rate_plan: str, check_in: str, nights: int,
                   guest_name: str, last_name: str, email: str) -> dict:
    hotel = get_hotel(hotel_id)
    if not hotel:
        return {"ok": False, "reason": "unknown hotel"}
    rate_plan = rate_plan.upper()
    if rate_plan not in RATE_MULTIPLIER:
        return {"ok": False, "reason": "unknown rate plan"}
    try:
        # Normalize to the same offset-based ISO format the seed data uses,
        # regardless of whether the client sent a 'Z' suffix or an offset.
        raw = check_in[:-1] + "+00:00" if check_in.endswith("Z") else check_in
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        check_in = _iso(parsed)
    except ValueError:
        return {"ok": False, "reason": "invalid check_in date"}
    nights = max(1, int(nights))
    nightly = round(hotel["nightly_rate"] * RATE_MULTIPLIER[rate_plan], 2)
    room = round(nightly * nights, 2)
    taxes = round(room * TAX_RATE, 2)
    row = dict(
        booking_id=_next_booking_id(), last_name=last_name.strip(),
        guest_name=guest_name.strip(), email=email.strip(),
        hotel=f"{hotel['name']}, {hotel['city']}", rate_plan=rate_plan,
        check_in=check_in, nights=nights, nightly_rate=nightly, taxes_fees=taxes,
        amount_paid=round(room + taxes, 2), currency="USD", status="CONFIRMED",
        refund_amount=0.0, refund_code=None, cancelled_at=None)
    with _conn() as c:
        c.execute(
            f"INSERT INTO bookings ({','.join(_BOOKING_COLS)}) "
            f"VALUES ({','.join('?' for _ in _BOOKING_COLS)})",
            tuple(row[k] for k in _BOOKING_COLS))
    return {"ok": True, "booking": row}


# --------------------------------------------------------------------------- #
# Tool-execution log (observability)                                          #
# --------------------------------------------------------------------------- #
TOOL_LOG: list[dict] = []


def _log(name: str, params: dict, result: dict, t0: float) -> None:
    TOOL_LOG.append({
        "ts": _iso(datetime.now(timezone.utc)),
        "tool": name, "params": params, "result": result,
        "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
    })
    del TOOL_LOG[:-200]


# --------------------------------------------------------------------------- #
# Agent tools                                                                 #
# --------------------------------------------------------------------------- #
def search_policy(query: str, k: int = 3) -> dict:
    """RAG retrieval over the hotel policy corpus."""
    t0 = time.perf_counter()
    hits = rag.search(query, k=k)
    out = {"query": query, "matches": hits}
    _log("search_policy", {"query": query},
         {"n": len(hits), "sources": [h["source"] for h in hits]}, t0)
    return out


def lookup_booking(booking_id: str, last_name: str) -> dict:
    t0 = time.perf_counter()
    row = get_booking(booking_id)
    if not row or row["last_name"].lower() != last_name.strip().lower():
        out = {"found": False,
               "reason": "No booking matches that reference and surname."}
    else:
        out = {"found": True, "booking": row}
    _log("lookup_booking", {"booking_id": booking_id, "last_name": last_name},
         {"found": out["found"]}, t0)
    return out


def evaluate_cancellation_policy(booking_id: str) -> dict:
    t0 = time.perf_counter()
    row = get_booking(booking_id)
    if not row:
        out = {"ok": False, "reason": "Booking not found."}
    elif row["status"] != "CONFIRMED":
        out = {"ok": False, "reason": f"Booking is already {row['status']}."}
    else:
        out = policy.evaluate(
            rate_plan=row["rate_plan"], check_in=row["check_in"],
            nights=row["nights"], nightly_rate=row["nightly_rate"],
            taxes_fees=row["taxes_fees"], amount_paid=row["amount_paid"])
        out["booking_id"] = row["booking_id"]
        out["currency"] = row["currency"]
    _log("evaluate_cancellation_policy", {"booking_id": booking_id},
         {k: out.get(k) for k in ("ok", "refund_amount", "refund_pct")}, t0)
    return out


def cancel_booking(booking_id: str, confirm: bool = False, reason: str = "") -> dict:
    """Two-phase: confirm=False only quotes; confirm=True mutates. Idempotent."""
    t0 = time.perf_counter()
    row = get_booking(booking_id)

    if not row:
        out = {"ok": False, "reason": "Booking not found."}
    elif row["status"] == "CANCELLED":
        out = {"ok": True, "already_cancelled": True, "booking_id": row["booking_id"],
               "status": "CANCELLED", "refund_amount": row["refund_amount"],
               "refund_code": row["refund_code"], "currency": row["currency"]}
    elif not confirm:
        out = {"ok": True, "needs_confirmation": True,
               "quote": evaluate_cancellation_policy(booking_id)}
    else:
        quote = policy.evaluate(
            rate_plan=row["rate_plan"], check_in=row["check_in"],
            nights=row["nights"], nightly_rate=row["nightly_rate"],
            taxes_fees=row["taxes_fees"], amount_paid=row["amount_paid"])
        refund = quote["refund_amount"]
        code = "RF-" + str(uuid.uuid4().int % 100000).zfill(5)
        ts = _iso(datetime.now(timezone.utc))
        with _conn() as c:
            c.execute("UPDATE bookings SET status='CANCELLED', refund_amount=?, "
                      "refund_code=?, cancelled_at=? WHERE booking_id=?",
                      (refund, code, ts, row["booking_id"]))
        out = {"ok": True, "booking_id": row["booking_id"], "status": "CANCELLED",
               "refund_amount": refund, "refund_code": code,
               "currency": row["currency"], "cancelled_at": ts,
               "rule_applied": quote["rule_applied"], "reason": reason}

    _log("cancel_booking",
         {"booking_id": booking_id, "confirm": confirm, "reason": reason},
         {k: out.get(k) for k in ("ok", "needs_confirmation", "refund_code")}, t0)
    return out
