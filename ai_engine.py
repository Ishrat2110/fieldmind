"""
ai_engine.py
------------
Step 3 — AI Estimation Layer
AI-Powered Research Farm Manager · UNL

Uses Google Gemini to:
  1. Estimate daily consumption rates per inventory item
  2. Predict stockout dates from farm profile + usage history
  3. Generate plain-English alerts with full reasoning
  4. Learn from farmer corrections over time

Run as a Streamlit page:
    streamlit run ai_engine.py
"""

import streamlit as st
from google import genai
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from database import get_session
from models import (
    Farm, InventoryItem, UsageLog, Plot, Field,
    CropVariety, TreatmentPlan, Equipment, Notification,
    NotificationStatus
)

load_dotenv()

# ── CONFIG ──────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL   = "gemini-2.0-flash"
if GEMINI_API_KEY:
    _client = genai.Client(api_key=GEMINI_API_KEY)
    model   = _client

st.set_page_config(
    page_title="AI Engine — UNL Farm",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
  * { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif !important; }
  .stApp { background: #f8faf9; }
  .stButton > button { background: #1F6B3A; color: white; border: none; border-radius: 6px; font-weight: 600; }
  .stButton > button:hover { background: #174f2b; }
  .topbar {
    background: linear-gradient(135deg, #1F6B3A, #0f3d20);
    color: white; padding: 16px 24px; border-radius: 10px;
    margin-bottom: 20px;
    display: flex; justify-content: space-between; align-items: center;
  }
  .topbar-title { font-size: 1.3rem; font-weight: 800; }
  .topbar-sub   { font-size: 0.82rem; opacity: 0.7; margin-top: 2px; }
  .section-header {
    font-size: 1.05rem; font-weight: 700; color: #1F6B3A;
    border-bottom: 2px solid #1F6B3A;
    padding-bottom: 5px; margin: 20px 0 14px 0;
  }
  .ai-card {
    background: white; border: 1px solid #e0ece4;
    border-radius: 10px; padding: 20px; margin-bottom: 14px;
  }
  .ai-card-critical {
    background: #fff8f8; border: 1px solid #f5c6c6;
    border-left: 4px solid #D00000;
    border-radius: 10px; padding: 20px; margin-bottom: 14px;
  }
  .ai-card-warning {
    background: #fffbf0; border: 1px solid #f9e4b0;
    border-left: 4px solid #e67e22;
    border-radius: 10px; padding: 20px; margin-bottom: 14px;
  }
  .ai-card-ok {
    background: #f0fff4; border: 1px solid #b7e4c7;
    border-left: 4px solid #1F6B3A;
    border-radius: 10px; padding: 20px; margin-bottom: 14px;
  }
  .ai-message {
    font-size: 0.95rem; line-height: 1.7; color: #1a1a1a;
    margin: 10px 0;
  }
  .ai-label {
    font-size: 0.7rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: #888; margin-bottom: 6px;
  }
  .confidence-bar {
    background: #e8f0eb; border-radius: 4px; height: 6px; margin: 4px 0 10px 0;
  }
  .confidence-fill {
    height: 6px; border-radius: 4px; background: #1F6B3A;
  }
  .correction-box {
    background: #f8faf9; border: 1px dashed #b7d4c0;
    border-radius: 8px; padding: 14px; margin-top: 12px;
  }
  .thinking-box {
    background: #f0f4ff; border: 1px solid #c7d7f5;
    border-left: 3px solid #4f6ef7;
    border-radius: 8px; padding: 14px; margin: 10px 0;
    font-size: 0.82rem; color: #3a4a7a; line-height: 1.6;
  }
  .stat-pill {
    display: inline-block; background: #e8f5ee; color: #1F6B3A;
    padding: 3px 10px; border-radius: 12px;
    font-size: 0.75rem; font-weight: 600; margin: 2px;
  }
</style>
""", unsafe_allow_html=True)

# ── SESSION STATE ────────────────────────────
if "ai_results" not in st.session_state:
    st.session_state.ai_results = []
if "corrections" not in st.session_state:
    st.session_state.corrections = {}

session = get_session()

# ── HELPERS ─────────────────────────────────
def get_farm_context():
    """Build a structured farm context dict for the AI prompt."""
    farm    = session.query(Farm).first()
    plots   = session.query(Plot).all()
    items   = session.query(InventoryItem).filter_by(farm_id=farm.id).all()
    equip   = session.query(Equipment).filter_by(farm_id=farm.id).all()

    # Summarize plots by species
    species_counts = {}
    for p in plots:
        sp = p.variety.species.common_name if p.variety and p.variety.species else "Unknown"
        species_counts[sp] = species_counts.get(sp, 0) + 1

    # Compute usage stats per item (last 30 days)
    usage_stats = {}
    cutoff = datetime.now() - timedelta(days=30)
    for item in items:
        logs = (session.query(UsageLog)
                .filter(UsageLog.inventory_item_id == item.id)
                .filter(UsageLog.log_date >= cutoff)
                .all())
        total = sum(l.quantity_used for l in logs)
        days  = len(set(l.log_date.date() for l in logs if l.log_date)) or 1
        usage_stats[item.id] = {
            "total_30d": round(total, 2),
            "avg_per_active_day": round(total / days, 2),
            "log_count": len(logs),
            "corrections": st.session_state.corrections.get(item.id, [])
        }

    # Upcoming treatments (next 30 days)
    cutoff_future = datetime.now() + timedelta(days=30)
    treatments = (session.query(TreatmentPlan)
                  .filter(TreatmentPlan.applied == False)
                  .filter(TreatmentPlan.planned_date <= cutoff_future)
                  .all())
    treatment_summary = []
    for t in treatments:
        treatment_summary.append({
            "plot": t.plot.plot_code if t.plot else "?",
            "item": t.inventory_item.name if t.inventory_item else "?",
            "item_id": t.inventory_item_id,
            "rate_per_ha": t.rate_per_ha,
            "plot_area_ha": t.plot.area_ha if t.plot else 0,
            "stage": t.growth_stage.stage_code if t.growth_stage else "?",
            "planned_date": t.planned_date.strftime("%Y-%m-%d") if t.planned_date else "?"
        })

    return {
        "farm_name": farm.name,
        "total_area_ha": farm.total_area_ha,
        "location": farm.location,
        "plots": len(plots),
        "species_breakdown": species_counts,
        "inventory": [
            {
                "id": item.id,
                "name": item.name,
                "category": item.category,
                "unit": item.unit,
                "quantity_on_hand": item.quantity_on_hand,
                "reorder_threshold": item.reorder_threshold,
                "reorder_quantity": item.reorder_quantity,
                "usage_30d": usage_stats.get(item.id, {})
            }
            for item in items
        ],
        "equipment": [
            {"name": e.name, "type": e.equipment_type,
             "fuel_rate_l_per_hr": e.fuel_rate_l_per_hr}
            for e in equip
        ],
        "upcoming_treatments_30d": treatment_summary
    }


def build_prompt(farm_ctx):
    """Build the Gemini prompt for inventory analysis."""
    corrections_text = ""
    for item_id, corrs in st.session_state.corrections.items():
        if corrs:
            item_name = next((i["name"] for i in farm_ctx["inventory"] if i["id"] == item_id), str(item_id))
            corrections_text += f"\n- {item_name}: farmer corrected AI estimate. Actual rates: {corrs}"

    return f"""
You are an AI assistant for a university agricultural research farm. Your job is to analyze farm inventory data and predict when supplies will run low, then generate clear, actionable alerts.

FARM CONTEXT:
{json.dumps(farm_ctx, indent=2)}

FARMER CORRECTIONS (use these to calibrate your estimates):
{corrections_text if corrections_text else "No corrections yet — use agronomic baselines."}

TASK:
Analyze each inventory item and return a JSON array. For each item provide:
1. A consumption rate estimate (per day) based on usage history OR agronomic baselines if history is sparse
2. Predicted days until stockout
3. Predicted days until reorder threshold is hit
4. A confidence level (0-100) based on how much real data exists
5. A plain-English alert message (2-3 sentences) that a farm manager would find useful — mention growth stages, upcoming treatments, and specific quantities
6. A severity: "critical" (< 7 days to reorder), "warning" (7-21 days), or "ok" (> 21 days)
7. A suggested reorder quantity
8. Your reasoning (1-2 sentences explaining how you estimated the rate)

Consider:
- Upcoming scheduled treatments will spike consumption on specific dates
- Equipment fuel consumption at stated rates per hour
- Research farm context: multiple varieties, replicated plots
- Seasonal patterns for Nebraska (planting ~May, harvest ~Oct)

Return ONLY valid JSON — no markdown, no explanation outside the JSON:
[
  {{
    "item_id": 1,
    "item_name": "Item name",
    "estimated_rate_per_day": 12.5,
    "days_to_stockout": 45,
    "days_to_reorder": 30,
    "confidence": 75,
    "severity": "warning",
    "alert_message": "Plain English message here.",
    "suggested_reorder_qty": 200,
    "reasoning": "How I estimated this rate."
  }}
]
"""


def run_ai_analysis(farm_ctx):
    """Call Gemini and parse the response."""
    prompt = build_prompt(farm_ctx)
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()
        return json.loads(text)
    except json.JSONDecodeError as e:
        st.error(f"AI returned invalid JSON: {e}")
        return []
    except Exception as e:
        st.error(f"Gemini API error: {e}")
        return []


def save_notification(result, farm_id):
    """Persist AI alert to the notifications table."""
    stockout_date = datetime.now() + timedelta(days=result.get("days_to_stockout", 999))
    existing = (session.query(Notification)
                .filter_by(inventory_item_id=result["item_id"],
                           status=NotificationStatus.pending)
                .first())
    if existing:
        existing.ai_message          = result["alert_message"]
        existing.predicted_stockout  = stockout_date
        existing.days_until_stockout = result.get("days_to_stockout")
        existing.draft_order_qty     = result.get("suggested_reorder_qty")
    else:
        notif = Notification(
            farm_id=farm_id,
            inventory_item_id=result["item_id"],
            predicted_stockout=stockout_date,
            days_until_stockout=result.get("days_to_stockout"),
            current_stock=next(
                (i.quantity_on_hand for i in session.query(InventoryItem)
                 .filter_by(id=result["item_id"])), 0),
            ai_message=result["alert_message"],
            draft_order_qty=result.get("suggested_reorder_qty"),
            status=NotificationStatus.pending
        )
        session.add(notif)
    session.commit()


# ── TOP BAR ─────────────────────────────────
st.markdown("""
<div class="topbar">
  <div>
    <div class="topbar-title">🤖 AI Prediction Engine</div>
    <div class="topbar-sub">Powered by Google Gemini · Research Farm Inventory Intelligence</div>
  </div>
  <div style="font-size:0.82rem;opacity:0.8">UNL East Campus</div>
</div>
""", unsafe_allow_html=True)

if not GEMINI_API_KEY:
    st.error("⚠️ GEMINI_API_KEY not found. Make sure your .env file is set up correctly.")
    st.stop()

# ── FARM SNAPSHOT ────────────────────────────
farm_ctx = get_farm_context()
farm     = session.query(Farm).first()

st.markdown('<div class="section-header">Farm Snapshot</div>', unsafe_allow_html=True)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Area",    f"{farm_ctx['total_area_ha']} ha")
c2.metric("Active Plots",  farm_ctx["plots"])
c3.metric("Inventory Items", len(farm_ctx["inventory"]))
c4.metric("Upcoming Treatments (30d)", len(farm_ctx["upcoming_treatments_30d"]))

# ── RUN AI ───────────────────────────────────
st.markdown('<div class="section-header">AI Analysis</div>', unsafe_allow_html=True)

col_btn, col_info = st.columns([1, 3])
with col_btn:
    run = st.button("🤖 Run AI Analysis", use_container_width=True)
with col_info:
    st.caption("Gemini will analyze your inventory, usage history, upcoming treatments, and equipment to predict stockouts and generate alerts.")

if run:
    with st.spinner("Gemini is analyzing your farm data..."):
        results = run_ai_analysis(farm_ctx)
        if results:
            st.session_state.ai_results = results
            for r in results:
                if r.get("severity") in ["critical", "warning"]:
                    save_notification(r, farm.id)

# ── DISPLAY RESULTS ──────────────────────────
if st.session_state.ai_results:
    results = st.session_state.ai_results

    # Sort: critical first, then warning, then ok
    order = {"critical": 0, "warning": 1, "ok": 2}
    results_sorted = sorted(results, key=lambda r: order.get(r.get("severity", "ok"), 2))

    critical_count = sum(1 for r in results if r.get("severity") == "critical")
    warning_count  = sum(1 for r in results if r.get("severity") == "warning")
    ok_count       = sum(1 for r in results if r.get("severity") == "ok")

    st.markdown(f"""
    <div style="display:flex;gap:8px;margin-bottom:16px">
      <span class="stat-pill" style="background:#fff0f0;color:#D00000">🔴 {critical_count} Critical</span>
      <span class="stat-pill" style="background:#fffbf0;color:#e67e22">🟡 {warning_count} Warning</span>
      <span class="stat-pill" style="background:#f0fff4;color:#1F6B3A">🟢 {ok_count} OK</span>
    </div>
    """, unsafe_allow_html=True)

    for r in results_sorted:
        severity  = r.get("severity", "ok")
        card_cls  = f"ai-card-{severity}"
        icon      = "🔴" if severity == "critical" else ("🟡" if severity == "warning" else "🟢")
        conf      = r.get("confidence", 50)
        item_id   = r.get("item_id")

        st.markdown(f"""
        <div class="{card_cls}">
          <div class="ai-label">{icon} {severity.upper()} · {r.get('item_name','')}</div>
          <div class="ai-message">{r.get('alert_message','')}</div>
          <div style="display:flex;gap:16px;font-size:0.8rem;color:#555;margin:8px 0">
            <span>📦 <strong>{r.get('days_to_reorder','?')}</strong> days to reorder point</span>
            <span>💀 <strong>{r.get('days_to_stockout','?')}</strong> days to stockout</span>
            <span>📈 <strong>{r.get('estimated_rate_per_day','?')}</strong> {next((i['unit'] for i in farm_ctx['inventory'] if i['id']==item_id), '')}/day estimated</span>
            <span>🛒 Reorder <strong>{r.get('suggested_reorder_qty','?')}</strong> units</span>
          </div>
          <div class="ai-label" style="margin-top:8px">AI Confidence</div>
          <div class="confidence-bar">
            <div class="confidence-fill" style="width:{conf}%"></div>
          </div>
          <div style="font-size:0.75rem;color:#888">{conf}% — {r.get('reasoning','')}</div>
        </div>
        """, unsafe_allow_html=True)

        # Correction loop
        with st.expander(f"✏️ Correct AI estimate for {r.get('item_name','')}"):
            st.markdown('<div class="correction-box">', unsafe_allow_html=True)
            st.caption("If the AI's rate estimate seems wrong, enter the actual rate here. The AI will use your correction next time.")
            col1, col2 = st.columns([2,1])
            actual_rate = col1.number_input(
                f"Actual daily usage rate",
                min_value=0.0, step=0.1,
                key=f"correction_{item_id}",
                help="Enter the real average daily consumption for this item"
            )
            if col2.button("Submit Correction", key=f"submit_{item_id}"):
                if item_id not in st.session_state.corrections:
                    st.session_state.corrections[item_id] = []
                st.session_state.corrections[item_id].append({
                    "rate": actual_rate,
                    "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                st.success(f"✓ Correction saved. Re-run analysis to apply.")
            st.markdown('</div>', unsafe_allow_html=True)

    # ── DRAFT REORDER TABLE ──────────────────
    critical_warning = [r for r in results_sorted if r.get("severity") in ["critical","warning"]]
    if critical_warning:
        st.markdown('<div class="section-header">Draft Purchase Orders</div>', unsafe_allow_html=True)
        st.caption("Review and approve items to reorder. These are AI-generated drafts — nothing is ordered automatically.")

        for r in critical_warning:
            item_id  = r.get("item_id")
            item_obj = session.query(InventoryItem).filter_by(id=item_id).first()
            if not item_obj:
                continue

            col1, col2, col3, col4 = st.columns([3,1,1,1])
            col1.markdown(f"**{r.get('item_name','')}**  \n{item_obj.supplier or 'No supplier set'}")
            qty = col2.number_input("Qty", value=float(r.get("suggested_reorder_qty", item_obj.reorder_quantity or 0)),
                                    key=f"order_qty_{item_id}", label_visibility="collapsed")
            col3.markdown(f"<div style='padding-top:8px;font-size:0.85rem;color:#555'>{item_obj.unit}</div>", unsafe_allow_html=True)

            if col4.button("✓ Approve", key=f"approve_{item_id}"):
                notif = (session.query(Notification)
                         .filter_by(inventory_item_id=item_id, status=NotificationStatus.pending)
                         .first())
                if notif:
                    notif.status = NotificationStatus.approved
                    notif.draft_order_qty = qty
                    notif.draft_order_sent = True
                    notif.resolved_at = datetime.now()
                    session.commit()
                st.success(f"✓ Order for {qty} {item_obj.unit} of {r.get('item_name','')} approved.")

else:
    st.markdown("""
    <div class="ai-card" style="text-align:center;padding:40px;color:#aaa">
      <div style="font-size:2.5rem;margin-bottom:12px">🤖</div>
      <div style="font-size:1rem;font-weight:600;color:#555;margin-bottom:6px">AI Engine Ready</div>
      <div style="font-size:0.85rem">Click "Run AI Analysis" to analyze your farm inventory,<br/>predict stockouts, and generate reorder recommendations.</div>
    </div>
    """, unsafe_allow_html=True)
