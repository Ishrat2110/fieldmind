"""
reorder_ai.py
-------------
AI-powered reorder suggestion service for the Farm Manager.

Public API:
  maybe_generate_suggestion(item, session) -> Notification | None
  get_active_suggestions(session, farm_id)  -> list[Notification]
  resolve_suggestion(nid, action, session)  -> Notification | None
"""

import json
import logging
import os
from datetime import datetime, date, timedelta, timezone

from sqlalchemy import func

from models import (
    InventoryItem, UsageLog, TreatmentPlan, Plot,
    Notification, NotificationStatus,
)

log = logging.getLogger("reorder_ai")

_GEMINI_KEY = os.getenv("GEMINI_API_KEY")
_GEMINI_ENABLED = bool(_GEMINI_KEY)
_MODEL = None

if _GEMINI_ENABLED:
    try:
        import google.generativeai as genai
        genai.configure(api_key=_GEMINI_KEY)
        _MODEL = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.3,
            },
        )
        log.info("reorder_ai: Gemini enabled (gemini-1.5-flash)")
    except Exception as e:
        log.warning("reorder_ai: Failed to initialise Gemini — %s", e)
        _GEMINI_ENABLED = False
else:
    log.warning("reorder_ai: GEMINI_API_KEY not set — using rule-based fallback only.")

_CACHE_TTL_HOURS = int(os.getenv("REORDER_AI_CACHE_HOURS", "24"))
_DEFAULT_LEAD_DAYS = int(os.getenv("REORDER_AI_DEFAULT_LEAD_DAYS", "7"))
_MAX_QTY_MULTIPLIER = float(os.getenv("REORDER_AI_MAX_QTY_MULTIPLIER", "5"))

REQUIRED_KEYS = {
    "suggested_order_qty", "unit", "urgency",
    "predicted_stockout_date", "days_until_stockout",
    "rationale", "assumed_lead_time_days",
    "estimated_cost_usd", "confidence",
}
VALID_URGENCY = {"low", "medium", "high", "critical"}
VALID_CONFIDENCE = {"low", "medium", "high"}


# ── internal helpers ───────────────────────────────────────────────────────────

