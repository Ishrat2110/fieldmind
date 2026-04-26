"""
reorder_ai.py
-------------
Rule-based reorder suggestion service for the Farm Manager.

Generates a reorder suggestion whenever an inventory item drops at or below
its reorder_threshold. No external APIs required.

Public API:
  maybe_generate_suggestion(item, session) -> Notification | None
  get_active_suggestions(session, farm_id)  -> list[Notification]
  resolve_suggestion(nid, action, session)  -> Notification | None
"""

import json
import logging
from datetime import datetime, date, timedelta, timezone

from sqlalchemy import func

from models import (
    InventoryItem, UsageLog, TreatmentPlan,
    Notification, NotificationStatus,
)

log = logging.getLogger("reorder_ai")

_CACHE_TTL_HOURS     = 24
_DEFAULT_LEAD_DAYS   = 7
_MAX_QTY_MULTIPLIER  = 5.0


# ── helpers ────────────────────────────────────────────────────────────────────

def _burn_rate(item: InventoryItem, session, days: int = 30) -> float:
    """Average daily consumption over the last N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    total = session.query(func.sum(UsageLog.quantity_used)).filter(
        UsageLog.inventory_item_id == item.id,
        UsageLog.log_date >= cutoff,
    ).scalar() or 0.0
    return round(float(total) / days, 4) if days > 0 else 0.0


def _upcoming_demand(item: InventoryItem, session, horizon_days: int = 30) -> float:
    """Total quantity needed by unapplied TreatmentPlans within the next N days."""
    now        = datetime.now(timezone.utc)
    horizon_end = now + timedelta(days=horizon_days)
    plans = session.query(TreatmentPlan).filter(
        TreatmentPlan.inventory_item_id == item.id,
        TreatmentPlan.applied == False,
        TreatmentPlan.planned_date >= now,
        TreatmentPlan.planned_date <= horizon_end,
    ).all()
    total = sum(
        (p.rate_per_ha or 0) * (p.plot.area_ha if p.plot and p.plot.area_ha else 0)
        for p in plans
    )
    return round(total, 2)


def _rule_based_suggestion(item: InventoryItem, session) -> dict:
    """Compute a reorder suggestion purely from usage history and treatment plans."""
    burn      = _burn_rate(item, session, days=30) or 0.1
    upcoming  = _upcoming_demand(item, session, horizon_days=30)
    lead_days = _DEFAULT_LEAD_DAYS

    # How many days until we hit zero at current burn
    days_until = int(item.quantity_on_hand / burn) if burn > 0 else 999

    # Urgency
    if days_until <= 3:
        urgency = "critical"
    elif days_until <= 7:
        urgency = "high"
    elif days_until <= 14:
        urgency = "medium"
    else:
        urgency = "low"

    # Quantity to order: cover 30 days after lead time + upcoming demand – current stock
    projected_need = burn * (30 + lead_days) + upcoming - item.quantity_on_hand
    qty = max(projected_need, item.reorder_quantity or 0)

    # Round up to a sensible purchase unit
    step = 5 if item.unit and item.unit.lower() in ("bags", "bag") else 10
    qty = max(round(qty / step + 0.5) * step, step)

    stockout_date   = (date.today() + timedelta(days=days_until)).isoformat()
    estimated_cost  = round(qty * item.unit_cost, 2) if item.unit_cost else None

    rationale = (
        f"Stock is at {item.quantity_on_hand:.1f} {item.unit} "
        f"(threshold: {item.reorder_threshold} {item.unit}). "
        f"At the current burn rate of {burn:.1f} {item.unit}/day, "
        f"stock will last ~{days_until} day{'s' if days_until != 1 else ''}. "
        f"Ordering {qty:.0f} {item.unit} covers 30 days of use after the "
        f"{lead_days}-day lead time"
        + (f" plus {upcoming:.1f} {item.unit} of scheduled treatments." if upcoming else ".")
    )

    return {
        "suggested_order_qty":    qty,
        "unit":                   item.unit,
        "urgency":                urgency,
        "predicted_stockout_date": stockout_date,
        "days_until_stockout":    days_until,
        "rationale":              rationale,
        "assumed_lead_time_days": lead_days,
        "estimated_cost_usd":     estimated_cost,
    }


def _cached_suggestion(item_id: int, session) -> "Notification | None":
    """Return an existing pending Notification younger than TTL, or None."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_CACHE_TTL_HOURS)
    return (
        session.query(Notification)
        .filter(
            Notification.inventory_item_id == item_id,
            Notification.status == NotificationStatus.pending,
            Notification.created_at >= cutoff,
        )
        .order_by(Notification.created_at.desc())
        .first()
    )


