"""
farm_map.py
-----------
Groundbreaking visual additions to Step 2:
  1. Interactive Farm Plot Map — click any plot for full details
  2. Inventory Depletion Forecast — AI-preview consumption curves

Run alongside app.py or add pages/ directory for multipage Streamlit.
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import folium
from streamlit_folium import st_folium
from database import get_session
from models import (
    Farm, Field, Plot, InventoryItem, UsageLog,
    TreatmentPlan, CropVariety, GrowthStage
)

st.set_page_config(
    page_title="Farm Map — UNL",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
  * { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif !important; }
  .stApp { background: #f8faf9; }
  .stButton > button {
    background: #1F6B3A; color: white; border: none;
    border-radius: 6px; font-weight: 600;
  }
  .stButton > button:hover { background: #174f2b; }
  .topbar {
    background: #1F6B3A; color: white;
    padding: 14px 24px; border-radius: 10px;
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
  .detail-card {
    background: white; border: 1px solid #e0ece4;
    border-left: 4px solid #1F6B3A;
    border-radius: 8px; padding: 16px; margin-bottom: 10px;
  }
  .detail-title { font-weight: 700; font-size: 1rem; color: #1a1a1a; margin-bottom: 6px; }
  .detail-row { font-size: 0.83rem; color: #555; margin: 3px 0; }
  .detail-row strong { color: #1a1a1a; }
  .badge {
    display: inline-block; padding: 2px 10px;
    border-radius: 12px; font-size: 0.72rem; font-weight: 600; margin: 2px;
  }
  .badge-exp    { background: #fff3cd; color: #856404; }
  .badge-comm   { background: #e8f5ee; color: #1F6B3A; }
  .badge-corn   { background: #fff8e6; color: #b45309; }
  .badge-soy    { background: #e6f0ff; color: #1d4ed8; }
  .badge-ok     { background: #e8f5ee; color: #1F6B3A; }
  .badge-low    { background: #fff0e6; color: #c0392b; }
  .stage-bar {
    background: #e8f0eb; border-radius: 6px;
    height: 8px; margin: 6px 0;
    position: relative; overflow: hidden;
  }
  .stage-fill {
    height: 100%; border-radius: 6px;
    background: linear-gradient(to right, #1F6B3A, #4ade80);
    transition: width 0.5s ease;
  }
</style>
""", unsafe_allow_html=True)

# ── DB ──
session = get_session()

def get_all_plots():
    return session.query(Plot).all()

def get_inventory():
    farm = session.query(Farm).first()
    return session.query(InventoryItem).filter_by(farm_id=farm.id).all() if farm else []

def get_recent_logs(item_id, days=30):
    cutoff = datetime.now() - timedelta(days=days)
    return (session.query(UsageLog)
            .filter(UsageLog.inventory_item_id == item_id)
            .filter(UsageLog.log_date >= cutoff)
            .order_by(UsageLog.log_date)
            .all())

def days_since_planting(plot):
    if not plot.planting_date:
        return None
    return (datetime.now() - plot.planting_date).days

def current_stage(plot):
    if not plot.variety or not plot.variety.growth_stages:
        return None, None
    days = days_since_planting(plot)
    if not days:
        return None, None
    stages = sorted(plot.variety.growth_stages, key=lambda s: s.day_offset)
    current = None
    for s in stages:
        if days >= s.day_offset:
            current = s
    next_s = None
    for s in stages:
        if days < s.day_offset:
            next_s = s
            break
    return current, next_s

def stage_progress(plot):
    days = days_since_planting(plot)
    if not days or not plot.variety:
        return 0
    total = plot.variety.season_days or 120
    return min(int((days / total) * 100), 100)

def upcoming_treatments(plot, days_ahead=21):
    cutoff = datetime.now() + timedelta(days=days_ahead)
    return (session.query(TreatmentPlan)
            .filter_by(plot_id=plot.id, applied=False)
            .filter(TreatmentPlan.planned_date <= cutoff)
            .order_by(TreatmentPlan.planned_date)
            .all())

def stock_ok(item):
    if not item.reorder_threshold:
        return True
    return item.quantity_on_hand > item.reorder_threshold

