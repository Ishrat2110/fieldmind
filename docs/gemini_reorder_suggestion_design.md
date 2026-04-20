# Gemini Reorder-Suggestion — Implementation Design

**Target repo:** `farm_manager_step1/` (FieldMind / FarmOS)
**Author:** Design spec
**Status:** Draft — ready for implementation
**Goal:** When an inventory item drops below its reorder threshold, call Google Gemini, get a context-aware reorder recommendation (quantity + rationale + urgency), persist it to the `notifications` table, and surface it to the user for approval.

This document is written so that each section maps to a concrete place in the code. Where a section says "add this function" or "add this route," the file name and approximate insertion point are called out.

---

## 1. Overview

The app already has the ingredients for this feature:

- `InventoryItem.reorder_threshold` and `InventoryItem.reorder_quantity` — baseline reorder rules
- `UsageLog` — burn-rate history
- `TreatmentPlan` — known upcoming demand
- `Notification` table — already defined in `models.py` with `predicted_stockout`, `days_until_stockout`, `current_stock`, `ai_message`, `draft_order_qty`, `draft_order_sent`, `status` (`pending / approved / dismissed`)
- `ai_engine.py` — already wired up to Gemini via `google-generativeai`

What's missing is the glue: a service module that evaluates each item's stock level, calls Gemini with the right context, parses a structured response, and writes a `Notification` row. Plus the UI hooks to show those suggestions and let the user approve them.

The design goal is **additive** — no changes to the existing data model, no migrations. Only new code in a new `reorder_ai.py` service module, plus new endpoints and small template additions.

---

## 2. Goals and non-goals

### Goals

1. Automatically detect when an item crosses `critical` or `warning` status (already computed by `stock_status()` in `server.py`).
2. Call Gemini with item-level context (current stock, 30-day burn rate, upcoming treatment demand, supplier, unit cost).
3. Receive a structured JSON response with: recommended order quantity, rationale, urgency, estimated cost, assumed lead time.
4. Store the suggestion in `notifications` so it persists across restarts and shows up in every UI surface.
5. Expose approve / dismiss actions. On approve, mark the `Notification` as resolved and optionally pre-fill a draft PO email (out of scope for v1 — just the flag flip).
6. Cache aggressively: don't call Gemini more than once per item per day.
7. Fall back gracefully when Gemini is down or the API key is missing — use a rule-based suggestion (`reorder_quantity` from the item row, stockout date from trailing average).

### Non-goals (v1)

- Automated purchase order submission
- Supplier-specific pricing lookups
- Multi-farm scoping (the rest of the codebase is single-farm today; match that)
- Vendor API integrations
- Email notifications (log to DB only; display in UI)

---

## 3. Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                     Trigger sources                           │
│                                                               │
│  (a) Dashboard render        (server.py /)                    │
│  (b) Log submission          (server.py /log, api.py /logs)   │
│  (c) Manual "refresh suggestions" button                      │
│  (d) Cron / scheduled task   (optional — 1x/day)              │
└───────────┬───────────────────────────────────────────────────┘
            │ for each low-stock item
            ▼
