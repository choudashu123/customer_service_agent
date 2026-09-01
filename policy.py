"""
Deterministic cancellation-policy evaluator.

Pure functions only: no I/O, no database, no clock reads except the `now`
argument that callers pass in. This is the single source of truth for refund
maths so the LLM never has to (and never gets to) do arithmetic itself.
"""
from __future__ import annotations

from datetime import datetime, timezone

# Rate plans and the plain-English rules the evaluator applies.
RATE_PLANS = {
    "FLEX": {
        "label": "Flexible",
        "summary": (
            "Free cancellation up to 48 hours before check-in (100% refund). "
            "Inside 48 hours a 1-night penalty applies; the rest is refunded."
        ),
    },
    "SEMI": {
        "label": "Semi-Flexible",
        "summary": (
            "100% refund if cancelled 7+ days before check-in, 50% refund "
            "between 2 and 7 days, no room refund inside 48 hours."
        ),
    },
    "NONREF": {
        "label": "Non-Refundable Promo",
        "summary": (
            "Room charge is never refundable. Prepaid taxes & fees are always "
            "refunded when the stay is cancelled."
        ),
    },
}


def _parse(dt: str) -> datetime:
    if dt.endswith("Z"):  # Python 3.9's fromisoformat rejects the 'Z' suffix
        dt = dt[:-1] + "+00:00"
    d = datetime.fromisoformat(dt)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def evaluate(
    *,
    rate_plan: str,
    check_in: str,
    nights: int,
    nightly_rate: float,
    taxes_fees: float,
    amount_paid: float,
    now: datetime | None = None,
) -> dict:
    """Return a refund quote for one booking. Never mutates anything."""
    now = now or datetime.now(timezone.utc)
    hours = (_parse(check_in) - now).total_seconds() / 3600.0
    days = hours / 24.0

    room_value = round(nightly_rate * nights, 2)
    taxes = round(taxes_fees, 2)
    one_night = round(nightly_rate, 2)

    if rate_plan == "FLEX":
        if hours >= 48:
            refund = room_value + taxes
            rule = "Flexible rate, 48h or more before check-in: full refund."
        else:
            refund = max(0.0, room_value - one_night) + taxes
            rule = (
                f"Flexible rate, inside 48h: one-night penalty of "
                f"{one_night:.2f} kept, remainder refunded."
            )
    elif rate_plan == "SEMI":
        if days >= 7:
            refund = room_value + taxes
            rule = "Semi-Flexible rate, 7+ days before check-in: full refund."
        elif hours >= 48:
            refund = round(room_value * 0.5, 2) + taxes
            rule = "Semi-Flexible rate, 48h-7 days before check-in: 50% room refund."
        else:
            refund = taxes
            rule = "Semi-Flexible rate, inside 48h: room charge forfeited, taxes returned."
    elif rate_plan == "NONREF":
        refund = taxes
        rule = "Non-Refundable rate: room charge not refundable, taxes returned."
    else:
        return {"ok": False, "reason": f"unknown rate plan {rate_plan!r}"}

    refund = round(min(refund, amount_paid), 2)
    pct = round(100.0 * refund / amount_paid, 1) if amount_paid else 0.0

    return {
        "ok": True,
        "rate_plan": rate_plan,
        "rate_plan_label": RATE_PLANS[rate_plan]["label"],
        "hours_until_check_in": round(hours, 1),
        "days_until_check_in": round(days, 2),
        "amount_paid": round(amount_paid, 2),
        "room_value": room_value,
        "taxes_fees": taxes,
        "refund_amount": refund,
        "non_refundable_amount": round(amount_paid - refund, 2),
        "refund_pct": pct,
        "rule_applied": rule,
    }