# ── TOP BAR ──
st.markdown("""
<div class="topbar">
  <div>
    <div class="topbar-title">🗺️ Farm Plot Map</div>
    <div class="topbar-sub">UNL East Campus · Interactive Field Layout</div>
  </div>
  <div style="font-size:0.82rem;opacity:0.8">Click any plot to inspect</div>
</div>
""", unsafe_allow_html=True)

plots = get_all_plots()
inventory = get_inventory()
inv_map = {i.id: i for i in inventory}

# ── BUILD MAP DATA ──
# Color palette per variety
VARIETY_COLORS = {}
CORN_PALETTE = ["#f59e0b", "#f97316", "#ef4444", "#dc2626", "#b45309", "#d97706", "#ea580c", "#c2410c"]
SOY_PALETTE  = ["#3b82f6", "#6366f1", "#8b5cf6", "#06b6d4", "#0284c7", "#4f46e5", "#7c3aed", "#0891b2"]

corn_idx = 0
soy_idx  = 0
for p in plots:
    if p.variety_id not in VARIETY_COLORS:
        if p.variety and p.variety.species and p.variety.species.common_name == "Corn":
            VARIETY_COLORS[p.variety_id] = CORN_PALETTE[corn_idx % len(CORN_PALETTE)]
            corn_idx += 1
        else:
            VARIETY_COLORS[p.variety_id] = SOY_PALETTE[soy_idx % len(SOY_PALETTE)]
            soy_idx += 1

# Group plots by field
fields = {}
for p in plots:
    fname = p.field.name if p.field else "Unknown"
    if fname not in fields:
        fields[fname] = []
    fields[fname].append(p)

# ── BUILD PLOTLY FIGURE ──
fig = go.Figure()

# Layout: two fields side by side, 4 cols x 2 rows each
CELL_W, CELL_H = 1.8, 1.2
GAP_X, GAP_Y   = 0.25, 0.25
FIELD_GAP       = 1.2

field_names = list(fields.keys())
all_shapes  = []
annotations = []