┌───────────────────────────────────────────────────────────────┐
│   reorder_ai.maybe_generate_suggestion(item, session)         │
│   ────────────────────────────────────────────────────────    │
│   1. Check cache: is there a pending Notification for this    │
│      item created in the last 24h? If yes → return it.        │
│   2. Build context (burn rate, upcoming demand, supplier).    │
│   3. Call Gemini with structured-output prompt.               │
│   4. Parse JSON response; validate schema.                    │
│   5. On failure → use rule_based_suggestion() fallback.       │
│   6. Persist Notification row.                                │
│   7. Return Notification.                                     │
└───────────┬───────────────────────────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────────────────────────┐
│   Surfaces                                                    │
│                                                               │
│   • Dashboard card  (templates/dashboard.html)                │
│   • Inventory page badges (templates/inventory.html)          │
│   • New /suggestions page (templates/suggestions.html)        │
│   • FastAPI /api/suggestions (api.py)                         │
└───────────────────────────────────────────────────────────────┘
```

Everything sits in **one new file**: `reorder_ai.py`. This keeps it decoupled from `ai_engine.py` (which is a standalone Streamlit app) and avoids touching the existing Streamlit flow.

---

## 4. New file: `reorder_ai.py`

Create this at the repo root next to `server.py`. It owns all AI logic for reorder suggestions.

### 4.1 Public API

Three functions are called from the rest of the app:

| Function | Caller | Purpose |
|---|---|---|
| `maybe_generate_suggestion(item, session) -> Notification \| None` | `server.py` dashboard, `server.py` /log POST, `api.py` /logs POST | Cached generation. Returns existing pending suggestion if one is fresh, otherwise generates a new one. |
| `get_active_suggestions(session, farm_id) -> list[Notification]` | `server.py` dashboard, `/suggestions` route, `api.py` /api/suggestions | All pending (not yet approved/dismissed) notifications for the farm. |
| `resolve_suggestion(notification_id, action, session) -> Notification` | `server.py` /suggestions/<id>/approve, `server.py` /suggestions/<id>/dismiss | Flip status, record `resolved_at`. |

### 4.2 Internal helpers

| Helper | Purpose |
|---|---|
| `_burn_rate(item, session, days=30) -> float` | Trailing-30-day avg daily consumption. Reuses the same SQL shape as `compute_sparklines` in `server.py` but returns a single number. |
| `_upcoming_demand(item, session, horizon_days=30) -> float` | Sum of `rate_per_ha * plot.area_ha` for all unapplied `TreatmentPlan` rows for this inventory item whose `planned_date` falls inside the horizon. |
| `_build_context(item, session) -> dict` | Assembles the dict that goes into the Gemini prompt. |
| `_call_gemini(context) -> dict` | Calls Gemini with structured-output request, returns parsed JSON. Raises on invalid response. |
| `_rule_based_suggestion(item, context) -> dict` | Pure-Python fallback. Used when Gemini fails or is disabled. |
| `_cached_suggestion(item_id, session, ttl_hours=24) -> Notification \| None` | Returns an existing pending notification younger than TTL. |

### 4.3 Module-level setup

```python
import os, json, logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
import google.generativeai as genai
from models import InventoryItem, UsageLog, TreatmentPlan, Plot, Notification, NotificationStatus

log = logging.getLogger("reorder_ai")

_GEMINI_KEY = os.getenv("GEMINI_API_KEY")
_GEMINI_ENABLED = bool(_GEMINI_KEY)
if _GEMINI_ENABLED:
    genai.configure(api_key=_GEMINI_KEY)
    _MODEL = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.3,
        },
    )
else:
    _MODEL = None
    log.warning("GEMINI_API_KEY not set — reorder suggester will use rule-based fallback only.")

_CACHE_TTL_HOURS = 24
```

---

## 5. Trigger logic — when to call Gemini

### 5.1 Stock status thresholds

Reuse the existing `stock_status()` in `server.py`:

- `critical` → `quantity_on_hand <= reorder_threshold * 0.5`
- `warning` → `quantity_on_hand <= reorder_threshold`
- `ok` → above threshold

Rule: **generate a suggestion for any item whose status is `critical` or `warning`**.

### 5.2 Call sites

Add exactly three call sites (keep them minimal — don't make Gemini a hot path):

1. **Dashboard render** (`server.py::dashboard()`)
   After `enrich_inventory(...)` runs, iterate over `inv` and call `maybe_generate_suggestion(item, s)` for every `critical`/`warning` item. The `_cached_suggestion` check guarantees at most one Gemini call per item per day.

2. **Usage log submission** (`server.py::log_usage` POST branch, right after `s.commit()`)
   After the log is written and stock is decremented, re-check `stock_status(item)`. If it's now `critical` or `warning`, call `maybe_generate_suggestion(item, s)`. This catches the exact moment an item crosses the threshold.

3. **Manual refresh** (`server.py::/suggestions/refresh` — new POST route)
   For users who want to force a fresh call. Invalidates the 24h cache for items they choose.

Do **not** call from the FastAPI `/api/logs` endpoint in v1 unless you're unifying the two databases (see the separate remediation doc). Otherwise, the suggestion gets written to one DB and the user reads from the other.

### 5.3 Cache behavior

`_cached_suggestion(item_id, session, ttl_hours=24)`:

```
SELECT * FROM notifications
WHERE inventory_item_id = :item_id
  AND status = 'pending'
  AND created_at >= :now - 24h
