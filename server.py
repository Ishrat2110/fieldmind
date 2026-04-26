"""
server.py — Flask web server for UNL Farm Manager
Run: python server.py
"""

import io
import csv
import os
from collections import defaultdict

from flask import (Flask, render_template, request, redirect,
                   url_for, flash, g, Response, session as flask_session)
from flask_wtf.csrf import CSRFProtect
from markupsafe import Markup
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from werkzeug.security import check_password_hash
from database import get_session
from models import (Farm, InventoryItem, UsageLog, Plot, Equipment,
                    User, TreatmentPlan, Notification, NotificationStatus,
                    CropVariety, Field)
from datetime import datetime, date, timedelta, timezone

app = Flask(__name__)
_secret = os.environ.get("SECRET_KEY")
if not _secret:
    raise RuntimeError(
        "SECRET_KEY is not set. Generate one with "
        "`python -c \"import secrets; print(secrets.token_hex(32))\"` "
        "and put it in your .env file."
    )
app.secret_key = _secret

csrf = CSRFProtect(app)

_PUBLIC_ENDPOINTS = {"login", "static"}

@app.before_request
def require_login():
    if request.endpoint not in _PUBLIC_ENDPOINTS and "user_id" not in flask_session:
        return redirect(url_for("login"))


# ── request-scoped DB session ───────────────────────────────────────────────────

def db():
    if "db" not in g:
        g.db = get_session()
    return g.db

@app.teardown_appcontext
def close_db(exc):
    session = g.pop("db", None)
    if session is not None:
        session.close()


# ── helpers ────────────────────────────────────────────────────────────────────

def get_farm(s):
    return s.query(Farm).first()

def stock_status(item):
    if item.reorder_threshold and item.quantity_on_hand <= item.reorder_threshold * 0.5:
        return "critical"
    if item.reorder_threshold and item.quantity_on_hand <= item.reorder_threshold:
        return "warning"
    return "ok"

def days_remaining(item, s):
    logs = (s.query(UsageLog)
              .filter_by(inventory_item_id=item.id)
              .order_by(UsageLog.log_date.desc())
              .limit(30).all())
    if len(logs) < 2:
        return None
    newest = logs[0].log_date
    oldest = logs[-1].log_date
    if hasattr(newest, "date"):
        newest = newest.date() if callable(newest.date) else newest
    if hasattr(oldest, "date"):
        oldest = oldest.date() if callable(oldest.date) else oldest
    span = max((newest - oldest).days, 1)
    avg_per_day = sum(l.quantity_used for l in logs) / span
    return int(item.quantity_on_hand / avg_per_day) if avg_per_day > 0 else None

def today_start():
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

def enrich_inventory(items, s):
    for item in items:
        item._status = stock_status(item)
        item._days   = days_remaining(item, s)
    sparklines = compute_sparklines([i.id for i in items], s)
    for item in items:
        item._spark = sparklines.get(item.id, Markup(""))
    return items

def nav_context(s):
    farm = get_farm(s)
    inv  = s.query(InventoryItem).filter_by(farm_id=farm.id).all() if farm else []
    today = today_start()
    overdue_count  = s.query(TreatmentPlan).filter(
        TreatmentPlan.applied == False,
        TreatmentPlan.planned_date < today
    ).count()
    critical_count = sum(1 for i in inv if stock_status(i) == "critical")
    warning_count  = sum(1 for i in inv if stock_status(i) == "warning")
    users = s.query(User).filter_by(is_active=True).order_by(User.name).all()
    suggestion_count = (
        s.query(Notification).filter_by(status=NotificationStatus.pending).count()
        if farm else 0
    )
    return dict(farm=farm, overdue_count=overdue_count,
                critical_count=critical_count, warning_count=warning_count,
                suggestion_count=suggestion_count,
                current_user_name=flask_session.get("user_name", ""),
                current_user_nuid=flask_session.get("user_nuid", ""),
                current_user_role=flask_session.get("user_role", ""),
                current_user_id=flask_session.get("user_id"),
                panel_inventory=inv, panel_users=users)


# ── auth routes ────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in flask_session:
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password   = request.form.get("password", "")

        s    = db()
        user = s.query(User).filter(
            or_(User.email == identifier, User.nuid == identifier)
        ).first()

        if not user or not user.is_active:
            error = "Invalid credentials."
        elif not user.email.endswith("@unl.edu"):
            error = "Access is restricted to UNL accounts."
        elif not check_password_hash(user.password_hash, password):
            error = "Invalid credentials."
        else:
            flask_session["user_id"]   = user.id
            flask_session["user_name"] = user.name
            flask_session["user_nuid"] = user.nuid or ""
            flask_session["user_role"] = user.role.value
            return redirect(url_for("dashboard"))

    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    flask_session.clear()
    return redirect(url_for("login"))