for fi, (fname, fplots) in enumerate(fields.items()):
    offset_x = fi * (4 * (CELL_W + GAP_X) + FIELD_GAP)
    fplots_sorted = sorted(fplots, key=lambda p: p.plot_code)

    # Field label background
    fw = 4 * CELL_W + 3 * GAP_X
    fh = 2 * CELL_H + GAP_Y
    all_shapes.append(dict(
        type="rect",
        x0=offset_x - 0.15, y0=-0.35,
        x1=offset_x + fw + 0.15, y1=fh + 0.55,
        fillcolor="rgba(31,107,58,0.04)",
        line=dict(color="rgba(31,107,58,0.2)", width=1.5),
        layer="below"
    ))
    annotations.append(dict(
        x=offset_x + fw/2, y=fh + 0.35,
        text=f"<b>{fname}</b>",
        showarrow=False,
        font=dict(size=13, color="#1F6B3A", family="SF Pro Display"),
        xanchor="center"
    ))

    for i, plot in enumerate(fplots_sorted):
        col = i % 4
        row = i // 4
        x0 = offset_x + col * (CELL_W + GAP_X)
        y0 = row * (CELL_H + GAP_Y)
        x1 = x0 + CELL_W
        y1 = y0 + CELL_H

        color     = VARIETY_COLORS.get(plot.variety_id, "#888")
        progress  = stage_progress(plot)
        curr_s, _ = current_stage(plot)
        days_in   = days_since_planting(plot)

        # Check if any upcoming treatment has low stock
        up_treatments = upcoming_treatments(plot)
        has_low_stock = any(
            t.inventory_item_id in inv_map and not stock_ok(inv_map[t.inventory_item_id])
            for t in up_treatments
        )

        # Plot cell
        all_shapes.append(dict(
            type="rect",
            x0=x0, y0=y0, x1=x1, y1=y1,
            fillcolor="rgba(" + ",".join(str(int(color.lstrip("#")[i:i+2], 16)) for i in (0,2,4)) + ",0.2)",
            line=dict(
                color="#D00000" if has_low_stock else color,
                width=3 if has_low_stock else 1.5
            ),
            layer="below"
        ))

        # Progress bar inside cell — always green so it never looks like a stock alert
        bar_w = (CELL_W - 0.2) * (progress / 100)
        all_shapes.append(dict(
            type="rect",
            x0=x0+0.1, y0=y0+0.08,
            x1=x1-0.1, y1=y0+0.2,
            fillcolor="rgba(0,0,0,0.08)",
            line=dict(width=0),
            layer="below"
        ))
        if bar_w > 0:
            all_shapes.append(dict(
                type="rect",
                x0=x0+0.1, y0=y0+0.08,
                x1=x0+0.1+bar_w, y1=y0+0.2,
                fillcolor="#1F6B3A",
                line=dict(width=0),
                layer="above"
            ))

        # Invisible scatter for hover + click
        variety_code = plot.variety.variety_code if plot.variety else "?"
        species_name = plot.variety.species.common_name if plot.variety and plot.variety.species else "?"
        is_exp       = plot.variety.is_experimental if plot.variety else False
        stage_label  = curr_s.stage_code if curr_s else "—"
        alert_text   = " ⚠️ LOW STOCK" if has_low_stock else ""

        hover = (
            f"<b>{plot.plot_code}</b>{alert_text}<br>"
            f"Variety: {variety_code}<br>"
            f"Species: {species_name}<br>"
            f"Rep: {plot.replication}<br>"
            f"Stage: {stage_label} ({days_in}d)<br>"
            f"Season: {progress}%<br>"
            f"<i>Click to inspect →</i>"
        )

        fig.add_trace(go.Scatter(
            x=[(x0+x1)/2], y=[(y0+y1)/2],
            mode="text",
            text=[f"<b>{plot.plot_code}</b><br><span style='font-size:10px'>{variety_code}</span><br><span style='font-size:9px'>{stage_label}</span>"],
            textfont=dict(size=11, color="#1a1a1a", family="SF Pro Display"),
            hovertemplate=hover + "<extra></extra>",
            customdata=[[plot.id]],
            name=plot.plot_code,
            showlegend=False
        ))

        # Low stock alert marker
        if has_low_stock:
            fig.add_trace(go.Scatter(
                x=[x1-0.15], y=[y1-0.15],
                mode="markers+text",
                marker=dict(color="#D00000", size=12, symbol="circle"),
                text=["!"],
                textfont=dict(size=8, color="white"),
                textposition="middle center",
                hoverinfo="skip",
                showlegend=False
            ))

# Legend
legend_x = 2 * (4 * (CELL_W + GAP_X) + FIELD_GAP) + 0.3
annotations.append(dict(x=legend_x, y=2.8, text="<b>Legend</b>", showarrow=False,
    font=dict(size=12, color="#333", family="SF Pro Display"), xanchor="left"))

legend_items = [
    ("rgba(245,158,11,0.2)", "#f59e0b", "Corn varieties"),
    ("rgba(59,130,246,0.2)", "#3b82f6", "Soybean varieties"),
    ("rgba(208,0,0,0.2)", "#D00000", "⚠️ Low stock alert"),
]
for li, (fill, stroke, label) in enumerate(legend_items):
    lx = legend_x; ly = 2.4 - li * 0.45
    all_shapes.append(dict(type="rect", x0=lx, y0=ly-0.12, x1=lx+0.3, y1=ly+0.12,
        fillcolor=fill, line=dict(color=stroke, width=1.5)))
    annotations.append(dict(x=lx+0.45, y=ly, text=label, showarrow=False,
        font=dict(size=11, color="#444", family="SF Pro Display"), xanchor="left"))

fig.update_layout(
    shapes=all_shapes,
    annotations=annotations,
    xaxis=dict(visible=False, range=[-0.5, legend_x+2]),
    yaxis=dict(visible=False, range=[-0.6, 3.2]),
    margin=dict(l=10, r=10, t=10, b=10),
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    height=420,
    hoverlabel=dict(
        bgcolor="white", bordercolor="#1F6B3A",
        font=dict(family="SF Pro Display", size=12)
    ),
    dragmode=False
)

# ── RENDER MAP ──
col_map, col_detail = st.columns([2.2, 1])

with col_map:
    st.markdown('<div class="section-header">Field Layout — Click a Plot to Inspect</div>', unsafe_allow_html=True)
    selected = st.plotly_chart(fig, use_container_width=True, key="farm_map",
                               on_select="rerun", selection_mode="points")

