"""
app.py
------
Step 2 — Inventory Dashboard & Usage Logging
AI-Powered Research Farm Manager
University of Nebraska–Lincoln

Run :
    streamlit run app.py
"""

import streamlit as st
import pandas as pd
import uuid
from datetime import datetime, timezone, date, timedelta
from werkzeug.security import check_password_hash
from sqlalchemy import or_
from database import get_session
from models import (
    Farm, InventoryItem, UsageLog, Plot, Equipment,
    User, Field, CropVariety, TreatmentPlan, ActivityLog
)

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Farm Manager — UNL",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;1,300;1,400&family=DM+Sans:wght@300;400;500&display=swap');

*, *::before, *::after { box-sizing: border-box; }

html, body, .stApp {
    background: #f9f8f6 !important;
    color: #0a0a0a !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 300 !important;
    letter-spacing: 0.01em;
}

/* Headings — editorial serif */
h1, h2, h3, h4,
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3 {
    font-family: 'Cormorant Garamond', Georgia, serif !important;
    font-weight: 400 !important;
    letter-spacing: 0.04em !important;
    color: #0a0a0a !important;
    line-height: 1.2 !important;
}

/* Sidebar — full black */
[data-testid="stSidebar"] {
    background: #0a0a0a !important;
    border-right: none !important;
}
[data-testid="stSidebar"] * { color: #d8d4cc !important; }
[data-testid="stSidebar"] hr { border-color: #1e1e1e !important; }
[data-testid="stSidebar"] .stSelectbox label {
    color: #555 !important;
    font-size: 0.68rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.14em !important;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] > div > div {
    background: #111 !important;
    border: 1px solid #1e1e1e !important;
    color: #aaa !important;
    border-radius: 0 !important;
}
[data-testid="stSidebar"] .stExpander {
    background: #111 !important;
    border: 1px solid #1e1e1e !important;
    border-radius: 0 !important;
}
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    border: 1px solid #2a2a2a !important;
    color: #777 !important;
    font-size: 0.68rem !important;
    letter-spacing: 0.14em !important;
    text-transform: uppercase !important;
    border-radius: 0 !important;
    padding: 6px 16px !important;
    transition: all 0.2s ease !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    border-color: #555 !important;
    color: #f9f8f6 !important;
    background: transparent !important;
}

/* Inputs */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stDateInput > div > div > input,
.stTextArea > div > div > textarea {
    background: #fff !important;
    border: none !important;
    border-bottom: 1px solid #d0cdc8 !important;
    border-radius: 0 !important;
    color: #0a0a0a !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 300 !important;
    padding: 10px 4px !important;
    font-size: 0.88rem !important;
    box-shadow: none !important;
}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-bottom: 1px solid #0a0a0a !important;
    box-shadow: none !important;
}
.stTextInput label, .stNumberInput label,
.stDateInput label, .stTextArea label, .stSelectbox label {
    font-size: 0.68rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.14em !important;
    color: #999 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 400 !important;
}
[data-testid="stSelectbox"] > div > div {
    border: none !important;
    border-bottom: 1px solid #d0cdc8 !important;
    border-radius: 0 !important;
    background: #fff !important;
}

/* Metrics */
[data-testid="stMetric"] {
    background: #fff;
    border: none;
    border-top: 1px solid #0a0a0a;
    border-radius: 0;
    padding: 20px 0 16px;
}
[data-testid="stMetricLabel"] {
    font-size: 0.65rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.16em !important;
    color: #aaa !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 400 !important;
}
[data-testid="stMetricValue"] {
    font-family: 'Cormorant Garamond', serif !important;
    font-size: 2.6rem !important;
    font-weight: 300 !important;
    color: #0a0a0a !important;
    line-height: 1.1 !important;
}

/* Forms */
div[data-testid="stForm"] {
    background: #fff;
    border: none;
    border-top: 2px solid #0a0a0a;
    border-radius: 0;
    padding: 28px 24px 24px;
}