ORDER BY created_at DESC
LIMIT 1
```

If a row exists → return it. If not → generate new.

This means:
- A user who approves a suggestion, then sees the item dip again, gets a new suggestion (since the old one is no longer `pending`).
- A user who dismisses a suggestion gets no new one for 24h (honor their dismissal — prevents nagging).
- A refreshed dashboard doesn't cost extra Gemini calls.

---

## 6. Context sent to Gemini

`_build_context(item, session)` returns a dict that's both sent to Gemini *and* stored for audit / reproducibility. The schema:

```python
{
  "item": {
    "id": 5,
    "name": "Roundup PowerMAX",
    "category": "herbicide",
    "unit": "L",
    "quantity_on_hand": 72.0,
    "reorder_threshold": 80.0,
    "reorder_quantity": 200.0,   # baseline, may differ from AI suggestion
    "unit_cost": 8.40,
    "supplier": "Bayer Crop Science"
  },
  "usage": {
    "avg_daily_burn": 4.3,              # L/day over last 30 days
    "days_of_data": 30,
    "trend_7d_vs_30d": 1.12,            # >1 means accelerating
    "last_log_date": "2026-04-15",
    "total_30d": 129.0
  },
  "upcoming_demand_30d": {
    "total_quantity": 110.0,
    "unit": "L",
    "treatments": [
      {"plot_code": "A-03", "rate_per_ha": 2.5, "area_ha": 2.5, "planned_date": "2026-04-22"},
      {"plot_code": "A-05", "rate_per_ha": 2.5, "area_ha": 2.5, "planned_date": "2026-04-24"}
    ]
  },
  "stockout_naive": {
    "days_until": 17,     # quantity_on_hand / avg_daily_burn
    "predicted_date": "2026-05-04"
  },
  "constraints": {
    "typical_lead_time_days": 7,   # default; override per-supplier later
    "bulk_discount_threshold": 250 # optional hint; omit if unknown
  }
}
```

Implementation notes:

- `trend_7d_vs_30d` = (7-day avg daily burn) / (30-day avg daily burn). Hint Gemini about acceleration.
- `upcoming_demand_30d.treatments` should cap at 5 items (trim oldest if more) to keep prompts small.
- If there's <7 days of usage data, set `days_of_data` accordingly and let the model know confidence is low.

---

## 7. Prompt design

Use Gemini's JSON mode (`response_mime_type: "application/json"`) plus an explicit schema in the prompt. No chain-of-thought; we want deterministic, cheap output.

### 7.1 System-style preamble (prepended to every call)

```
You are an agricultural inventory assistant for a university research farm.
Given an inventory item's current stock, consumption history, and upcoming
scheduled treatments, recommend a reorder quantity that:

  1. Covers at least 30 days of projected demand after the lead time elapses.
  2. Rounds up to a sensible purchase unit (nearest 10 for kg/L, nearest 5 for bags).
  3. Accounts for accelerating or decelerating usage trends.
  4. Does NOT exceed 3x the item's baseline `reorder_quantity` without
     explicit high-urgency justification.

Return ONLY a JSON object matching this schema:

{
  "suggested_order_qty": number,       // in the item's unit
  "unit": string,                      // echo the item's unit
  "urgency": "low" | "medium" | "high" | "critical",
  "predicted_stockout_date": "YYYY-MM-DD",
  "days_until_stockout": integer,
  "rationale": string,                 // 1-3 sentences, plain English
  "assumed_lead_time_days": integer,
  "estimated_cost_usd": number | null, // qty * unit_cost if unit_cost known
  "confidence": "low" | "medium" | "high"
}
```

### 7.2 User message

Serialize the context dict as JSON under the heading `CONTEXT:` and append:

```
CONTEXT:
{...context JSON...}