# ── chart helpers ──────────────────────────────────────────────────────────────

def _sparkline_svg(values, w=72, h=24, color="var(--text-3)"):
    """Build an inline SVG polyline from a list of daily values."""
    if not any(values):
        return Markup(f'<svg width="{w}" height="{h}"></svg>')
    max_v = max(values) or 1
    n = len(values)
    pad = 2
    pts = []
    for i, v in enumerate(values):
        x = round(pad + i * (w - 2 * pad) / max(n - 1, 1), 1)
        y = round(h - pad - (v / max_v) * (h - 2 * pad), 1)
        pts.append(f"{x},{y}")
    points = " ".join(pts)
    return Markup(
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none" '
        f'style="display:block;">'
        f'<polyline points="{points}" stroke="{color}" stroke-width="1.5" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )


def compute_sparklines(item_ids, s, days=7):
    """One bulk query → dict of item_id -> SVG sparkline markup."""
    if not item_ids:
        return {}
    cutoff = datetime.now() - timedelta(days=days)
    rows = (s.query(
        UsageLog.inventory_item_id,
        func.date(UsageLog.log_date).label("day"),
        func.sum(UsageLog.quantity_used).label("total")
    )
    .filter(UsageLog.inventory_item_id.in_(item_ids),
            UsageLog.log_date >= cutoff)
    .group_by(UsageLog.inventory_item_id, func.date(UsageLog.log_date))
    .all())

    day_map = defaultdict(dict)
    for row in rows:
        day_map[row.inventory_item_id][str(row.day)] = float(row.total)

    today = date.today()
    result = {}
    for iid in item_ids:
        values = [
            day_map[iid].get((today - timedelta(days=days - 1 - i)).isoformat(), 0)
            for i in range(days)
        ]
        has_data = any(v > 0 for v in values)
        color = "var(--green)" if has_data else "var(--text-3)"
        result[iid] = _sparkline_svg(values, color=color)
    return result


def daily_chart_data(s, days=14):
    """14-day daily total consumption across all items — for dashboard bar chart."""
    cutoff = datetime.now() - timedelta(days=days)
    rows = (s.query(
        func.date(UsageLog.log_date).label("day"),
        func.sum(UsageLog.quantity_used).label("total")
    )
    .filter(UsageLog.log_date >= cutoff)
    .group_by(func.date(UsageLog.log_date))
    .all())

    day_map = {str(r.day): float(r.total) for r in rows}
    today = date.today()
    chart = []
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        v = day_map.get(d.isoformat(), 0)
        chart.append({"date": d.strftime("%b %d"), "weekday": d.strftime("%a"),
                      "value": round(v, 1), "is_today": d == today})
    max_v = max((c["value"] for c in chart), default=1) or 1
    for c in chart:
        c["pct"] = round(c["value"] / max_v * 100, 1)
    return chart


def top_items_chart(s, days=14):
    """Top 5 items by total usage in last N days."""
    cutoff = datetime.now() - timedelta(days=days)
    rows = (s.query(
        UsageLog.inventory_item_id,
        func.sum(UsageLog.quantity_used).label("total")
    )
    .filter(UsageLog.log_date >= cutoff)
    .group_by(UsageLog.inventory_item_id)
    .order_by(func.sum(UsageLog.quantity_used).desc())
    .limit(5).all())

    result = []
    if not rows:
        return result
    max_v = float(rows[0].total) or 1
    for row in rows:
        item = s.query(InventoryItem).get(row.inventory_item_id)
        if item:
            result.append({
                "name": item.name,
                "unit": item.unit,
                "total": round(float(row.total), 1),
                "pct": round(float(row.total) / max_v * 100, 1),
            })
    return result


# ── routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    s    = db()
    ctx  = nav_context(s)
    farm = ctx["farm"]
    today = today_start()

    inv = enrich_inventory(
        s.query(InventoryItem).filter_by(farm_id=farm.id).all() if farm else [], s
    )

    overdue = (s.query(TreatmentPlan)
               .options(joinedload(TreatmentPlan.plot),
                        joinedload(TreatmentPlan.inventory_item),
                        joinedload(TreatmentPlan.growth_stage))
               .filter(TreatmentPlan.applied == False,
                       TreatmentPlan.planned_date < today)
               .order_by(TreatmentPlan.planned_date).all())

    upcoming = (s.query(TreatmentPlan)
                .options(joinedload(TreatmentPlan.plot),
                         joinedload(TreatmentPlan.inventory_item),
                         joinedload(TreatmentPlan.growth_stage))
                .filter(TreatmentPlan.applied == False,
                        TreatmentPlan.planned_date >= today,
                        TreatmentPlan.planned_date <= today + timedelta(days=7))
                .order_by(TreatmentPlan.planned_date).all())

    today_logs = (s.query(UsageLog)
                  .options(joinedload(UsageLog.inventory_item),
                           joinedload(UsageLog.plot),
                           joinedload(UsageLog.equipment))
                  .filter(UsageLog.log_date >= today)
                  .order_by(UsageLog.log_date.desc()).all())

    plots_count = s.query(Plot).count()

    for t in overdue:
        t._days_late  = (today - t.planned_date).days if t.planned_date else 0
        t._total      = round(t.rate_per_ha * (t.plot.area_ha or 0), 2) if t.plot else 0
    for t in upcoming:
        t._days_until = (t.planned_date - today).days if t.planned_date else 0
        t._total      = round(t.rate_per_ha * (t.plot.area_ha or 0), 2) if t.plot else 0

    chart  = daily_chart_data(s)
    top5   = top_items_chart(s)

    # Generate AI reorder suggestions for critical/warning items
    from reorder_ai import maybe_generate_suggestion, get_active_suggestions, _extract_urgency
    for item in inv:
        if item._status in ("critical", "warning"):
            maybe_generate_suggestion(item, s)
    suggestions = get_active_suggestions(s, farm.id) if farm else []

    return render_template("dashboard.html",
        page="dashboard",
        overdue=overdue, upcoming=upcoming,
        today_logs=today_logs, inventory=inv,
        plots_count=plots_count,
        chart=chart, top5=top5,
        suggestions=suggestions,
        **ctx)


@app.route("/inventory")
def inventory():
    s    = db()
    ctx  = nav_context(s)
    farm = ctx["farm"]
    inv  = enrich_inventory(
        s.query(InventoryItem).filter_by(farm_id=farm.id).all() if farm else [], s
    )
    inv.sort(key=lambda i: ({"critical": 0, "warning": 1, "ok": 2}[i._status], i._days or 9999))

    # Attach pending suggestion info to each item
    from reorder_ai import get_active_suggestions
    active_sugs = {n.inventory_item_id: n for n in get_active_suggestions(s, farm.id)} if farm else {}
    for item in inv:
        sug = active_sugs.get(item.id)
        item._has_suggestion = sug is not None
        item._suggested_qty  = int(sug.draft_order_qty) if sug and sug.draft_order_qty else None

    return render_template("inventory.html", page="inventory", inventory=inv, **ctx)


@app.route("/inventory/add", methods=["POST"])
def inventory_add():
    guard = _require_manager_or_admin()
    if guard:
        return guard
    s    = db()
    farm = get_farm(s)
    name     = request.form.get("name", "").strip()
    category = request.form.get("category", "other")
    unit     = request.form.get("unit", "").strip()

    try:
        qty         = float(request.form.get("qty", 0))
        threshold   = float(request.form.get("threshold", 0))
        reorder_qty = float(request.form.get("reorder_qty", 0))
        unit_cost_raw = request.form.get("unit_cost", "")
        unit_cost   = float(unit_cost_raw) if unit_cost_raw else None
    except ValueError:
        flash("Invalid numeric value.", "error")
        return redirect(url_for("inventory"))

    if qty < 0 or threshold < 0 or reorder_qty < 0:
        flash("Quantities cannot be negative.", "error")
        return redirect(url_for("inventory"))

    supplier = request.form.get("supplier", "").strip()

    if name and unit and farm:
        item = InventoryItem(
            farm_id=farm.id, name=name, category=category, unit=unit,
            quantity_on_hand=qty, reorder_threshold=threshold,
            reorder_quantity=reorder_qty, supplier=supplier or None,
            unit_cost=unit_cost
        )
        s.add(item)
        s.commit()
        flash(f"'{name}' added to inventory.", "success")
    else:
        flash("Name and unit are required.", "error")
    return redirect(url_for("inventory"))


@app.route("/inventory/<int:iid>/edit", methods=["POST"])
def inventory_edit(iid):
    guard = _require_manager_or_admin()
    if guard:
        return guard
    s    = db()
    item = s.query(InventoryItem).get(iid)
    if not item:
        flash("Item not found.", "error")
        return redirect(url_for("inventory"))

    name = request.form.get("name", "").strip()
    unit = request.form.get("unit", "").strip()
    if not name or not unit:
        flash("Name and unit are required.", "error")
        return redirect(url_for("inventory"))

    try:
        qty         = float(request.form.get("qty", 0))
        threshold   = float(request.form.get("threshold", 0))
        reorder_qty = float(request.form.get("reorder_qty", 0))
        unit_cost_raw = request.form.get("unit_cost", "")
        unit_cost   = float(unit_cost_raw) if unit_cost_raw else None
    except ValueError:
        flash("Invalid numeric value.", "error")
        return redirect(url_for("inventory"))

    if qty < 0 or threshold < 0 or reorder_qty < 0:
        flash("Quantities cannot be negative.", "error")
        return redirect(url_for("inventory"))

    item.name             = name
    item.category         = request.form.get("category", item.category)
    item.unit             = unit
    item.quantity_on_hand = qty
    item.reorder_threshold = threshold
    item.reorder_quantity  = reorder_qty
    item.supplier         = request.form.get("supplier", "").strip() or None
    item.unit_cost        = unit_cost
    item.last_updated     = datetime.now(timezone.utc)
    s.commit()
    flash(f"'{item.name}' updated.", "success")
    return redirect(url_for("inventory"))


@app.route("/inventory/<int:iid>/receive", methods=["POST"])
def inventory_receive(iid):
    s    = db()
    item = s.get(InventoryItem, iid)
    if not item:
        flash("Item not found.", "error")
        return redirect(url_for("inventory"))

    try:
        qty_received = float(request.form.get("qty_received", 0))
    except ValueError:
        flash("Invalid quantity.", "error")
        return redirect(url_for("inventory"))

    if qty_received <= 0:
        flash("Quantity received must be greater than zero.", "error")
        return redirect(url_for("inventory"))

    item.quantity_on_hand += qty_received
    item.last_updated = datetime.now(timezone.utc)

    # Auto-dismiss any pending suggestion for this item
    pending = s.query(Notification).filter_by(
        inventory_item_id=iid,
        status=NotificationStatus.pending
    ).all()
    for n in pending:
        n.status = NotificationStatus.approved
        n.resolved_at = datetime.now(timezone.utc)

    s.commit()
    flash(
        f"Received {qty_received:.1f} {item.unit} of {item.name}. "
        f"New stock: {item.quantity_on_hand:.1f} {item.unit}.",
        "success"
    )
    return redirect(url_for("inventory"))


@app.route("/inventory/<int:iid>/delete", methods=["POST"])
def inventory_delete(iid):
    guard = _require_manager_or_admin()
    if guard:
        return guard
    s    = db()
    item = s.query(InventoryItem).get(iid)
    if not item:
        return redirect(url_for("inventory"))

    log_count = s.query(UsageLog).filter_by(inventory_item_id=iid).count()
    if log_count > 0:
        flash(
            f"Cannot delete '{item.name}': {log_count} usage log entries reference it. "
            "Delete those logs first, or keep the item for historical accuracy.",
            "error"
        )
        return redirect(url_for("inventory"))

    s.delete(item)
    s.commit()
    flash(f"Deleted {item.name}.", "success")
    return redirect(url_for("inventory"))


@app.route("/treatments")
def treatments():
    s   = db()
    ctx = nav_context(s)
    today = today_start()

    overdue = (s.query(TreatmentPlan)
               .options(joinedload(TreatmentPlan.plot),
                        joinedload(TreatmentPlan.inventory_item),
                        joinedload(TreatmentPlan.growth_stage))
               .filter(TreatmentPlan.applied == False,
                       TreatmentPlan.planned_date < today)
               .order_by(TreatmentPlan.planned_date).all())

    upcoming = (s.query(TreatmentPlan)
                .options(joinedload(TreatmentPlan.plot),
                         joinedload(TreatmentPlan.inventory_item),
                         joinedload(TreatmentPlan.growth_stage))
                .filter(TreatmentPlan.applied == False,
                        TreatmentPlan.planned_date >= today,
                        TreatmentPlan.planned_date <= today + timedelta(days=14))
                .order_by(TreatmentPlan.planned_date).all())

    for t in overdue:
        t._days_late = (today - t.planned_date).days
        t._total     = round(t.rate_per_ha * (t.plot.area_ha or 0), 2) if t.plot else None

    for t in upcoming:
        t._days_until = (t.planned_date - today).days
        t._total      = round(t.rate_per_ha * (t.plot.area_ha or 0), 2) if t.plot else None
        inv_item      = t.inventory_item
        t._stock_ok   = (inv_item.quantity_on_hand >= t._total) if (inv_item and t._total) else True

    plots = s.query(Plot).all()
    selected_plot_id = request.args.get("plot_id", type=int)
    selected_plot    = s.query(Plot).get(selected_plot_id) if selected_plot_id else (plots[0] if plots else None)
    show_applied     = request.args.get("applied", "0") == "1"

    plot_treatments = []
    if selected_plot:
        q = (s.query(TreatmentPlan)
               .options(joinedload(TreatmentPlan.inventory_item),
                        joinedload(TreatmentPlan.growth_stage))
               .filter_by(plot_id=selected_plot.id)
               .order_by(TreatmentPlan.planned_date))
        if not show_applied:
            q = q.filter(TreatmentPlan.applied == False)
        plot_treatments = q.all()
        for t in plot_treatments:
            t._total = round(t.rate_per_ha * (selected_plot.area_ha or 0), 2)

    return render_template("treatments.html",
        page="treatments",
        overdue=overdue, upcoming=upcoming,
        plots=plots, selected_plot=selected_plot,
        plot_treatments=plot_treatments, show_applied=show_applied,
        **ctx)


@app.route("/treatments/<int:tid>/apply", methods=["POST"])
def treatment_apply(tid):
    guard = _require_manager_or_admin()
    if guard:
        return guard
    s = db()
    t = s.query(TreatmentPlan).get(tid)
    if t:
        t.applied      = True
        t.applied_date = datetime.now()
        s.commit()
        flash("Treatment marked as applied.", "success")
    return redirect(request.referrer or url_for("treatments"))


@app.route("/treatments/apply-bulk", methods=["POST"])
def treatment_apply_bulk():
    guard = _require_manager_or_admin()
    if guard:
        return guard
    s     = db()
    ids   = request.form.getlist("ids[]", type=int)
    count = 0
    for tid in ids:
        t = s.query(TreatmentPlan).get(tid)
        if t and not t.applied:
            t.applied      = True
            t.applied_date = datetime.now()
            count += 1
    s.commit()
    flash(f"{count} treatment{'s' if count != 1 else ''} marked as applied.", "success")
    return redirect(request.referrer or url_for("treatments"))


@app.route("/log", methods=["GET", "POST"])
def log_usage():
    s   = db()
    ctx = nav_context(s)
    farm = ctx["farm"]

    inv   = s.query(InventoryItem).filter_by(farm_id=farm.id).all() if farm else []
    plots = s.query(Plot).all()
    equip = s.query(Equipment).filter_by(farm_id=farm.id).all() if farm else []
    users = s.query(User).all()
    today = today_start()
    today_logs = (s.query(UsageLog)
                  .options(joinedload(UsageLog.inventory_item),
                           joinedload(UsageLog.plot),
                           joinedload(UsageLog.equipment))
                  .filter(UsageLog.log_date >= today)
                  .order_by(UsageLog.log_date.desc()).all())

    if request.method == "POST":
        guard = _require_manager_or_admin()
        if guard:
            return guard
        try:
            item_id  = int(request.form["item_id"])
            qty_used = float(request.form["qty_used"])
            user_id  = int(request.form["user_id"])
            log_date = datetime.strptime(request.form["log_date"], "%Y-%m-%d")
        except (KeyError, ValueError):
            flash("Invalid form data.", "error")
            return redirect(url_for("log_usage"))

        if qty_used <= 0:
            flash("Quantity must be greater than zero.", "error")
            return redirect(url_for("log_usage"))

        if log_date.date() > date.today():
            flash("Log date cannot be in the future.", "error")
            return redirect(url_for("log_usage"))

        plot_id  = request.form.get("plot_id") or None
        equip_id = request.form.get("equip_id") or None
        notes    = request.form.get("notes", "").strip()

        item = s.query(InventoryItem).get(item_id)
        if not item:
            flash("Inventory item not found.", "error")
            return redirect(url_for("log_usage"))

        if qty_used > (item.quantity_on_hand or 0):
            flash(
                f"Cannot log {qty_used} {item.unit}: only "
                f"{item.quantity_on_hand:.1f} {item.unit} on hand. "
                "Restock the item first, or correct the quantity.",
                "error"
            )
            return redirect(url_for("log_usage"))

        item.quantity_on_hand = (item.quantity_on_hand or 0) - qty_used

        log = UsageLog(
            inventory_item_id=item_id,
            plot_id=int(plot_id)   if plot_id  else None,
            equipment_id=int(equip_id) if equip_id else None,
            logged_by=user_id,
            quantity_used=qty_used,
            log_date=log_date,
            notes=notes or None
        )
        s.add(log)
        s.commit()
        flash(f"Logged {qty_used} {item.unit} of {item.name}. Stock: {item.quantity_on_hand:.1f} {item.unit}", "success")
        if item.reorder_threshold and item.quantity_on_hand <= item.reorder_threshold:
            flash(f"{item.name} is now below reorder threshold.", "warning")
            from reorder_ai import maybe_generate_suggestion
            maybe_generate_suggestion(item, s)
        return redirect(url_for("log_usage"))

    return render_template("log.html",
        page="log",
        inventory=inv, plots=plots, equipment=equip,
        users=users, today_logs=today_logs,
        today=date.today().isoformat(), **ctx)


@app.route("/log/<int:lid>/delete", methods=["POST"])
def log_delete(lid):
    guard = _require_manager_or_admin()
    if guard:
        return guard
    s   = db()
    log = s.query(UsageLog).get(lid)
    if log:
        item_name = log.inventory_item.name if log.inventory_item else "item"
        qty       = log.quantity_used
        unit      = log.inventory_item.unit if log.inventory_item else ""
        s.delete(log)
        s.commit()
        flash(
            f"Log entry removed ({qty} {unit} of {item_name}). "
            "Current stock was not changed — adjust manually if needed.",
            "success"
        )
    return redirect(request.referrer or url_for("log_usage"))


PER_PAGE = 50

@app.route("/history")
def history():
    s   = db()
    ctx = nav_context(s)
    farm = ctx["farm"]

    inv         = s.query(InventoryItem).filter_by(farm_id=farm.id).all() if farm else []
    filter_item = request.args.get("item", "")
    period      = request.args.get("period", "30")
    filter_src  = request.args.get("src", "all")
    page        = max(1, request.args.get("page", 1, type=int))

    q = (s.query(UsageLog)
           .options(joinedload(UsageLog.inventory_item),
                    joinedload(UsageLog.plot),
                    joinedload(UsageLog.equipment),
                    joinedload(UsageLog.logged_by_user))
           .order_by(UsageLog.log_date.desc()))

    if filter_item:
        item_obj = s.query(InventoryItem).filter_by(name=filter_item).first()
        if item_obj:
            q = q.filter(UsageLog.inventory_item_id == item_obj.id)

    if period != "all":
        cutoff = datetime.now() - timedelta(days=int(period))
        q = q.filter(UsageLog.log_date >= cutoff)

    if filter_src == "manual":
        q = q.filter(UsageLog.ai_estimated == False)
    elif filter_src == "ai":
        q = q.filter(UsageLog.ai_estimated == True)

    total_count = q.count()
    logs        = q.offset((page - 1) * PER_PAGE).limit(PER_PAGE).all()
    total_qty   = s.query(UsageLog).with_entities(
        __import__("sqlalchemy").func.sum(UsageLog.quantity_used)
    ).filter(UsageLog.id.in_([l.id for l in logs])).scalar() or 0

    pages = (total_count + PER_PAGE - 1) // PER_PAGE

    return render_template("history.html",
        page="history",
        logs=logs,
        inventory=inv,
        filter_item=filter_item,
        period=period,
        filter_src=filter_src,
        total=total_qty,
        current_page=page,
        pages=pages,
        total_count=total_count,
        **ctx)


@app.route("/history/export")
def history_export():
    s    = db()
    farm = get_farm(s)
    inv  = s.query(InventoryItem).filter_by(farm_id=farm.id).all() if farm else []

    filter_item = request.args.get("item", "")
    period      = request.args.get("period", "30")
    filter_src  = request.args.get("src", "all")

    q = (s.query(UsageLog)
           .options(joinedload(UsageLog.inventory_item),
                    joinedload(UsageLog.plot),
                    joinedload(UsageLog.equipment),
                    joinedload(UsageLog.logged_by_user))
           .order_by(UsageLog.log_date.desc()))

    if filter_item:
        item_obj = s.query(InventoryItem).filter_by(name=filter_item).first()
        if item_obj:
            q = q.filter(UsageLog.inventory_item_id == item_obj.id)

    if period != "all":
        cutoff = datetime.now() - timedelta(days=int(period))
        q = q.filter(UsageLog.log_date >= cutoff)

    if filter_src == "manual":
        q = q.filter(UsageLog.ai_estimated == False)
    elif filter_src == "ai":
        q = q.filter(UsageLog.ai_estimated == True)

    logs = q.all()

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Date", "Item", "Quantity", "Unit", "Plot", "Equipment",
                     "Logged By", "AI Estimated", "Notes"])
    for log in logs:
        writer.writerow([
            log.log_date.strftime("%Y-%m-%d") if log.log_date else "",
            log.inventory_item.name if log.inventory_item else "",
            log.quantity_used,
            log.inventory_item.unit if log.inventory_item else "",
            log.plot.plot_code if log.plot else "",
            log.equipment.name if log.equipment else "",
            log.logged_by_user.name if log.logged_by_user else "",
            "yes" if log.ai_estimated else "no",
            log.notes or "",
        ])

    filename = f"usage_history_{date.today().isoformat()}.csv"
    return Response(
        out.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.route("/users")
def users():
    s    = db()
    ctx  = nav_context(s)
    all_users = s.query(User).order_by(User.role, User.name).all()
    return render_template("users.html", page="users", users=all_users, **ctx)


# ── suggestion routes ──────────────────────────────────────────────────────────

# Simple in-memory rate limit: {user_id: last_refresh_ts}
_refresh_rate_limit: dict = {}
_REFRESH_COOLDOWN_SECS = 300  # 5 minutes


def _require_manager_or_admin():
    """Return a redirect/403 response if the current user lacks the required role.
    Returns None if the user has sufficient privileges."""
    role = flask_session.get("user_role", "")
    if role not in ("admin", "manager"):
        flash("You do not have permission to perform this action.", "error")
        return redirect(request.referrer or url_for("dashboard"))
    return None


@app.route("/suggestions")
def suggestions():
    s   = db()
    ctx = nav_context(s)
    farm = ctx["farm"]
    from reorder_ai import get_active_suggestions
    active = get_active_suggestions(s, farm.id) if farm else []
    resolved = (
        s.query(Notification)
        .filter(
            Notification.status != NotificationStatus.pending,
            Notification.resolved_at >= datetime.now(timezone.utc) - timedelta(days=7),
        )
        .order_by(Notification.resolved_at.desc())
        .limit(20)
        .all()
    ) if farm else []
    return render_template("suggestions.html",
                           page="suggestions",
                           active=active, resolved=resolved, **ctx)


@app.route("/suggestions/<int:nid>/approve", methods=["POST"])
def suggestion_approve(nid):
    guard = _require_manager_or_admin()
    if guard:
        return guard
    s = db()
    from reorder_ai import resolve_suggestion
    resolve_suggestion(nid, "approve", s)
    flash("Reorder suggestion approved.", "success")
    return redirect(request.referrer or url_for("suggestions"))


@app.route("/suggestions/<int:nid>/dismiss", methods=["POST"])
def suggestion_dismiss(nid):
    guard = _require_manager_or_admin()
    if guard:
        return guard
    s = db()
    from reorder_ai import resolve_suggestion
    resolve_suggestion(nid, "dismiss", s)
    flash("Suggestion dismissed.", "success")
    return redirect(request.referrer or url_for("suggestions"))


@app.route("/suggestions/refresh", methods=["POST"])
def suggestions_refresh():
    guard = _require_manager_or_admin()
    if guard:
        return guard

    user_id = flask_session.get("user_id")
    now_ts = datetime.now(timezone.utc).timestamp()
    last = _refresh_rate_limit.get(user_id, 0)
    if now_ts - last < _REFRESH_COOLDOWN_SECS:
        remaining = int(_REFRESH_COOLDOWN_SECS - (now_ts - last))
        flash(f"Please wait {remaining}s before refreshing again.", "warning")
        return redirect(url_for("suggestions"))

    _refresh_rate_limit[user_id] = now_ts

    s   = db()
    ctx = nav_context(s)
    farm = ctx["farm"]
    if not farm:
        return redirect(url_for("suggestions"))

    # Invalidate suggestions older than 1h (mark dismissed)
    stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    stale = (
        s.query(Notification)
        .filter(
            Notification.farm_id == farm.id,
            Notification.status == NotificationStatus.pending,
            Notification.created_at <= stale_cutoff,
        )
        .all()
    )
    for n in stale:
        n.status = NotificationStatus.dismissed
        n.resolved_at = datetime.now(timezone.utc)
    s.commit()

    # Re-generate for all low-stock items
    from reorder_ai import maybe_generate_suggestion
    inv = s.query(InventoryItem).filter_by(farm_id=farm.id).all()
    count = 0
    for item in inv:
        if stock_status(item) in ("critical", "warning"):
            sug = maybe_generate_suggestion(item, s)
            if sug:
                count += 1

    flash(f"Refreshed — {count} suggestion{'s' if count != 1 else ''} generated.", "success")
    return redirect(url_for("suggestions"))


@app.route("/map")
def farm_map():
    import json as _json
    s   = db()
    ctx = nav_context(s)
    farm = ctx["farm"]

    plots = (s.query(Plot)
               .options(
                   joinedload(Plot.field),
                   joinedload(Plot.variety).joinedload(CropVariety.growth_stages),
                   joinedload(Plot.variety).joinedload(CropVariety.species),
                   joinedload(Plot.treatment_plans).joinedload(TreatmentPlan.inventory_item),
                   joinedload(Plot.treatment_plans).joinedload(TreatmentPlan.growth_stage),
               )
               .all())

    inv_map = {}
    if farm:
        for item in s.query(InventoryItem).filter_by(farm_id=farm.id).all():
            inv_map[item.id] = item

    def _days_since(dt):
        if not dt:
            return None
        return (datetime.now() - dt).days

    def _season_pct(plot):
        days = _days_since(plot.planting_date)
        if not days or not plot.variety:
            return 0
        total = plot.variety.season_days or 120
        return min(int(days / total * 100), 100)

    def _current_stage(plot):
        days = _days_since(plot.planting_date)
        if not days or not plot.variety or not plot.variety.growth_stages:
            return None
        stages = sorted(plot.variety.growth_stages, key=lambda g: g.day_offset)
        current = None
        for g in stages:
            if days >= g.day_offset:
                current = g
        return current.stage_code if current else None

    def _upcoming_treatments(plot, days_ahead=21):
        cutoff = datetime.now() + timedelta(days=days_ahead)
        return [t for t in plot.treatment_plans
                if not t.applied and t.planned_date and t.planned_date <= cutoff]

    def _stock_ok(item):
        if not item or not item.reorder_threshold:
            return True
        return item.quantity_on_hand > item.reorder_threshold

    plots_data = []
    for p in plots:
        up = _upcoming_treatments(p)
        has_low_stock = any(
            t.inventory_item_id in inv_map and not _stock_ok(inv_map[t.inventory_item_id])
            for t in up
        )
        species = p.variety.species.common_name if p.variety and p.variety.species else "Unknown"
        plots_data.append({
            "id":           p.id,
            "plot_code":    p.plot_code,
            "field":        p.field.name if p.field else "Unknown",
            "variety":      p.variety.variety_code if p.variety else "—",
            "species":      species,
            "is_exp":       p.variety.is_experimental if p.variety else False,
            "replication":  p.replication,
            "area_ha":      p.area_ha,
            "planting_date": p.planting_date.strftime("%b %d, %Y") if p.planting_date else None,
            "days_in_field": _days_since(p.planting_date),
            "season_pct":   _season_pct(p),
            "stage":        _current_stage(p),
            "has_low_stock": has_low_stock,
            "upcoming": [
                {
                    "item":  t.inventory_item.name if t.inventory_item else "—",
                    "stage": t.growth_stage.stage_code if t.growth_stage else "—",
                    "date":  t.planned_date.strftime("%b %d") if t.planned_date else "—",
                    "qty":   round(t.rate_per_ha * (p.area_ha or 0), 1),
                    "unit":  t.inventory_item.unit if t.inventory_item else "",
                    "low":   t.inventory_item_id in inv_map and not _stock_ok(inv_map[t.inventory_item_id]),
                }
                for t in up
            ],
        })

    return render_template("map.html",
        page="map",
        plots_json=_json.dumps(plots_data),
        **ctx)


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1", "yes")
    app.run(debug=debug, port=5001)