def _burn_rate(item: InventoryItem, session, days: int = 30) -> float:
    """Trailing-N-day average daily consumption. Returns 0.0 if no data."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = (
        session.query(func.sum(UsageLog.quantity_used))
        .filter(
            UsageLog.inventory_item_id == item.id,
            UsageLog.log_date >= cutoff,
        )
        .scalar()
    )
    total = float(result or 0.0)
    return round(total / days, 4) if days > 0 else 0.0


def _upcoming_demand(item: InventoryItem, session, horizon_days: int = 30) -> dict:
    """Sum of rate_per_ha * plot.area_ha for unapplied TreatmentPlan rows
    for this item whose planned_date falls within the next horizon_days."""
    horizon_end = datetime.now(timezone.utc) + timedelta(days=horizon_days)
    now = datetime.now(timezone.utc)

    plans = (
        session.query(TreatmentPlan)
        .filter(
            TreatmentPlan.inventory_item_id == item.id,
            TreatmentPlan.applied == False,
            TreatmentPlan.planned_date >= now,
            TreatmentPlan.planned_date <= horizon_end,
        )
        .all()
    )

    total_qty = 0.0
    treatments = []
    for p in plans[:5]:  # cap at 5 to keep prompts small
        area = p.plot.area_ha if p.plot and p.plot.area_ha else 0.0
        qty = p.rate_per_ha * area
        total_qty += qty
        planned_str = p.planned_date.strftime("%Y-%m-%d") if p.planned_date else None
        treatments.append({
            "plot_code": p.plot.plot_code if p.plot else None,
            "rate_per_ha": p.rate_per_ha,
            "area_ha": area,
            "planned_date": planned_str,
        })

    return {"total_quantity": round(total_qty, 2), "unit": item.unit, "treatments": treatments}


def _build_context(item: InventoryItem, session) -> dict:
    """Assemble the dict that goes into the Gemini prompt."""
    burn = _burn_rate(item, session, days=30)
    burn_7d = _burn_rate(item, session, days=7)
    trend = round(burn_7d / burn, 2) if burn > 0 else 1.0

    # 30-day total
    cutoff30 = datetime.now(timezone.utc) - timedelta(days=30)
    total30 = session.query(func.sum(UsageLog.quantity_used)).filter(
        UsageLog.inventory_item_id == item.id,
        UsageLog.log_date >= cutoff30,
    ).scalar() or 0.0

    last_log = (
        session.query(UsageLog)
        .filter_by(inventory_item_id=item.id)
        .order_by(UsageLog.log_date.desc())
        .first()
    )
    last_log_date = last_log.log_date.strftime("%Y-%m-%d") if last_log and last_log.log_date else None

    if last_log and last_log.log_date:
        log_dt = last_log.log_date
        if log_dt.tzinfo is None:
            log_dt = log_dt.replace(tzinfo=timezone.utc)
        days_of_data = min((datetime.now(timezone.utc) - log_dt).days, 30)
    else:
        days_of_data = 0

    days_until = int(item.quantity_on_hand / burn) if burn > 0 else 999
    stockout_date = (date.today() + timedelta(days=days_until)).isoformat()

    upcoming = _upcoming_demand(item, session, horizon_days=30)

    return {
        "item": {
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "unit": item.unit,
            "quantity_on_hand": item.quantity_on_hand,
            "reorder_threshold": item.reorder_threshold,
            "reorder_quantity": item.reorder_quantity,
            "unit_cost": item.unit_cost,
            "supplier": item.supplier,
        },
        "usage": {
            "avg_daily_burn": burn,
            "days_of_data": days_of_data,
            "trend_7d_vs_30d": trend,
            "last_log_date": last_log_date,
            "total_30d": round(float(total30), 2),
        },
        "upcoming_demand_30d": upcoming,
        "stockout_naive": {
            "days_until": days_until,
            "predicted_date": stockout_date,
        },
        "constraints": {
            "typical_lead_time_days": _DEFAULT_LEAD_DAYS,
        },
    }


def _validate_response(r: dict, item_unit: str) -> dict:
    """Validate Gemini response shape. Raises ValueError on failure."""
    missing = REQUIRED_KEYS - r.keys()
    if missing:
        raise ValueError(f"Gemini response missing keys: {missing}")
    if r["urgency"] not in VALID_URGENCY:
        raise ValueError(f"Bad urgency: {r['urgency']}")
    if r["confidence"] not in VALID_CONFIDENCE:
        raise ValueError(f"Bad confidence: {r['confidence']}")
    if not isinstance(r["suggested_order_qty"], (int, float)) or r["suggested_order_qty"] <= 0:
        raise ValueError("suggested_order_qty must be a positive number")
    if r["unit"] != item_unit:
        r["unit"] = item_unit  # coerce rather than fail
    return r


def _call_gemini(context: dict) -> dict:
    """Call Gemini with structured-output request. Raises on failure."""
    if not _GEMINI_ENABLED or _MODEL is None:
        raise RuntimeError("Gemini is not configured")

    system_preamble = (
        "You are an agricultural inventory assistant for a university research farm.\n"
        "Given an inventory item's current stock, consumption history, and upcoming\n"
        "scheduled treatments, recommend a reorder quantity that:\n\n"
        "  1. Covers at least 30 days of projected demand after the lead time elapses.\n"
        "  2. Rounds up to a sensible purchase unit (nearest 10 for kg/L, nearest 5 for bags).\n"
        "  3. Accounts for accelerating or decelerating usage trends.\n"
        "  4. Does NOT exceed 3x the item's baseline reorder_quantity without explicit\n"
        "     high-urgency justification.\n\n"
        "Return ONLY a JSON object matching this schema:\n\n"
        "{\n"
        '  "suggested_order_qty": number,\n'
        '  "unit": string,\n'
        '  "urgency": "low" | "medium" | "high" | "critical",\n'
        '  "predicted_stockout_date": "YYYY-MM-DD",\n'
        '  "days_until_stockout": integer,\n'
        '  "rationale": string,\n'
        '  "assumed_lead_time_days": integer,\n'
        '  "estimated_cost_usd": number | null,\n'
        '  "confidence": "low" | "medium" | "high"\n'
        "}\n"
    )

    user_message = f"CONTEXT:\n{json.dumps(context, indent=2, default=str)}\n\nProduce the JSON recommendation now."

    prompt = f"{system_preamble}\n\n{user_message}"

    response = _MODEL.generate_content(prompt, request_options={"timeout": 10})

    # Check for safety or other finish reasons
    candidate = response.candidates[0] if response.candidates else None
    if candidate and candidate.finish_reason != 1:
        raise RuntimeError(f"Gemini finish_reason={candidate.finish_reason}")

    raw = response.text
    parsed = json.loads(raw)
    return parsed


def _rule_based_suggestion(item: InventoryItem, context: dict) -> dict:
    """Pure-Python fallback when Gemini is unavailable or fails."""
    burn = context["usage"]["avg_daily_burn"] or 0.1
    upcoming = context["upcoming_demand_30d"]["total_quantity"]
    lead_time = _DEFAULT_LEAD_DAYS

    projected_need = (burn * (30 + lead_time)) + upcoming - item.quantity_on_hand
    qty = max(projected_need, item.reorder_quantity or 0)

    step = 5 if item.unit and item.unit.lower() in ("bags", "bag") else 10
    qty = max(round(qty / step) * step, step)

    days_until = int(item.quantity_on_hand / burn) if burn > 0 else 999
    if days_until <= 3:
        urgency = "critical"
    elif days_until <= 7:
        urgency = "high"
    else:
        urgency = "medium"

    stockout_date = (date.today() + timedelta(days=days_until)).isoformat()
    estimated_cost = round(qty * item.unit_cost, 2) if item.unit_cost else None

    return {
        "suggested_order_qty": qty,
        "unit": item.unit,
        "urgency": urgency,
        "predicted_stockout_date": stockout_date,
        "days_until_stockout": days_until,
        "rationale": (
            f"Rule-based: current stock lasts ~{days_until} days at "
            f"{burn:.1f} {item.unit}/day. Covers 30 days post-{lead_time}-day lead time "
            f"plus {upcoming:.1f} {item.unit} of scheduled treatments."
        ),
        "assumed_lead_time_days": lead_time,
        "estimated_cost_usd": estimated_cost,
        "confidence": "low",
    }


def _cached_suggestion(item_id: int, session, ttl_hours: int = None) -> "Notification | None":
    """Return an existing pending Notification younger than TTL, or None."""
    ttl = ttl_hours if ttl_hours is not None else _CACHE_TTL_HOURS
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl)
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
    """Parse urgency from the embedded JSON comment in ai_message."""
    try:
        start = ai_message.find("<!--json\n")
        if start == -1:
            return "medium"
        end = ai_message.find("\n-->", start)
        if end == -1:
            return "medium"
        raw = ai_message[start + 9:end]
        data = json.loads(raw)
        return data.get("urgency", "medium")
    except Exception:
        return "medium"


def _persist_suggestion(item: InventoryItem, result: dict, session) -> "Notification":
    """Write a Notification row from a suggestion result dict."""
    # Clamp to safety cap
    max_qty = (item.reorder_quantity or 0) * _MAX_QTY_MULTIPLIER
    if max_qty > 0 and result["suggested_order_qty"] > max_qty:
        result["suggested_order_qty"] = max_qty
        result["rationale"] += f" (clamped to {_MAX_QTY_MULTIPLIER}× reorder quantity)"

    # Stockout date as datetime
    try:
        stockout_dt = datetime.strptime(result["predicted_stockout_date"], "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, KeyError):
        stockout_dt = None

    # Embed full JSON as an HTML comment for audit
    full_json = json.dumps(result, indent=2, default=str)
    rationale_only = result.get("rationale", "")
    ai_message = f"{rationale_only}\n\n<!--json\n{full_json}\n-->"

    n = Notification(
        farm_id=item.farm_id,
        inventory_item_id=item.id,
        status=NotificationStatus.pending,
        predicted_stockout=stockout_dt,
        days_until_stockout=result.get("days_until_stockout"),
        current_stock=item.quantity_on_hand,
        ai_message=ai_message,
        draft_order_qty=result.get("suggested_order_qty"),
        draft_order_sent=False,
        created_at=datetime.now(timezone.utc),
    )
    session.add(n)
    session.commit()
    # attach urgency for callers
    n._urgency = result.get("urgency", "medium")
    return n


# ── public API ─────────────────────────────────────────────────────────────────

def maybe_generate_suggestion(item: InventoryItem, session) -> "Notification | None":
    """Generate (or return cached) an AI reorder suggestion for a low-stock item.

    Returns None if item is not below threshold, or if an error prevents
    writing the suggestion (dashboard must never break because of this).
    """
    from models import InventoryItem as _II  # avoid circular at module level

    try:
        # Only generate for warning / critical items
        if item.reorder_threshold is None or item.quantity_on_hand > item.reorder_threshold:
            return None

        # Skip items with zero stock and no recent activity (likely retired)
        if item.quantity_on_hand == 0:
            from datetime import datetime as _dt
            cutoff90 = _dt.now(timezone.utc) - timedelta(days=90)
            recent = session.query(UsageLog).filter(
                UsageLog.inventory_item_id == item.id,
                UsageLog.log_date >= cutoff90,
            ).first()
            if not recent:
                return None

        # Cache check
        cached = _cached_suggestion(item.id, session)
        if cached:
            cached._urgency = _extract_urgency(cached.ai_message)
            return cached

        # Build context
        context = _build_context(item, session)

        # Try Gemini; fall back to rule-based
        result = None
        if _GEMINI_ENABLED:
            try:
                raw = _call_gemini(context)
                result = _validate_response(raw, item.unit)
            except Exception as exc:
                log.warning("reorder_ai: Gemini call failed for item %d (%s): %s",
                            item.id, item.name, exc)
                result = None

        if result is None:
            result = _rule_based_suggestion(item, context)

        return _persist_suggestion(item, result, session)

    except Exception as exc:
        log.error("reorder_ai: Unhandled error generating suggestion for item %d: %s",
                  item.id, exc)
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
    """Flip a pending suggestion to approved or dismissed."""
    n = session.get(Notification, nid)
    if not n or n.status != NotificationStatus.pending:
        return None
    n.status = (
        NotificationStatus.approved if action == "approve"
        else NotificationStatus.dismissed
    )
    n.resolved_at = datetime.now(timezone.utc)
    session.commit()
    return n