Produce the JSON recommendation now.
```

### 7.3 Why these choices

- **JSON mode** — eliminates regex parsing; SDK gives you a dict directly.
- **Temperature 0.3** — want mild variation but mostly deterministic.
- **No streaming** — the response is tiny (<400 tokens). Streaming adds complexity with no UX benefit.
- **Single turn** — no follow-up questions from the model; the user is not in the loop during generation.

---

## 8. Response schema & validation

After `_call_gemini(context)` returns, validate before trusting:

```python
REQUIRED_KEYS = {
    "suggested_order_qty", "unit", "urgency",
    "predicted_stockout_date", "days_until_stockout",
    "rationale", "assumed_lead_time_days",
    "estimated_cost_usd", "confidence",
}

VALID_URGENCY    = {"low", "medium", "high", "critical"}
VALID_CONFIDENCE = {"low", "medium", "high"}

def _validate_response(r: dict, item_unit: str) -> dict:
    missing = REQUIRED_KEYS - r.keys()
    if missing:
        raise ValueError(f"Gemini response missing keys: {missing}")
    if r["urgency"] not in VALID_URGENCY:
        raise ValueError(f"Bad urgency: {r['urgency']}")
    if r["confidence"] not in VALID_CONFIDENCE:
        raise ValueError(f"Bad confidence: {r['confidence']}")
    if not isinstance(r["suggested_order_qty"], (int, float)) or r["suggested_order_qty"] <= 0:
        raise ValueError("suggested_order_qty must be positive")
    if r["unit"] != item_unit:
        # Gemini echoed the wrong unit; coerce rather than fail.
        r["unit"] = item_unit
    # Sanity cap at 5x reorder_quantity to prevent runaway prompts.
    # (Handled in maybe_generate_suggestion, not here.)
    return r
```

If validation fails → log the raw response, fall through to `_rule_based_suggestion()`.

---

## 9. Rule-based fallback

`_rule_based_suggestion(item, context)` returns the same shape as a Gemini response but with no API call. Used when:

- `GEMINI_API_KEY` is missing
- Gemini call raises (network, quota, safety block)
- Gemini response fails validation

Logic:

```python
def _rule_based_suggestion(item, context):
    burn = context["usage"]["avg_daily_burn"] or 0.1
    upcoming = context["upcoming_demand_30d"]["total_quantity"]
    lead_time = 7

    # cover 30 days of demand after lead time + upcoming treatments - current stock
    projected_need = (burn * (30 + lead_time)) + upcoming - item.quantity_on_hand
    qty = max(projected_need, item.reorder_quantity or 0)

    # round to nearest 10 for kg/L, nearest 5 for bags
    step = 5 if item.unit == "bags" else 10
    qty = round(qty / step) * step

    days_until = int(item.quantity_on_hand / burn) if burn > 0 else 999
    urgency = "critical" if days_until <= 3 else "high" if days_until <= 7 else "medium"

    return {
        "suggested_order_qty": qty,
        "unit": item.unit,
        "urgency": urgency,
        "predicted_stockout_date": (datetime.now(timezone.utc) + timedelta(days=days_until)).date().isoformat(),
        "days_until_stockout": days_until,
        "rationale": (
            f"Rule-based: current stock lasts ~{days_until} days at "
            f"{burn:.1f} {item.unit}/day. Covers 30 days post–{lead_time}-day lead time "
            f"plus {upcoming:.1f} {item.unit} of scheduled treatments."
        ),
        "assumed_lead_time_days": lead_time,
        "estimated_cost_usd": round(qty * item.unit_cost, 2) if item.unit_cost else None,
        "confidence": "low",
    }