with col_detail:
    st.markdown('<div class="section-header">Plot Details</div>', unsafe_allow_html=True)

    # Get selected plot
    sel_plot = None
    if selected and selected.get("selection") and selected["selection"].get("points"):
        point = selected["selection"]["points"][0]
        curve = point.get("curve_number", 0)
        # Match by trace index to plot
        visible_traces = [t for t in fig.data if t.showlegend == False and hasattr(t, 'customdata') and t.customdata is not None]
        try:
            sel_id = fig.data[curve].customdata[0][0]
            sel_plot = next((p for p in plots if p.id == sel_id), None)
        except:
            sel_plot = None

    if sel_plot:
        curr_s, next_s = current_stage(sel_plot)
        days_in        = days_since_planting(sel_plot)
        progress       = stage_progress(sel_plot)
        up_treatments  = upcoming_treatments(sel_plot, 21)
        is_exp         = sel_plot.variety.is_experimental if sel_plot.variety else False
        species        = sel_plot.variety.species.common_name if sel_plot.variety and sel_plot.variety.species else "?"

        badge_type = "badge-exp" if is_exp else "badge-comm"
        badge_text = "🧪 Experimental" if is_exp else "Commercial"
        species_badge = "badge-corn" if species == "Corn" else "badge-soy"

        st.markdown(f"""
        <div class="detail-card">
          <div class="detail-title">Plot {sel_plot.plot_code} — Rep {sel_plot.replication}</div>
          <span class="badge {species_badge}">{species}</span>
          <span class="badge {badge_type}">{badge_text}</span>
          <div class="detail-row" style="margin-top:8px"><strong>Variety:</strong> {sel_plot.variety.variety_code if sel_plot.variety else '—'}</div>
          <div class="detail-row"><strong>Field:</strong> {sel_plot.field.name if sel_plot.field else '—'}</div>
          <div class="detail-row"><strong>Area:</strong> {sel_plot.area_ha} ha</div>
          <div class="detail-row"><strong>Planted:</strong> {sel_plot.planting_date.strftime('%b %d, %Y') if sel_plot.planting_date else '—'}</div>
          <div class="detail-row"><strong>Days in field:</strong> {days_in} days</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div class="detail-card">
          <div class="detail-title">Growth Stage</div>
          <div class="detail-row"><strong>Current:</strong> {curr_s.stage_code + ' — ' + curr_s.stage_name if curr_s else 'Not started'}</div>
          <div class="detail-row"><strong>Next:</strong> {next_s.stage_code + ' (day ' + str(next_s.day_offset) + ')' if next_s else 'Harvest'}</div>
          <div class="detail-row" style="margin-top:6px"><strong>Season progress: {progress}%</strong></div>
          <div class="stage-bar"><div class="stage-fill" style="width:{progress}%"></div></div>
        </div>
        """, unsafe_allow_html=True)

        if up_treatments:
            st.markdown('<div class="detail-card"><div class="detail-title">Upcoming Treatments (21 days)</div>', unsafe_allow_html=True)
            for t in up_treatments:
                item = inv_map.get(t.inventory_item_id)
                ok   = stock_ok(item) if item else True
                badge_color = "#1F6B3A" if ok else "#c0392b"
                badge_bg    = "#e8f5ee" if ok else "#fff0e6"
                badge_txt   = "✓ In stock" if ok else "⚠️ Low stock"
                needed = round(t.rate_per_ha * (sel_plot.area_ha or 0), 1)
                unit   = item.unit if item else ""
                stage  = t.growth_stage.stage_code if t.growth_stage else "?"
                iname  = item.name if item else "?"
                date_s = t.planned_date.strftime("%b %d") if t.planned_date else "?"
                st.markdown(
                    f'<div style="margin:6px 0;padding:6px 0;border-bottom:1px solid #f0f0f0">' +
                    f'<span style="font-weight:700">{stage}</span> &mdash; <span style="font-weight:600">{iname}</span><br/>' +
                    f'<span style="font-size:0.78rem;color:#888">{needed} {unit} needed · {date_s}</span>' +
                    f'<span style="margin-left:6px;padding:2px 8px;border-radius:10px;font-size:0.72rem;font-weight:600;background:{badge_bg};color:{badge_color}">{badge_txt}</span></div>',
                    unsafe_allow_html=True
                )
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="detail-card"><div class="detail-row">No treatments due in next 21 days.</div></div>', unsafe_allow_html=True)

    else:
        st.markdown("""
        <div class="detail-card" style="text-align:center;padding:32px 16px;color:#aaa">
          <div style="font-size:2rem;margin-bottom:8px">🗺️</div>
          <div style="font-size:0.9rem">Click any plot on the map<br/>to see its details here</div>
        </div>
        """, unsafe_allow_html=True)