/* Buttons */
.stButton > button {
    background: #0a0a0a !important;
    color: #f9f8f6 !important;
    border: none !important;
    border-radius: 0 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.68rem !important;
    font-weight: 400 !important;
    letter-spacing: 0.16em !important;
    text-transform: uppercase !important;
    padding: 10px 28px !important;
    transition: background 0.2s ease !important;
}
.stButton > button:hover { background: #2a2a2a !important; }

/* DataFrames */
[data-testid="stDataFrame"] {
    border: none !important;
    border-top: 1px solid #0a0a0a !important;
}
[data-testid="stDataFrame"] th {
    font-size: 0.65rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.12em !important;
    color: #aaa !important;
    font-weight: 400 !important;
    border-bottom: 1px solid #e8e6e2 !important;
}
[data-testid="stDataFrame"] td {
    font-size: 0.82rem !important;
    font-weight: 300 !important;
}

/* Divider */
hr {
    border: none !important;
    border-top: 1px solid #e8e6e2 !important;
    margin: 28px 0 !important;
}

/* Alert cards — monochromatic */
.alert-critical {
    background: #fff; border-left: 3px solid #0a0a0a;
    padding: 14px 18px; margin: 6px 0;
}
.alert-warning {
    background: #fff; border-left: 3px solid #888;
    padding: 14px 18px; margin: 6px 0;
}
.alert-ok {
    background: #f9f8f6; border-left: 3px solid #d0cdc8;
    padding: 14px 18px; margin: 6px 0;
}
.alert-overdue {
    background: #fff; border-left: 3px solid #0a0a0a;
    padding: 14px 18px; margin: 6px 0;
}
.alert-upcoming {
    background: #f9f8f6; border-left: 3px solid #bbb;
    padding: 14px 18px; margin: 6px 0;
}
.alert-title {
    font-size: 0.84rem; font-weight: 400; letter-spacing: 0.04em;
    color: #0a0a0a; margin-bottom: 3px;
    font-family: 'DM Sans', sans-serif;
}
.alert-sub {
    font-size: 0.73rem; color: #999; letter-spacing: 0.02em; font-weight: 300;
}

/* Captions */
.stCaption, [data-testid="stCaptionContainer"] {
    font-size: 0.68rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.12em !important;
    color: #aaa !important;
}

/* Alerts (st.success, st.warning, etc.) */
[data-testid="stAlert"] {
    border-radius: 0 !important;
    border: none !important;
    border-left: 2px solid #888 !important;
    background: #f9f8f6 !important;
    font-size: 0.8rem !important;
    font-family: 'DM Sans', sans-serif !important;
}

/* Checkbox */
.stCheckbox label {
    font-size: 0.72rem !important;
    letter-spacing: 0.08em !important;
    color: #666 !important;
    text-transform: uppercase !important;
}

/* Page-load fade-in */
@keyframes fadeUp {
    from { opacity: 0; transform: translateY(14px); }
    to   { opacity: 1; transform: translateY(0); }
}
.main .block-container {
    animation: fadeUp 0.45s ease forwards;
    max-width: 1200px !important;
    padding: 2rem 3rem !important;
}

/* Bar chart */
[data-testid="stVegaLiteChart"] {
    border-top: 1px solid #0a0a0a !important;
}

/* Custom classes */
.page-header {
    display: flex;
    align-items: baseline;
    gap: 20px;
    border-bottom: 1px solid #0a0a0a;
    padding-bottom: 16px;
    margin-bottom: 36px;
}
.page-header-title {
    font-family: 'Cormorant Garamond', serif;
    font-size: 1.7rem;
    font-weight: 400;
    letter-spacing: 0.1em;
    color: #0a0a0a;
    text-transform: uppercase;
}
.page-header-sub {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    color: #bbb;
    font-family: 'DM Sans', sans-serif;
    font-weight: 300;
}
.section-label {
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.2em;
    color: #bbb;
    font-family: 'DM Sans', sans-serif;
    margin-bottom: 14px;
    display: block;
}
.stock-bar-track {
    background: #eceae6; height: 2px; margin-bottom: 18px;
}
.stock-bar-fill { height: 2px; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# AUTHENTICATION GATE
# ─────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    col_l, col_m, col_r = st.columns([1, 1.2, 1])
    with col_m:
        st.markdown("""
        <div style='text-align:center; padding: 72px 0 48px;'>
            <div style='font-family:"Cormorant Garamond",serif; font-size:3rem;
                        font-weight:300; letter-spacing:0.2em; text-transform:uppercase;
                        color:#0a0a0a; line-height:1;'>Farm Manager</div>
            <div style='font-size:0.6rem; text-transform:uppercase; letter-spacing:0.26em;
                        color:#bbb; margin-top:10px; font-family:"DM Sans",sans-serif;'>
                University of Nebraska–Lincoln
            </div>
            <div style='width:36px; height:1px; background:#0a0a0a; margin:24px auto 0;'></div>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            identifier = st.text_input("NUID or UNL Email", placeholder="12345678 or you@unl.edu")
            password   = st.text_input("Password", type="password")
            submitted  = st.form_submit_button("Sign In")

        st.markdown("""
        <div style='text-align:center; margin-top:14px;'>
            <span style='font-size:0.6rem; text-transform:uppercase; letter-spacing:0.14em;
                         color:#ccc; font-family:"DM Sans",sans-serif;'>
                Restricted to @unl.edu accounts
            </span>
        </div>
        """, unsafe_allow_html=True)

    if submitted:
        _s    = get_session()
        _user = _s.query(User).filter(
            or_(User.email == identifier, User.nuid == identifier)
        ).first()
        _s.close()

        if (
            _user
            and _user.is_active
            and _user.email.endswith("@unl.edu")
            and check_password_hash(_user.password_hash, password)
        ):
            _session_id = str(uuid.uuid4())
            st.session_state.authenticated = True
            st.session_state.user_name  = _user.name
            st.session_state.user_id    = _user.id
            st.session_state.session_id = _session_id
            _log_s = get_session()
            _log_s.add(ActivityLog(
                user_id=_user.id, session_id=_session_id,
                action="login",
                detail=f"Signed in as {_user.name} ({_user.email})"
            ))
            _log_s.commit()
            _log_s.close()
            st.rerun()
        else:
            st.error("Invalid credentials or non-UNL account.")

    st.stop()


# ─────────────────────────────────────────────
# SESSION & DATA HELPERS
# ─────────────────────────────────────────────
@st.cache_resource
def get_db():
    return get_session()

session = get_db()

def get_farm():
    return session.query(Farm).first()

def get_inventory():
    farm = get_farm()
    if not farm:
        return []
    return session.query(InventoryItem).filter_by(farm_id=farm.id).all()

def get_plots():
    return session.query(Plot).all()

def get_equipment():
    farm = get_farm()
    return session.query(Equipment).filter_by(farm_id=farm.id).all() if farm else []

def get_users():
    return session.query(User).all()

def get_recent_logs(limit=50):
    return (session.query(UsageLog)
            .order_by(UsageLog.log_date.desc())
            .limit(limit).all())

def get_upcoming_treatments(days_ahead=7):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = today + timedelta(days=days_ahead)
    return (session.query(TreatmentPlan)
            .filter(TreatmentPlan.applied == False)
            .filter(TreatmentPlan.planned_date >= today)
            .filter(TreatmentPlan.planned_date <= cutoff)
            .order_by(TreatmentPlan.planned_date)
            .all())

def get_overdue_treatments():
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return (session.query(TreatmentPlan)
            .filter(TreatmentPlan.applied == False)
            .filter(TreatmentPlan.planned_date < today)
            .order_by(TreatmentPlan.planned_date)
            .all())

def get_today_logs():
    logs = get_recent_logs(100)
    return [l for l in logs if l.log_date and l.log_date.date() == date.today()]

def stock_status(item):
    if item.quantity_on_hand <= item.reorder_threshold * 0.5:
        return "critical"
    elif item.quantity_on_hand <= item.reorder_threshold:
        return "warning"
    return "ok"

def days_remaining(item):
    logs = (session.query(UsageLog)
            .filter_by(inventory_item_id=item.id)
            .order_by(UsageLog.log_date.desc())
            .limit(14).all())
    if not logs or len(logs) < 2:
        return None
    total_used = sum(l.quantity_used for l in logs)
    avg_per_day = total_used / 14
    if avg_per_day == 0:
        return None
    return int(item.quantity_on_hand / avg_per_day)

def log_activity(action: str, detail: str):
    s = get_session()
    s.add(ActivityLog(
        user_id=st.session_state.user_id,
        session_id=st.session_state.get("session_id", "unknown"),
        action=action,
        detail=detail,
    ))
    s.commit()
    s.close()

def mark_treatment_applied(treatment_id):
    t = session.query(TreatmentPlan).get(treatment_id)
    if t:
        t.applied = True
        t.applied_date = datetime.now()
        session.commit()
        plot_code  = t.plot.plot_code if t.plot else "unknown plot"
        input_name = t.inventory_item.name if t.inventory_item else "unknown item"
        log_activity("mark_treatment_applied",
                     f"Marked treatment applied: {input_name} on {plot_code}")


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
farm = get_farm()
inventory = get_inventory()

with st.sidebar:
    st.markdown("""
    <div style='padding:32px 0 24px;'>
        <div style='font-family:"Cormorant Garamond",serif; font-size:1.4rem;
                    font-weight:300; letter-spacing:0.2em; text-transform:uppercase;
                    color:#f9f8f6;'>Farm Manager</div>
        <div style='width:24px; height:1px; background:#2a2a2a; margin-top:10px;'></div>
    </div>
    """, unsafe_allow_html=True)

    if farm:
        st.markdown(f"""
        <div style='margin-bottom:20px;'>
            <div style='font-family:"Cormorant Garamond",serif; font-size:1rem;
                        color:#c8c4bc; letter-spacing:0.06em;'>{farm.name}</div>
            <div style='font-size:0.65rem; color:#555; letter-spacing:0.1em;
                        text-transform:uppercase; margin-top:4px;'>
                {farm.location or ''} · {farm.total_area_ha} ha
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style='margin-bottom:16px;'>
        <div style='font-size:0.6rem;text-transform:uppercase;letter-spacing:0.14em;color:#444;'>Signed in as</div>
        <div style='font-size:0.8rem;color:#888;margin-top:2px;'>{st.session_state.get('user_name','')}</div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("Sign Out", key="signout"):
        st.session_state.authenticated = False
        st.rerun()

    st.divider()

    page = st.selectbox(
        "Navigate",
        ["Dashboard", "Inventory", "Log Usage", "Treatments", "Usage History", "Users", "Activity Log"]
    )

    st.divider()

    critical = [i for i in inventory if stock_status(i) == "critical"]
    warning  = [i for i in inventory if stock_status(i) == "warning"]
    overdue  = get_overdue_treatments()

    def _sb(text, color="#555"):
        st.markdown(
            f"<div style='font-size:0.65rem;text-transform:uppercase;letter-spacing:0.1em;"
            f"color:{color};margin:4px 0;'>{text}</div>",
            unsafe_allow_html=True
        )

    if overdue:   _sb(f"▪ {len(overdue)} overdue treatment{'s' if len(overdue)>1 else ''}", "#999")
    if critical:  _sb(f"▪ {len(critical)} critical stock", "#999")
    if warning:   _sb(f"▪ {len(warning)} low stock", "#666")
    if not overdue and not critical and not warning:
        _sb("▫ All clear", "#444")

    st.divider()

    with st.expander("⚡ Quick Log"):
        inv_map  = {f"{i.name} ({i.unit})": i for i in inventory}
        users    = get_users()
        user_map = {u.name: u for u in users}

        with st.form("quick_log"):
            item_label = st.selectbox("Item", list(inv_map.keys()), key="ql_item")
            qty        = st.number_input("Qty Used", min_value=0.01, step=0.5, key="ql_qty")
            user_label = st.selectbox("Logged By", list(user_map.keys()), key="ql_user")
            if st.form_submit_button("Log"):
                item = inv_map[item_label]
                user = user_map[user_label]
                item.quantity_on_hand = max(0, item.quantity_on_hand - qty)
                log = UsageLog(
                    inventory_item_id=item.id,
                    logged_by=user.id,
                    quantity_used=qty,
                    log_date=datetime.now(),
                )
                session.add(log)
                session.commit()
                log_activity("quick_log", f"Quick-logged {qty} {item.unit} of {item.name}")
                st.success(f"Logged {qty} {item.unit}")
                st.rerun()


# ─────────────────────────────────────────────
# PAGE HEADER
# ─────────────────────────────────────────────
today_str = datetime.now().strftime("%d %b %Y").upper()
st.markdown(
    f"""<div class="page-header">
        <span class="page-header-title">UNL Research Farm</span>
        <span class="page-header-sub">{page} &nbsp;·&nbsp; {today_str}</span>
    </div>""",
    unsafe_allow_html=True
)


# ═════════════════════════════════════════════
# PAGE: DASHBOARD
# ═════════════════════════════════════════════
if page == "Dashboard":

    plots      = get_plots()
    upcoming   = get_upcoming_treatments(7)
    overdue    = get_overdue_treatments()
    today_logs = get_today_logs()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Active Plots",    len(plots))
    c2.metric("Inventory Items", len(inventory))
    c3.metric("Overdue",         len(overdue),
              delta=f"{len(overdue)} need action" if overdue else None,
              delta_color="inverse")
    c4.metric("Due This Week",   len(upcoming))
    c5.metric("Logged Today",    len(today_logs))

    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    st.markdown("<span class='section-label'>Needs Attention</span>", unsafe_allow_html=True)

    has_issues = False

    for t in overdue:
        has_issues = True
        days_late  = (datetime.now() - t.planned_date).days if t.planned_date else "?"
        plot_code  = t.plot.plot_code if t.plot else "—"
        input_name = t.inventory_item.name if t.inventory_item else "—"
        stage      = t.growth_stage.stage_code if t.growth_stage else "—"
        st.markdown(f"""
        <div class="alert-overdue">
          <div class="alert-title">Overdue — {input_name} on {plot_code} ({stage})</div>
          <div class="alert-sub">{t.planned_date.strftime('%d %b') if t.planned_date else '—'} · {days_late} day{'s' if days_late != 1 else ''} late · {t.rate_per_ha} {t.inventory_item.unit if t.inventory_item else ''}/ha</div>
        </div>""", unsafe_allow_html=True)

    for item in inventory:
        status = stock_status(item)
        days   = days_remaining(item)
        days_str = f" · ~{days} days left" if days else ""
        if status == "critical":
            has_issues = True
            st.markdown(f"""
            <div class="alert-critical">
              <div class="alert-title">Critical Stock — {item.name}</div>
              <div class="alert-sub">{item.quantity_on_hand:.1f} {item.unit} on hand · reorder at {item.reorder_threshold} {item.unit}{days_str}</div>
            </div>""", unsafe_allow_html=True)
        elif status == "warning":
            has_issues = True
            st.markdown(f"""
            <div class="alert-warning">
              <div class="alert-title">Low Stock — {item.name}</div>
              <div class="alert-sub">{item.quantity_on_hand:.1f} {item.unit} on hand · reorder at {item.reorder_threshold} {item.unit}{days_str}</div>
            </div>""", unsafe_allow_html=True)

    if not has_issues:
        st.markdown('<div class="alert-ok"><div class="alert-title">All Clear</div><div class="alert-sub">No overdue treatments · all stock levels healthy</div></div>', unsafe_allow_html=True)

    st.divider()

    left, right = st.columns(2)

    with left:
        st.markdown("<span class='section-label'>Today's Activity</span>", unsafe_allow_html=True)
        if today_logs:
            rows = []
            for log in today_logs:
                rows.append({
                    "Item": log.inventory_item.name if log.inventory_item else "—",
                    "Used": f"{log.quantity_used} {log.inventory_item.unit if log.inventory_item else ''}",
                    "Plot": log.plot.plot_code if log.plot else "—",
                    "By":   log.logged_by_user.name if log.logged_by_user else "—",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.caption("Nothing logged yet today.")

    with right:
        st.markdown("<span class='section-label'>Due This Week</span>", unsafe_allow_html=True)
        if upcoming:
            rows = []
            for t in upcoming:
                rows.append({
                    "Date":  t.planned_date.strftime("%d %b") if t.planned_date else "—",
                    "Plot":  t.plot.plot_code if t.plot else "—",
                    "Input": t.inventory_item.name if t.inventory_item else "—",
                    "Stage": t.growth_stage.stage_code if t.growth_stage else "—",
                    "Rate":  f"{t.rate_per_ha} /ha",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.caption("No treatments due in the next 7 days.")


# ═════════════════════════════════════════════
# PAGE: INVENTORY
# ═════════════════════════════════════════════
elif page == "Inventory":

    def sort_key(item):
        s = stock_status(item)
        d = days_remaining(item) or 9999
        order = {"critical": 0, "warning": 1, "ok": 2}
        return (order[s], d)

    inventory_sorted = sorted(inventory, key=sort_key)

    rows = []
    for item in inventory_sorted:
        status = stock_status(item)
        days   = days_remaining(item)
        rows.append({
            "Item":          item.name,
            "Category":      item.category.capitalize() if item.category else "—",
            "On Hand":       item.quantity_on_hand,
            "Unit":          item.unit,
            "Days Left":     days if days is not None else "—",
            "Reorder At":    item.reorder_threshold,
            "Reorder Qty":   item.reorder_quantity,
            "Supplier":      item.supplier or "—",
            "Unit Cost ($)": item.unit_cost or "—",
            "Status":        "Critical" if status == "critical" else ("Low" if status == "warning" else "OK"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("<span class='section-label'>Stock Levels</span>", unsafe_allow_html=True)

    for item in inventory_sorted:
        max_val = max(item.quantity_on_hand, item.reorder_threshold * 3) if item.reorder_threshold else item.quantity_on_hand
        pct    = min(item.quantity_on_hand / max_val, 1.0) if max_val > 0 else 0
        status = stock_status(item)
        days   = days_remaining(item)
        color  = "#0a0a0a" if status == "critical" else ("#888" if status == "warning" else "#d0cdc8")
        col1, col2 = st.columns([4, 1])
        with col1:
            days_label = f"  ·  ~{days}d left" if days else ""
            st.markdown(
                f"<div style='font-size:0.78rem;letter-spacing:0.04em;color:#0a0a0a;"
                f"font-family:\"DM Sans\",sans-serif;margin-bottom:4px;font-weight:400;'>"
                f"{item.name}"
                f"<span style='color:#bbb;font-size:0.7rem;font-weight:300;'>{days_label}</span></div>",
                unsafe_allow_html=True
            )
            st.markdown(
                f'<div class="stock-bar-track">'
                f'<div class="stock-bar-fill" style="width:{pct*100:.0f}%;background:{color};"></div>'
                f'</div>',
                unsafe_allow_html=True
            )
        with col2:
            st.markdown(
                f"<div style='text-align:right;font-size:0.72rem;color:#bbb;"
                f"font-family:\"DM Sans\",sans-serif;letter-spacing:0.04em;'>"
                f"{item.quantity_on_hand:.1f} {item.unit}</div>",
                unsafe_allow_html=True
            )

    st.divider()
    st.markdown("<span class='section-label'>Add Item</span>", unsafe_allow_html=True)

    with st.form("add_inventory"):
        c1, c2 = st.columns(2)
        name     = c1.text_input("Item Name")
        category = c2.selectbox("Category", ["fertilizer", "herbicide", "fungicide", "fuel", "seed", "lubricant", "other"])
        c3, c4   = st.columns(2)
        unit     = c3.text_input("Unit (e.g. kg, L, bags)")
        qty      = c4.number_input("Quantity on Hand", min_value=0.0, step=1.0)
        c5, c6   = st.columns(2)
        threshold   = c5.number_input("Reorder Threshold", min_value=0.0, step=1.0)
        reorder_qty = c6.number_input("Reorder Quantity", min_value=0.0, step=1.0)
        supplier  = st.text_input("Supplier (optional)")
        unit_cost = st.number_input("Unit Cost ($)", min_value=0.0, step=0.01)
        if st.form_submit_button("Add Item") and name and unit:
            farm = get_farm()
            new_item = InventoryItem(
                farm_id=farm.id, name=name, category=category,
                unit=unit, quantity_on_hand=qty,
                reorder_threshold=threshold, reorder_quantity=reorder_qty,
                supplier=supplier, unit_cost=unit_cost if unit_cost > 0 else None
            )
            session.add(new_item)
            session.commit()
            log_activity("add_inventory", f"Added inventory item: {name} ({qty} {unit}, {category})")
            st.success(f"'{name}' added.")
            st.rerun()


# ═════════════════════════════════════════════
# PAGE: LOG USAGE
# ═════════════════════════════════════════════
elif page == "Log Usage":

    today_logs = get_today_logs()

    if today_logs:
        st.caption(f"{len(today_logs)} log{'s' if len(today_logs)>1 else ''} recorded today")
        rows = []
        for log in today_logs:
            rows.append({
                "Item":  log.inventory_item.name if log.inventory_item else "—",
                "Used":  f"{log.quantity_used} {log.inventory_item.unit if log.inventory_item else ''}",
                "Plot":  log.plot.plot_code if log.plot else "—",
                "Equip": log.equipment.name if log.equipment else "—",
                "Notes": log.notes or "—",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.caption("Nothing logged yet today.")

    st.divider()
    st.markdown("<span class='section-label'>New Entry</span>", unsafe_allow_html=True)

    plots     = get_plots()
    equipment = get_equipment()
    users     = get_users()

    inv_map   = {f"{i.name} ({i.unit})": i for i in inventory}
    plot_map  = {f"{p.plot_code} — {p.variety.variety_code}": p for p in plots}
    equip_map = {e.name: e for e in equipment}
    user_map  = {u.name: u for u in users}

    # Equipment outside form for live fuel preview
    equip_label_preview = st.selectbox(
        "Equipment (optional)",
        ["— None —"] + list(equip_map.keys()),
        key="equip_preview"
    )
    equip_preview = equip_map.get(equip_label_preview)

    estimated_qty = None
    if equip_preview and equip_preview.fuel_rate_l_per_hr:
        rate = equip_preview.fuel_rate_l_per_hr
        st.markdown(
            f"<div style='font-size:0.65rem;text-transform:uppercase;letter-spacing:0.14em;"
            f"color:#aaa;margin:10px 0 4px;'>{equip_preview.name} — {rate} L / hr</div>",
            unsafe_allow_html=True
        )
        hours_input = st.number_input(
            "Hours Used — leave 0 to enter quantity manually",
            min_value=0.0, step=0.5, value=0.0,
            key="hours_preview"
        )
        if hours_input > 0:
            estimated_qty = round(rate * hours_input, 2)
            st.markdown(
                f"<div style='font-family:\"Cormorant Garamond\",serif;font-size:2rem;"
                f"font-weight:300;color:#0a0a0a;letter-spacing:0.04em;margin:10px 0 18px;'>"
                f"{estimated_qty} L "
                f"<span style='font-size:0.9rem;color:#bbb;font-family:\"DM Sans\",sans-serif;'>"
                f"estimated</span></div>",
                unsafe_allow_html=True
            )
    else:
        hours_input = 0.0
        if equip_label_preview != "— None —":
            st.caption("No fuel rate set for this equipment — enter quantity manually.")

    with st.form("log_usage"):
        c1, c2 = st.columns(2)
        item_label  = c1.selectbox("Inventory Item", list(inv_map.keys()))
        default_qty = float(estimated_qty) if estimated_qty else 0.01
        qty_used    = c2.number_input(
            "Quantity Used (L)" if estimated_qty else "Quantity Used",
            min_value=0.01, step=0.5, value=default_qty
        )

        c3, c4 = st.columns(2)
        plot_label = c3.selectbox("Plot (optional)", ["— None —"] + list(plot_map.keys()))
        c4.text_input("Equipment", value=equip_label_preview, disabled=True)

        c5, c6 = st.columns(2)
        user_label = c5.selectbox("Logged By", list(user_map.keys()))
        log_date   = c6.date_input("Date", value=date.today())

        notes = st.text_area("Notes (optional)", height=68)

        if st.form_submit_button("Submit Log"):
            item  = inv_map[item_label]
            plot  = plot_map.get(plot_label)
            equip = equip_map.get(equip_label_preview)
            user  = user_map[user_label]
            log_dt = datetime.combine(log_date, datetime.min.time())

            final_qty = estimated_qty if estimated_qty else qty_used

            item.quantity_on_hand = max(0, item.quantity_on_hand - final_qty)

            log = UsageLog(
                inventory_item_id=item.id,
                plot_id=plot.id if plot else None,
                equipment_id=equip.id if equip else None,
                logged_by=user.id,
                quantity_used=final_qty,
                log_date=log_dt,
                notes=notes
            )
            session.add(log)
            session.commit()

            plot_str  = plot.plot_code if plot else "no plot"
            equip_str = equip.name if equip else "no equipment"
            est_note  = (
                f" [auto-estimated: {hours_input}h × {equip.fuel_rate_l_per_hr} L/hr]"
                if estimated_qty and equip else ""
            )
            log_activity(
                "log_usage",
                f"Logged {final_qty} {item.unit} of {item.name} on {plot_str} using {equip_str}"
                + est_note
                + (f" — {notes}" if notes else "")
            )
            st.success(
                f"Logged {final_qty} {item.unit} of {item.name}. "
                f"Stock now: {item.quantity_on_hand:.1f} {item.unit}"
            )
            if item.reorder_threshold and item.quantity_on_hand <= item.reorder_threshold:
                st.warning(f"{item.name} is now below reorder threshold.")
            st.rerun()


# ═════════════════════════════════════════════
# PAGE: TREATMENTS
# ═════════════════════════════════════════════
elif page == "Treatments":

    overdue  = get_overdue_treatments()
    upcoming = get_upcoming_treatments(14)

    if overdue:
        st.markdown(f"<span class='section-label'>Overdue — {len(overdue)}</span>", unsafe_allow_html=True)
        for t in overdue:
            days_late  = (datetime.now() - t.planned_date).days if t.planned_date else "?"
            plot_code  = t.plot.plot_code if t.plot else "—"
            input_name = t.inventory_item.name if t.inventory_item else "—"
            stage      = t.growth_stage.stage_code if t.growth_stage else "—"
            total      = round(t.rate_per_ha * (t.plot.area_ha or 0), 2) if t.plot else "—"
            unit       = t.inventory_item.unit if t.inventory_item else ""

            col1, col2 = st.columns([5, 1])
            with col1:
                st.markdown(f"""
                <div class="alert-overdue">
                  <div class="alert-title">{input_name} — {plot_code} ({stage})</div>
                  <div class="alert-sub">{t.planned_date.strftime('%d %b') if t.planned_date else '—'} · {days_late}d overdue · {t.rate_per_ha} {unit}/ha · total: {total} {unit}</div>
                </div>""", unsafe_allow_html=True)
            with col2:
                st.write("")
                if st.button("Mark Applied", key=f"apply_od_{t.id}"):
                    mark_treatment_applied(t.id)
                    st.success("Applied.")
                    st.rerun()

        st.divider()

    st.markdown("<span class='section-label'>Upcoming — Next 14 Days</span>", unsafe_allow_html=True)
    if upcoming:
        for t in upcoming:
            days_until = (t.planned_date - datetime.now()).days if t.planned_date else "?"
            plot_code  = t.plot.plot_code if t.plot else "—"
            input_name = t.inventory_item.name if t.inventory_item else "—"
            stage      = t.growth_stage.stage_code if t.growth_stage else "—"
            total      = round(t.rate_per_ha * (t.plot.area_ha or 0), 2) if t.plot else "—"
            unit       = t.inventory_item.unit if t.inventory_item else ""
            inv_item   = t.inventory_item
            stock_ok   = inv_item and inv_item.quantity_on_hand >= total if isinstance(total, (int, float)) else True
            stock_note = "" if stock_ok else f" · only {inv_item.quantity_on_hand:.1f} {unit} in stock"

            col1, col2 = st.columns([5, 1])
            with col1:
                st.markdown(f"""
                <div class="alert-upcoming">
                  <div class="alert-title">{input_name} — {plot_code} ({stage})</div>
                  <div class="alert-sub">{t.planned_date.strftime('%d %b') if t.planned_date else '—'} · in {days_until}d · {t.rate_per_ha} {unit}/ha · total: {total} {unit}{stock_note}</div>
                </div>""", unsafe_allow_html=True)
            with col2:
                st.write("")
                if st.button("Mark Applied", key=f"apply_up_{t.id}"):
                    mark_treatment_applied(t.id)
                    st.success("Applied.")
                    st.rerun()
    else:
        st.caption("No treatments due in the next 14 days.")

    st.divider()

    st.markdown("<span class='section-label'>All Plans by Plot</span>", unsafe_allow_html=True)
    plots      = get_plots()
    plot_names = {f"{p.plot_code} — {p.variety.variety_code if p.variety else '?'}": p for p in plots}
    selected   = st.selectbox("Select Plot", list(plot_names.keys()))
    plot       = plot_names[selected]

    show_applied = st.checkbox("Include applied treatments", value=False)

    treatments = (session.query(TreatmentPlan)
                  .filter_by(plot_id=plot.id)
                  .order_by(TreatmentPlan.planned_date)
                  .all())
    if not show_applied:
        treatments = [t for t in treatments if not t.applied]

    if treatments:
        rows = []
        for t in treatments:
            total = round(t.rate_per_ha * (plot.area_ha or 0), 2)
            rows.append({
                "Stage":        t.growth_stage.stage_code if t.growth_stage else "—",
                "Input":        t.inventory_item.name if t.inventory_item else "—",
                "Rate /ha":     t.rate_per_ha,
                "Total Needed": total,
                "Unit":         t.inventory_item.unit if t.inventory_item else "—",
                "Planned":      t.planned_date.strftime("%d %b %Y") if t.planned_date else "—",
                "Type":         t.treatment_type.value.capitalize(),
                "Applied":      "✓" if t.applied else "Pending",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        pending = [t for t in treatments if not t.applied]
        if pending:
            if st.button(f"Mark all {len(pending)} pending as applied"):
                for t in pending:
                    mark_treatment_applied(t.id)
                st.success(f"Marked {len(pending)} treatments as applied.")
                st.rerun()
    else:
        st.caption("No pending treatments for this plot.")


# ═════════════════════════════════════════════
# PAGE: USAGE HISTORY
# ═════════════════════════════════════════════
elif page == "Usage History":

    col1, col2, col3 = st.columns(3)
    inv_names    = ["All Items"] + [i.name for i in inventory]
    filter_item  = col1.selectbox("Item", inv_names)
    date_range   = col2.selectbox("Period", ["Last 7 days", "Last 30 days", "Last 90 days", "All time"])
    filter_src   = col3.selectbox("Source", ["All logs", "Manual only", "AI estimated"])

    cutoffs = {
        "Last 7 days":  date.today() - timedelta(days=7),
        "Last 30 days": date.today() - timedelta(days=30),
        "Last 90 days": date.today() - timedelta(days=90),
        "All time":     None,
    }
    cutoff = cutoffs[date_range]

    logs = get_recent_logs(500)
    if filter_item != "All Items":
        logs = [l for l in logs if l.inventory_item and l.inventory_item.name == filter_item]
    if cutoff:
        logs = [l for l in logs if l.log_date and l.log_date.date() >= cutoff]
    if filter_src == "Manual only":
        logs = [l for l in logs if not l.ai_estimated]
    elif filter_src == "AI estimated":
        logs = [l for l in logs if l.ai_estimated]

    if logs:
        total_used = sum(l.quantity_used for l in logs)
        st.caption(f"{len(logs)} log{'s' if len(logs)>1 else ''} · total consumed: {total_used:.1f}")

        rows = []
        for log in logs:
            rows.append({
                "Date":      log.log_date.strftime("%d %b %Y") if log.log_date else "—",
                "Item":      log.inventory_item.name if log.inventory_item else "—",
                "Qty Used":  log.quantity_used,
                "Unit":      log.inventory_item.unit if log.inventory_item else "—",
                "Plot":      log.plot.plot_code if log.plot else "—",
                "Equipment": log.equipment.name if log.equipment else "—",
                "Logged By": log.logged_by_user.name if log.logged_by_user else "—",
                "AI Est.":   "Yes" if log.ai_estimated else "—",
                "Notes":     log.notes or "—",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        if filter_item != "All Items" and len(rows) > 1:
            st.divider()
            st.markdown("<span class='section-label'>Consumption Over Time</span>", unsafe_allow_html=True)
            chart_df = pd.DataFrame(rows)[["Date", "Qty Used"]].copy()
            chart_df["Date"] = pd.to_datetime(chart_df["Date"])
            chart_df = chart_df.sort_values("Date").set_index("Date").resample("D").sum()
            st.bar_chart(chart_df, color="#0a0a0a")
    else:
        st.info("No logs match the current filters.")


# ═════════════════════════════════════════════
# PAGE: USERS
# ═════════════════════════════════════════════
elif page == "Users":

    all_users = session.query(User).order_by(User.role, User.name).all()
    st.caption(f"{len(all_users)} registered accounts")

    rows = []
    for u in all_users:
        rows.append({
            "Name":    u.name + (" (you)" if u.id == st.session_state.get("user_id") else ""),
            "NUID":    u.nuid or "—",
            "Email":   u.email,
            "Role":    u.role.value.capitalize(),
            "Status":  "Active" if u.is_active else "Inactive",
            "Created": u.created_at.strftime("%d %b %Y") if u.created_at else "—",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ═════════════════════════════════════════════
# PAGE: ACTIVITY LOG
# ═════════════════════════════════════════════
elif page == "Activity Log":

    st.caption("Every login and action recorded in the system.")

    all_users   = session.query(User).order_by(User.name).all()
    user_names  = ["All Users"] + [u.name for u in all_users]
    action_opts = ["All Actions", "login", "log_usage", "quick_log",
                   "mark_treatment_applied", "add_inventory"]

    col1, col2, col3 = st.columns(3)
    filter_user   = col1.selectbox("User",   user_names)
    filter_action = col2.selectbox("Action", action_opts)
    filter_period = col3.selectbox("Period", ["Last 7 days", "Last 30 days", "All time"])

    cutoffs = {
        "Last 7 days":  date.today() - timedelta(days=7),
        "Last 30 days": date.today() - timedelta(days=30),
        "All time":     None,
    }
    cutoff = cutoffs[filter_period]

    q = session.query(ActivityLog).order_by(ActivityLog.timestamp.desc())
    if filter_user != "All Users":
        u = next((u for u in all_users if u.name == filter_user), None)
        if u:
            q = q.filter(ActivityLog.user_id == u.id)
    if filter_action != "All Actions":
        q = q.filter(ActivityLog.action == filter_action)
    if cutoff:
        q = q.filter(ActivityLog.timestamp >= datetime.combine(cutoff, datetime.min.time()))

    entries = q.limit(500).all()

    if entries:
        action_labels = {
            "login":                  "Sign In",
            "log_usage":              "Log Usage",
            "quick_log":              "Quick Log",
            "mark_treatment_applied": "Treatment Applied",
            "add_inventory":          "Add Inventory",
        }
        rows = []
        for e in entries:
            rows.append({
                "Timestamp": e.timestamp.strftime("%d %b %Y  %H:%M:%S") if e.timestamp else "—",
                "User":      e.user.name if e.user else "—",
                "Action":    action_labels.get(e.action, e.action),
                "Detail":    e.detail or "—",
                "Session":   e.session_id[:8] + "…",
            })
        df = pd.DataFrame(rows)
        st.caption(f"{len(rows)} event{'s' if len(rows) != 1 else ''} found")
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("<span class='section-label'>Summary by User</span>", unsafe_allow_html=True)
        summary = (
            df.groupby("User")["Action"]
            .value_counts()
            .rename("Count")
            .reset_index()
            .sort_values(["User", "Count"], ascending=[True, False])
        )
        st.dataframe(summary, use_container_width=True, hide_index=True)
    else:
        st.info("No activity found for the selected filters.")