def _extract_urgency(ai_message: str) -> str:
    """Parse urgency from the embedded JSON in ai_message."""
    try:
        start = ai_message.find("<!--json\n")
        end   = ai_message.find("\n-->", start)
        if start == -1 or end == -1:
            return "medium"
        return json.loads(ai_message[start + 9:end]).get("urgency", "medium")
    except Exception:
        return "medium"


def _persist_suggestion(item: InventoryItem, result: dict, session) -> "Notification":
    """Write a Notification row from a suggestion result dict."""
    max_qty = (item.reorder_quantity or 0) * _MAX_QTY_MULTIPLIER
    if max_qty > 0 and result["suggested_order_qty"] > max_qty:
        result["suggested_order_qty"] = max_qty
        result["rationale"] += f" (capped at {_MAX_QTY_MULTIPLIER}× reorder quantity)"

    try:
        stockout_dt = datetime.strptime(result["predicted_stockout_date"], "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, KeyError):
        stockout_dt = None

    full_json  = json.dumps(result, indent=2, default=str)
    ai_message = f"{result['rationale']}\n\n<!--json\n{full_json}\n-->"

    n = Notification(
        farm_id              = item.farm_id,
        inventory_item_id    = item.id,
        status               = NotificationStatus.pending,
        predicted_stockout   = stockout_dt,
        days_until_stockout  = result.get("days_until_stockout"),
        current_stock        = item.quantity_on_hand,
        ai_message           = ai_message,
        draft_order_qty      = result.get("suggested_order_qty"),
        draft_order_sent     = False,
        created_at           = datetime.now(timezone.utc),
    )
    session.add(n)
    session.commit()
    n._urgency = result.get("urgency", "medium")
    return n


# ── public API ─────────────────────────────────────────────────────────────────

def maybe_generate_suggestion(item: InventoryItem, session) -> "Notification | None":
    """Generate (or return cached) a reorder suggestion when stock is at/below threshold.

    Returns None if stock is healthy or if writing fails.
    """
    try:
        if item.reorder_threshold is None or item.quantity_on_hand > item.reorder_threshold:
            return None

        # Skip items with no recent activity (likely retired)
        if item.quantity_on_hand == 0:
            cutoff90 = datetime.now(timezone.utc) - timedelta(days=90)
            recent = session.query(UsageLog).filter(
                UsageLog.inventory_item_id == item.id,
                UsageLog.log_date >= cutoff90,
            ).first()
            if not recent:
                return None

        cached = _cached_suggestion(item.id, session)
        if cached:
            cached._urgency = _extract_urgency(cached.ai_message)
            return cached

        result = _rule_based_suggestion(item, session)
        return _persist_suggestion(item, result, session)

    except Exception as exc:
        log.error("reorder_ai: error generating suggestion for item %d: %s", item.id, exc)
        return None


def get_active_suggestions(session, farm_id: int) -> list:
    """All pending notifications for a farm, newest first."""
    suggestions = (
        session.query(Notification)
        .filter_by(farm_id=farm_id, status=NotificationStatus.pending)
        .order_by(Notification.created_at.desc())
        .all()
    )
    for s in suggestions:
        s._urgency = _extract_urgency(s.ai_message)
    return suggestions


def resolve_suggestion(nid: int, action: str, session) -> "Notification | None":
    """Mark a pending suggestion as approved or dismissed."""
    n = session.get(Notification, nid)
    if not n or n.status != NotificationStatus.pending:
        return None
    n.status     = NotificationStatus.approved if action == "approve" else NotificationStatus.dismissed
    n.resolved_at = datetime.now(timezone.utc)
    session.commit()
    return n