# ════════════════════════════════════════════
# FARM SATELLITE SUBPLOT
# ════════════════════════════════════════════
st.markdown('<div class="section-header">Farm Location — Satellite View</div>', unsafe_allow_html=True)

FARM_LAT  =  40.6012   # 851 US-6, Harvard, NE 68944
FARM_LON  = -98.1056
FARM_ADDR = "851 US-6, Harvard, NE 68944"

col_sat, col_sat_info = st.columns([2.2, 1])

with col_sat:
    sat_map = folium.Map(
        location=[FARM_LAT, FARM_LON],
        zoom_start=15,
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        max_zoom=19,
    )

    # Semi-transparent field boundary box (~200 m radius)
    folium.Rectangle(
        bounds=[[FARM_LAT - 0.0018, FARM_LON - 0.0028],
                [FARM_LAT + 0.0018, FARM_LON + 0.0028]],
        color="#1F6B3A",
        weight=2.5,
        fill=True,
        fill_color="#1F6B3A",
        fill_opacity=0.10,
        tooltip="Farm boundary (approx.)"
    ).add_to(sat_map)

    folium.Marker(
        location=[FARM_LAT, FARM_LON],
        tooltip=FARM_ADDR,
        popup=folium.Popup(
            f"<b>🌾 Harvard Farm</b><br>{FARM_ADDR}",
            max_width=220
        ),
        icon=folium.Icon(color="green", icon="leaf", prefix="fa"),
    ).add_to(sat_map)

    # Labels overlay so field borders are still visible
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
        attr="Esri Labels",
        name="Labels",
        overlay=True,
        opacity=0.7,
    ).add_to(sat_map)

    st_folium(sat_map, width=None, height=380, returned_objects=[])

with col_sat_info:
    st.markdown(f"""
    <div class="detail-card">
      <div class="detail-title">📍 Farm Address</div>
      <div class="detail-row"><strong>{FARM_ADDR}</strong></div>
      <div class="detail-row" style="margin-top:6px">Clay County, Nebraska</div>
      <div class="detail-row">Lat: {FARM_LAT:.4f}°N</div>
      <div class="detail-row">Lon: {abs(FARM_LON):.4f}°W</div>
    </div>
    <div class="detail-card">
      <div class="detail-title">🗺️ Map Layers</div>
      <div class="detail-row">Base: ESRI World Imagery</div>
      <div class="detail-row">Overlay: Place labels</div>
      <div class="detail-row">Marker: Farm pin</div>
      <div class="detail-row" style="margin-top:6px;color:#1F6B3A;font-weight:600">Zoom/pan freely on the map →</div>
    </div>
    """, unsafe_allow_html=True)

# ════════════════════════════════════════════
# DEPLETION FORECAST CHART
# ════════════════════════════════════════════
st.markdown('<div class="section-header">Inventory Depletion Forecast — AI Preview</div>', unsafe_allow_html=True)
st.caption("Based on real usage history. The red dashed line shows where stock hits the reorder threshold.")

inventory = get_inventory()
sel_item_name = st.selectbox(
    "Select inventory item",
    [i.name for i in inventory],
    key="forecast_select"
)
sel_item = next((i for i in inventory if i.name == sel_item_name), None)