```

The rationale explicitly says "Rule-based" so the UI can show that it's a fallback.

---

## 10. Persistence — writing to `notifications`

The `Notification` table already has the right fields. Map Gemini output → row:

| Notification column | Source |
|---|---|
| `farm_id` | `item.farm_id` |
| `inventory_item_id` | `item.id` |
| `status` | `NotificationStatus.pending` |
| `predicted_stockout` | parse `predicted_stockout_date` to datetime |
| `days_until_stockout` | direct |
| `current_stock` | `item.quantity_on_hand` at generation time |
| `ai_message` | the `rationale` field |
| `draft_order_qty` | `suggested_order_qty` |
| `draft_order_sent` | `False` |
| `created_at` | `datetime.now(timezone.utc)` |
| `resolved_at` | `None` |

**Audit gap to fix:** the current `Notification` model doesn't have a column for the raw AI response. Options:

- (a) Stuff the full JSON into `ai_message` (concatenate rationale + structured fields). Ugly but no migration.
- (b) Add a new `raw_response` Text column. Requires a schema change.
- (c) Extend `ai_message` formatting to include a fenced JSON block.

Recommend **(c)** for v1 — append `\n\n<!--json\n{...}\n-->` to `ai_message`. The UI strips the comment; the data is still there for debugging.

---

## 11. Approval flow

Add three routes to `server.py`:

### 11.1 List view — `GET /suggestions`

```python
@app.route("/suggestions")
def suggestions():
    s = db()
    ctx = nav_context(s)
    from reorder_ai import get_active_suggestions
    active = get_active_suggestions(s, ctx["farm"].id)
    # also show recently resolved (last 7 days) for context
    resolved = (s.query(Notification)
                .filter(Notification.status != NotificationStatus.pending,
                        Notification.resolved_at >= datetime.now(timezone.utc) - timedelta(days=7))
                .order_by(Notification.resolved_at.desc())
                .limit(20).all())
    return render_template("suggestions.html",
                           page="suggestions",
                           active=active, resolved=resolved, **ctx)
```

### 11.2 Approve — `POST /suggestions/<int:nid>/approve`

```python
@app.route("/suggestions/<int:nid>/approve", methods=["POST"])
def suggestion_approve(nid):
    s = db()
    from reorder_ai import resolve_suggestion
    resolve_suggestion(nid, "approve", s)
    flash("Reorder suggestion approved.", "success")
    return redirect(request.referrer or url_for("suggestions"))
```

### 11.3 Dismiss — `POST /suggestions/<int:nid>/dismiss`

Same shape with `"dismiss"` action.

`resolve_suggestion()` simply:

```python
def resolve_suggestion(nid, action, session):
    n = session.query(Notification).get(nid)
    if not n or n.status != NotificationStatus.pending:
        return None
    n.status = NotificationStatus.approved if action == "approve" else NotificationStatus.dismissed
    n.resolved_at = datetime.now(timezone.utc)
    session.commit()
    return n