if sel_item:
    logs = get_recent_logs(sel_item.id, 60)

    if len(logs) >= 1:
        # Build daily usage series
        log_dates  = [l.log_date for l in logs]
        log_qty    = [l.quantity_used for l in logs]
        total_used = sum(log_qty)
        days_span  = max((log_dates[-1] - log_dates[0]).days, 1) if len(log_dates) > 1 else 1
        avg_per_day = total_used / days_span

        # Project forward 60 days
        today = datetime.now()
        future_days = 60
        forecast_dates = [today + timedelta(days=d) for d in range(future_days+1)]
        forecast_stock = [max(sel_item.quantity_on_hand - avg_per_day * d, 0) for d in range(future_days+1)]

        # Find stockout day
        stockout_day = next((d for d, s in enumerate(forecast_stock) if s <= 0), None)
        threshold_day = next((d for d, s in enumerate(forecast_stock) if s <= (sel_item.reorder_threshold or 0)), None)

        fig2 = go.Figure()

        # Historical usage bars
        if logs:
            fig2.add_trace(go.Bar(
                x=log_dates, y=log_qty,
                name="Daily usage",
                marker_color="rgba(31,107,58,0.3)",
                yaxis="y2",
                hovertemplate="%{y:.1f} " + sel_item.unit + "<extra>Used</extra>"
            ))

        # Forecast line
        fig2.add_trace(go.Scatter(
            x=forecast_dates, y=forecast_stock,
            name="Projected stock",
            line=dict(color="#1F6B3A", width=3),
            fill="tozeroy",
            fillcolor="rgba(31,107,58,0.08)",
            hovertemplate="%{y:.1f} " + sel_item.unit + "<extra>Stock</extra>"
        ))

        # Reorder threshold line
        if sel_item.reorder_threshold:
            fig2.add_hline(
                y=sel_item.reorder_threshold,
                line=dict(color="#D00000", width=2, dash="dash"),
                annotation_text=f"Reorder threshold ({sel_item.reorder_threshold} {sel_item.unit})",
                annotation_position="top right",
                annotation_font=dict(color="#D00000", size=11)
            )

        # Threshold crossing marker
        if threshold_day is not None:
            td = today + timedelta(days=threshold_day)
            fig2.add_trace(go.Scatter(
                x=[td], y=[sel_item.reorder_threshold],
                mode="markers+text",
                marker=dict(color="#D00000", size=14, symbol="circle"),
                text=[f"  ⚠️ Reorder by {td.strftime('%b %d')}"],
                textposition="middle right",
                textfont=dict(color="#D00000", size=12),
                name="Reorder point",
                hovertemplate=f"Reorder needed by {td.strftime('%b %d, %Y')}<extra></extra>"
            ))

        fig2.update_layout(
            xaxis=dict(title="Date", showgrid=True, gridcolor="rgba(0,0,0,0.05)"),
            yaxis=dict(title=f"Stock ({sel_item.unit})", showgrid=True, gridcolor="rgba(0,0,0,0.05)"),
            yaxis2=dict(title="Daily usage", overlaying="y", side="right", showgrid=False),
            plot_bgcolor="white",
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", y=-0.2),
            height=380,
            margin=dict(l=10, r=10, t=20, b=10),
            font=dict(family="SF Pro Display", size=12),
            hoverlabel=dict(bgcolor="white", bordercolor="#1F6B3A",
                           font=dict(family="SF Pro Display", size=12))
        )

        st.plotly_chart(fig2, use_container_width=True)

        # Summary callouts
        c1, c2, c3 = st.columns(3)
        c1.metric("Current Stock",   f"{sel_item.quantity_on_hand:.1f} {sel_item.unit}")
        c2.metric("Avg Daily Usage", f"{avg_per_day:.1f} {sel_item.unit}/day")
        if threshold_day is not None:
            c3.metric("Reorder In",  f"{threshold_day} days",
                      delta=f"{(today + timedelta(days=threshold_day)).strftime('%b %d')}",
                      delta_color="inverse")
        else:
            c3.metric("Reorder In", "Stock healthy ✓")

    else:
        st.info("Not enough usage history yet to generate a forecast. Log some daily usage first.")
        c1, c2, c3 = st.columns(3)
        c1.metric("Current Stock", f"{sel_item.quantity_on_hand:.1f} {sel_item.unit}")
        c2.metric("Reorder At",    f"{sel_item.reorder_threshold} {sel_item.unit}")
        c3.metric("Supplier",       sel_item.supplier or "—")