```

Both routes require role check — add a `require_role("admin", "manager")` decorator before merging (viewers can see suggestions but can't act on them).

### 11.4 Refresh — `POST /suggestions/refresh`

Invalidates pending suggestions older than 1h (mark them dismissed) and regenerates for every low-stock item. Guard rails:

- Only admin/manager can refresh
- Rate-limit to 1 call per 5 minutes per user (sliding window in memory is fine for v1)

---

## 12. FastAPI endpoint

Add to `api.py`:

```python
@app.get("/api/suggestions")
def get_suggestions(
    current_user: SessionUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from reorder_ai import get_active_suggestions
    notifications = get_active_suggestions(db, FARM_ID)
    return [
        {
            "id": n.id,
            "item_id": n.inventory_item_id,
            "item_name": n.inventory_item.name if n.inventory_item else None,
            "current_stock": n.current_stock,
            "days_until_stockout": n.days_until_stockout,
            "predicted_stockout": n.predicted_stockout.isoformat() if n.predicted_stockout else None,
            "draft_order_qty": n.draft_order_qty,
            "ai_message": n.ai_message,
            "status": n.status.value,
            "created_at": n.created_at.isoformat(),
        }
        for n in notifications
    ]

@app.post("/api/suggestions/{nid}/approve", status_code=200)
def approve_suggestion(
    nid: int,
    current_user: SessionUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from reorder_ai import resolve_suggestion
    n = resolve_suggestion(nid, "approve", db)
    if not n:
        raise HTTPException(404, "Suggestion not found or already resolved")
    return {"status": "approved", "id": nid}
```

Mirror for `/api/suggestions/{nid}/dismiss`.

---

## 13. UI integration

### 13.1 Dashboard (`templates/dashboard.html`)

Add a new card at the top of the right column, above "Today's Logs":

```jinja
{% if suggestions %}
<div class="card suggestions-card">
  <div class="card-header">
    <h3>AI Reorder Suggestions</h3>
    <span class="badge">{{ suggestions|length }}</span>
  </div>
  {% for sug in suggestions[:3] %}
    <div class="suggestion-row urgency-{{ sug._urgency }}">
      <div class="suggestion-main">
        <strong>{{ sug.inventory_item.name }}</strong>
        <span class="muted">→ order {{ sug.draft_order_qty }} {{ sug.inventory_item.unit }}</span>
      </div>
      <div class="suggestion-rationale muted">{{ sug.ai_message }}</div>
      <div class="suggestion-actions">
        <form method="POST" action="{{ url_for('suggestion_approve', nid=sug.id) }}" style="display:inline">
          <button type="submit" class="btn-primary-sm">Approve</button>
        </form>
        <form method="POST" action="{{ url_for('suggestion_dismiss', nid=sug.id) }}" style="display:inline">
          <button type="submit" class="btn-secondary-sm">Dismiss</button>
        </form>
      </div>
    </div>
  {% endfor %}
  {% if suggestions|length > 3 %}
    <a href="{{ url_for('suggestions') }}" class="muted">View all {{ suggestions|length }} →</a>
  {% endif %}
</div>
{% endif %}
```

The `_urgency` attribute is set in `server.py::dashboard()`:

```python
for sug in suggestions:
    # parse urgency from embedded JSON or default to "medium"
    sug._urgency = _extract_urgency(sug.ai_message)  # helper in reorder_ai
```

### 13.2 Inventory page (`templates/inventory.html`)

Add a small AI badge next to each item that has a pending suggestion:

```jinja
{% if item._has_suggestion %}
  <span class="ai-badge" title="AI suggests reordering {{ item._suggested_qty }} {{ item.unit }}">
    🤖 Reorder {{ item._suggested_qty }} {{ item.unit }}
  </span>
{% endif %}
```

Populate `_has_suggestion` and `_suggested_qty` in `enrich_inventory()` by joining `notifications`.

### 13.3 New dedicated page (`templates/suggestions.html`)

Full list with both pending and recently resolved. Layout:

- Header: "AI Reorder Suggestions"
- "Refresh" button (POST to `/suggestions/refresh`)
- Pending section (cards with Approve/Dismiss buttons)
- Recently Resolved section (read-only, with who/when)

Add "Suggestions" to the sidebar nav in `templates/base.html`, between "Inventory" and "Treatments."

### 13.4 Navigation counter

In `nav_context()` (server.py), add:

```python
suggestion_count = s.query(Notification).filter_by(status=NotificationStatus.pending).count()
```

Then `{{ suggestion_count }}` badge next to the sidebar "Suggestions" link.

---

## 14. Configuration

### 14.1 Environment variables

Add to `.env.example` (and document in README):

```
GEMINI_API_KEY=...
REORDER_AI_CACHE_HOURS=24          # override if you want
REORDER_AI_DEFAULT_LEAD_DAYS=7     # used by rule-based fallback
REORDER_AI_MAX_QTY_MULTIPLIER=3    # safety cap on Gemini output
```

### 14.2 Rate limits to respect

Google Gemini Flash free tier (as of 2025): 15 RPM, 1M TPM. With 7 inventory items and a 24h cache, worst case ~7 calls per dashboard load, once per day per item. Nowhere near limits.

### 14.3 Secrets

**Never hardcode the API key.** The current `.env` in your repo already contains a working key — **rotate that key before publishing any fix**, since it's been shared. Generate a fresh one at https://aistudio.google.com/apikey.

---

## 15. Error handling

| Failure mode | Handling |
|---|---|
| `GEMINI_API_KEY` missing | Skip Gemini entirely, use rule-based fallback. Log once at startup. |
| Network timeout | `try/except` in `_call_gemini`, fall back to rule-based. Timeout 10s. |
| Gemini returns non-JSON | `json.JSONDecodeError` → fallback. |
| Gemini returns schema-invalid JSON | `_validate_response` raises → fallback. |
| Gemini returns `suggested_order_qty > 5 * reorder_quantity` | Clamp to `5 * reorder_quantity`, append a note to rationale. |
| Gemini content-safety block | `response.candidates[0].finish_reason != 1` → fallback. |
| DB write fails | Rollback, log, return `None`. Do NOT surface Python errors to the user — just don't show a suggestion that render. |

The user-facing rule: **the dashboard never breaks because the AI is down.** If suggestions are unavailable, the card silently hides.

---

## 16. Cost controls

- **Cache TTL: 24h** — hard-coded default. Override with `REORDER_AI_CACHE_HOURS`.
- **Model: `gemini-1.5-flash`** — cheapest model that reliably does JSON mode.
- **Batch when possible.** If you later want to generate for multiple items at once, make one Gemini call with a list of items instead of N calls. Not needed for v1 (7 items is trivial).
- **Don't trigger on read-only pages you don't need.** Only dashboard, `/log` POST, and manual refresh.
- **Skip generation for inactive items** — items where `quantity_on_hand == 0` and no logs in 90 days are likely retired; don't waste calls on them.

Back-of-envelope: 7 items × 1 call/day × 30 days = 210 calls/month. At Flash pricing (~$0.075 per 1M input tokens, ~$0.30 per 1M output tokens), with ~800 tokens in and ~300 tokens out per call, monthly cost is roughly **$0.01**. Free tier covers this outright.

---

## 17. Testing

Add a new file: `tests/test_reorder_ai.py`. Structure:

### 17.1 Fixtures

Reuse `seeded_db` from `test_api.py`. Extend to include:
- 30 days of synthetic `UsageLog` rows for one item
- One pending `TreatmentPlan` 10 days out

### 17.2 Unit tests (no network)

Monkeypatch `_call_gemini` to return a canned dict.

- `test_maybe_generate_writes_notification`
- `test_maybe_generate_uses_cache_within_ttl`
- `test_maybe_generate_regenerates_after_ttl`
- `test_dismissed_suggestion_does_not_regenerate` (within TTL)
- `test_approved_suggestion_allows_new_one` (since it's no longer pending)
- `test_validate_response_rejects_bad_urgency`
- `test_validate_response_coerces_bad_unit`
- `test_rule_based_fallback_covers_30_days`
- `test_fallback_fires_when_gemini_raises`
- `test_clamp_at_5x_reorder_quantity`

### 17.3 Integration test (mocked Gemini)

- `test_dashboard_renders_suggestions` — fake a critical item, assert the card HTML shows up.
- `test_approve_endpoint_flips_status`
- `test_dismiss_endpoint_flips_status`
- `test_refresh_endpoint_invalidates_cache`
- `test_viewer_cannot_approve` (403)

### 17.4 Contract test against real Gemini (optional, gated)

```python
@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="Needs real key")
def test_gemini_real_roundtrip():
    ...
```

Run it manually before a release; don't put it in CI.

Target coverage for `reorder_ai.py`: **90%+**.

---

## 18. Security

- **Never log the raw Gemini API key.** The module-level setup at the top of `reorder_ai.py` should only log "enabled" / "disabled."
- **Role gate the mutation routes.** `/suggestions/<id>/approve`, `/dismiss`, `/refresh` must be admin/manager only. This depends on you fixing the missing role check (see the separate remediation doc — item #5).
- **CSRF on POST routes.** The approve/dismiss buttons are forms; they need CSRF tokens if you add CSRF middleware.
- **Don't let Gemini dictate code paths.** Every value from the response is treated as data, not code. No `eval`, no format strings with user-controlled templates, no shell passthrough.
- **Input size cap.** Truncate `upcoming_demand_30d.treatments` to 5 rows max before sending. A malicious or broken treatment-plan seed shouldn't let someone blow up the prompt.
- **Output size cap.** Validate `suggested_order_qty` is a number and <= 5x reorder_quantity.
- **Rate limit `/suggestions/refresh`.** Without a limit, a script can force 7 Gemini calls per click. In-memory dict `{user_id: last_refresh_ts}` is enough for v1.

---

## 19. Where this plugs into the existing fixes

This feature depends on two things from the broader remediation plan:

1. **Single database** — today `server.py` (via `database.py`) and `api.py` point to different SQLite files. A `Notification` written through the Flask flow is invisible to the FastAPI flow. Unify the `DATABASE_URL` before shipping the FastAPI endpoints above.
2. **Role enforcement** — the approve/dismiss endpoints are dangerous if viewers can hit them. Put a `require_role` decorator in place first.

If you haven't fixed those yet, ship v1 as **Flask-only** (skip the FastAPI endpoints in section 12) and **admin-only** (hard-code the role check inline).

---

## 20. Implementation checklist (in order)

Treat this as a PR-by-PR sequence.

### PR 1 — Scaffolding

- [ ] Create `reorder_ai.py` with module setup (Gemini config, logging)
- [ ] Implement `_burn_rate`, `_upcoming_demand`, `_build_context`
- [ ] Implement `_rule_based_suggestion` + tests
- [ ] Implement `_cached_suggestion` + tests
- [ ] Implement `maybe_generate_suggestion` using ONLY the rule-based path (no Gemini yet)
- [ ] Implement `get_active_suggestions`, `resolve_suggestion`
- [ ] Write tests (section 17.2) — should pass without any network

### PR 2 — Gemini integration

- [ ] Implement `_call_gemini` with JSON mode
- [ ] Implement `_validate_response`
- [ ] Wire `_call_gemini` into `maybe_generate_suggestion` with fallback
- [ ] Add tests with monkeypatched `_call_gemini`
- [ ] Add one gated real-API contract test

### PR 3 — Flask UI

- [ ] Add `/suggestions`, `/suggestions/<id>/approve`, `/suggestions/<id>/dismiss`, `/suggestions/refresh` routes to `server.py`
- [ ] Call `maybe_generate_suggestion` from `dashboard()` for low-stock items
- [ ] Call `maybe_generate_suggestion` from `log_usage()` POST after commit
- [ ] Create `templates/suggestions.html`
- [ ] Add suggestion card to `templates/dashboard.html`
- [ ] Add AI badge to `templates/inventory.html`
- [ ] Add "Suggestions" nav link + count badge to `templates/base.html`
- [ ] Add route-level role checks (admin/manager) on approve/dismiss/refresh

### PR 4 — FastAPI parity (optional, after DB unification)

- [ ] Add `/api/suggestions` GET
- [ ] Add `/api/suggestions/{id}/approve` POST
- [ ] Add `/api/suggestions/{id}/dismiss` POST
- [ ] Tests in `test_api.py`

### PR 5 — Polish

- [ ] README updates (new env vars, feature description)
- [ ] `.env.example` updated
- [ ] Rate-limit `/suggestions/refresh`
- [ ] Urgency color scheme in CSS
- [ ] Empty-state copy ("No suggestions right now — everything is stocked.")

### PR 6 — Rotate the leaked key

- [ ] Generate fresh Gemini key
- [ ] Update `.env` locally
- [ ] Verify `.env` is in `.gitignore` (it already is)
- [ ] Audit `git log -p` for accidental commits of the old key and purge with `git filter-repo` if found

---

## 21. Future enhancements (explicitly out of scope for v1)

- Per-supplier lead times stored in a new `suppliers` table
- Draft email generation to the supplier (prefill To/Subject/Body) — `draft_order_sent` boolean is already on the model
- Weather-adjusted demand (rain delays herbicide use)
- Multi-item bundled orders ("these three arrive together — optimize shipping")
- Price-forecast integration (sunk cost if you order late)
- Slack / Teams notification on `critical` urgency
- Unit-cost trend tracking (Notification remembers unit_cost at time of suggestion)
- "Explain this suggestion" button that shows the full context JSON for debugging

---

## 22. Quick reference — files touched

| File | Change |
|---|---|
| `reorder_ai.py` | **NEW** — all AI logic |
| `server.py` | +4 routes, ~30 lines in `dashboard()` and `log_usage()` |
| `api.py` | +3 endpoints, ~50 lines (optional, PR 4) |
| `templates/base.html` | +1 nav link with badge |
| `templates/dashboard.html` | +1 card (~25 lines) |
| `templates/inventory.html` | +1 badge per row (~5 lines) |
| `templates/suggestions.html` | **NEW** (~80 lines) |
| `tests/test_reorder_ai.py` | **NEW** (~200 lines) |
| `.env.example` | +3 vars |
| `README.md` | New feature section |
| **No change to** `models.py`, `database.py`, or migrations | — |

End of document.
