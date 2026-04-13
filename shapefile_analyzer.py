"""
shapefile_analyzer.py
---------------------
Drop any farm shapefile and this page will:
  1. Parse the geometry and attributes
  2. Render an interactive map with plot/field boundaries
  3. Color polygons by any attribute (variety, crop, treatment, etc.)
  4. Show a full attribute table
  5. Match detected fields/plots to the database if names align
  6. Export a summary report

Run with:
    streamlit run shapefile_analyzer.py
"""

import streamlit as st
import os
import json
import tempfile
import zipfile
from pathlib import Path

st.set_page_config(
    page_title="Shapefile Analyzer — UNL Farm",
    page_icon="🗺️",
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
    color: white; padding: 16px 24px; border-radius: 10px; margin-bottom: 20px;
    display: flex; justify-content: space-between; align-items: center;
  }
  .topbar-title { font-size: 1.3rem; font-weight: 800; }
  .topbar-sub   { font-size: 0.82rem; opacity: 0.7; margin-top: 2px; }
  .section-header {
    font-size: 1.05rem; font-weight: 700; color: #1F6B3A;
    border-bottom: 2px solid #1F6B3A;
    padding-bottom: 5px; margin: 20px 0 14px 0;
  }
  .info-card {
    background: white; border: 1px solid #e0ece4;
    border-left: 4px solid #1F6B3A;
    border-radius: 8px; padding: 16px; margin-bottom: 12px;
  }
  .drop-zone {
    background: white; border: 2px dashed #b7d4c0;
    border-radius: 12px; padding: 48px 24px;
    text-align: center; color: #888;
  }
  .drop-zone-title { font-size: 1.1rem; font-weight: 600; color: #555; margin-bottom: 8px; }
  .drop-zone-sub   { font-size: 0.85rem; color: #aaa; }
  .stat-box {
    background: white; border: 1px solid #e0ece4;
    border-radius: 8px; padding: 14px; text-align: center;
  }
  .stat-val { font-size: 1.6rem; font-weight: 700; color: #1F6B3A; }
  .stat-lbl { font-size: 0.72rem; color: #888; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 2px; }
</style>
""", unsafe_allow_html=True)

# ── TOP BAR ──────────────────────────────────
st.markdown("""
<div class="topbar">
  <div>
    <div class="topbar-title">📐 Shapefile Analyzer</div>
    <div class="topbar-sub">Drop any farm shapefile to visualize and analyze field boundaries</div>
  </div>
  <div style="font-size:0.82rem;opacity:0.8">UNL East Campus</div>
</div>
""", unsafe_allow_html=True)

# ── DEPENDENCY CHECK ─────────────────────────
@st.cache_resource
def check_deps():
    missing = []
    try:
        import geopandas
    except ImportError:
        missing.append("geopandas")
    try:
        import folium
    except ImportError:
        missing.append("folium")
    try:
        import streamlit_folium
    except ImportError:
        missing.append("streamlit-folium")
    return missing

missing = check_deps()
if missing:
    st.error(f"Missing packages: {', '.join(missing)}")
    st.code(f"pip install {' '.join(missing)}")
    st.stop()

import geopandas as gpd
import folium
from streamlit_folium import st_folium
import pandas as pd

# ── FILE UPLOAD ──────────────────────────────
st.markdown('<div class="section-header">Upload Shapefile</div>', unsafe_allow_html=True)

st.markdown("""
<div class="drop-zone">
  <div class="drop-zone-title">Drop your shapefile here</div>
  <div class="drop-zone-sub">
    Upload a .zip containing .shp, .dbf, .shx (and optionally .prj)<br/>
    or upload the .shp, .dbf, and .shx files together
  </div>
</div>
""", unsafe_allow_html=True)

uploaded = st.file_uploader(
    "Choose shapefile",
    type=["zip", "shp"],
    accept_multiple_files=True,
    label_visibility="collapsed"
)

def load_shapefile(files):
    """
    Accepts either:
      - A single .zip file containing the shapefile components
      - Multiple files (.shp, .dbf, .shx, .prj)
    Returns a GeoDataFrame.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        for f in files:
            fpath = Path(tmpdir) / f.name
            fpath.write_bytes(f.read())

        # If zip, extract it
        zips = list(Path(tmpdir).glob("*.zip"))
        if zips:
            with zipfile.ZipFile(zips[0], 'r') as z:
                z.extractall(tmpdir)

        # Find .shp file
        shps = list(Path(tmpdir).glob("**/*.shp"))
        if not shps:
            return None, "No .shp file found. Make sure your zip contains a .shp file."

        gdf = gpd.read_file(shps[0])
        return gdf, None

if uploaded:
    gdf, error = load_shapefile(uploaded)

    if error:
        st.error(error)
        st.stop()

    if gdf is None or gdf.empty:
        st.error("Could not read shapefile or file is empty.")
        st.stop()

    # ── REPROJECT TO WGS84 ──────────────────
    if gdf.crs is None:
        st.warning("No CRS found in shapefile. Assuming WGS84 (EPSG:4326).")
        gdf = gdf.set_crs("EPSG:4326")
    else:
        gdf = gdf.to_crs("EPSG:4326")

    # ── STATS ────────────────────────────────
    st.markdown('<div class="section-header">File Summary</div>', unsafe_allow_html=True)

    total_area = 0
    try:
        gdf_proj = gdf.to_crs(gdf.estimate_utm_crs())
        total_area = gdf_proj.geometry.area.sum() / 10000  # m² to ha
    except:
        pass

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f'<div class="stat-box"><div class="stat-val">{len(gdf)}</div><div class="stat-lbl">Features</div></div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="stat-box"><div class="stat-val">{gdf.geometry.geom_type.unique()[0]}</div><div class="stat-lbl">Geometry Type</div></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="stat-box"><div class="stat-val">{len(gdf.columns)-1}</div><div class="stat-lbl">Attributes</div></div>', unsafe_allow_html=True)
    c4.markdown(f'<div class="stat-box"><div class="stat-val">{total_area:.1f} ha</div><div class="stat-lbl">Total Area</div></div>', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="info-card" style="margin-top:12px">
      <div style="font-size:0.82rem;color:#555">
        <strong>CRS:</strong> {gdf.crs.name if gdf.crs else "Unknown"} &nbsp;|&nbsp;
        <strong>Columns:</strong> {", ".join([c for c in gdf.columns if c != "geometry"])}
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── COLOR BY ATTRIBUTE ───────────────────
    st.markdown('<div class="section-header">Map Visualization</div>', unsafe_allow_html=True)

    non_geom_cols = [c for c in gdf.columns if c != "geometry"]
    color_col = None

    if non_geom_cols:
        col1, col2 = st.columns([2, 1])
        color_col = col1.selectbox(
            "Color plots by attribute",
            ["None"] + non_geom_cols,
            help="Choose an attribute to color-code the map (variety, crop type, treatment, etc.)"
        )
        if color_col == "None":
            color_col = None

    # ── BUILD FOLIUM MAP ─────────────────────
    bounds   = gdf.total_bounds  # [minx, miny, maxx, maxy]
    center_y = (bounds[1] + bounds[3]) / 2
    center_x = (bounds[0] + bounds[2]) / 2

    m = folium.Map(
        location=[center_y, center_x],
        zoom_start=16,
        tiles="Esri.WorldImagery",
        attr="Esri"
    )

    # Add satellite + labels tile layer
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Satellite",
        overlay=False,
        control=True
    ).add_to(m)

    folium.TileLayer("OpenStreetMap", name="Street Map").add_to(m)

    # Build color mapping
    COLOR_PALETTE = [
        "#e74c3c","#3498db","#2ecc71","#f39c12","#9b59b6",
        "#1abc9c","#e67e22","#e91e63","#00bcd4","#8bc34a",
        "#ff5722","#607d8b","#795548","#ff9800","#673ab7"
    ]

    color_map = {}
    if color_col and color_col in gdf.columns:
        unique_vals = gdf[color_col].dropna().unique()
        for i, val in enumerate(unique_vals):
            color_map[str(val)] = COLOR_PALETTE[i % len(COLOR_PALETTE)]

    # Add polygons
    for idx, row in gdf.iterrows():
        if row.geometry is None:
            continue

        # Pick color
        if color_col and color_col in gdf.columns:
            val = str(row[color_col]) if pd.notna(row[color_col]) else "Unknown"
            fill_color = color_map.get(val, "#888888")
        else:
            fill_color = "#1F6B3A"

        # Build popup content
        popup_html = "<div style='font-family:sans-serif;font-size:13px;min-width:160px'>"
        popup_html += f"<div style='font-weight:700;margin-bottom:6px;color:#1F6B3A'>Feature {idx}</div>"
        for col in non_geom_cols:
            val = row[col]
            if pd.notna(val):
                popup_html += f"<div><strong>{col}:</strong> {val}</div>"
        popup_html += "</div>"

        # Area
        try:
            area_ha = gdf_proj.iloc[idx].geometry.area / 10000
            popup_html += f"<div><strong>Area:</strong> {area_ha:.2f} ha</div>"
        except:
            pass

        popup_html += "</div>"

        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda x, fc=fill_color: {
                "fillColor": fc,
                "color": "white",
                "weight": 1.5,
                "fillOpacity": 0.6
            },
            highlight_function=lambda x: {
                "fillOpacity": 0.9,
                "weight": 3,
                "color": "white"
            },
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=str(row[non_geom_cols[0]]) if non_geom_cols else f"Feature {idx}"
        ).add_to(m)

    # Legend
    if color_map:
        legend_html = """
        <div style="position:fixed;bottom:30px;right:30px;z-index:1000;
                    background:white;padding:14px;border-radius:8px;
                    border:1px solid #ccc;font-family:sans-serif;font-size:12px;
                    max-height:300px;overflow-y:auto;box-shadow:0 2px 8px rgba(0,0,0,0.15)">
          <div style="font-weight:700;margin-bottom:8px;color:#1F6B3A">Legend</div>
        """
        for val, color in list(color_map.items())[:15]:
            legend_html += f"""
            <div style="display:flex;align-items:center;gap:8px;margin:4px 0">
              <div style="width:14px;height:14px;border-radius:3px;background:{color};flex-shrink:0"></div>
              <span style="color:#333">{val}</span>
            </div>"""
        if len(color_map) > 15:
            legend_html += f"<div style='color:#888;margin-top:4px'>+{len(color_map)-15} more</div>"
        legend_html += "</div>"
        m.get_root().html.add_child(folium.Element(legend_html))

    folium.LayerControl().add_to(m)
    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])

    map_data = st_folium(m, use_container_width=True, height=520)

    # ── CLICKED FEATURE DETAIL ───────────────
    if map_data and map_data.get("last_object_clicked_popup"):
        st.markdown('<div class="section-header">Selected Feature</div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div class="info-card">{map_data["last_object_clicked_popup"]}</div>
        """, unsafe_allow_html=True)

    # ── ATTRIBUTE TABLE ──────────────────────
    st.markdown('<div class="section-header">Attribute Table</div>', unsafe_allow_html=True)

    display_df = gdf.drop(columns=["geometry"]).copy()

    # Add computed area column
    try:
        display_df["area_ha"] = (gdf_proj.geometry.area / 10000).round(3)
    except:
        pass

    st.dataframe(display_df, use_container_width=True, hide_index=False)

    # ── MATCH TO DATABASE ────────────────────
    st.markdown('<div class="section-header">Match to Farm Database</div>', unsafe_allow_html=True)
    st.caption("If your shapefile contains a plot code or field name column that matches the database, select it below to link the geometry to your farm records.")

    col1, col2 = st.columns(2)
    match_col = col1.selectbox("Shapefile column to match on", ["None"] + non_geom_cols)

    if match_col != "None":
        from database import get_session
        from models import Plot, Field

        db = get_session()
        plots  = db.query(Plot).all()
        fields = db.query(Field).all()

        plot_codes  = {p.plot_code: p for p in plots}
        field_names = {f.name: f for f in fields}

        shp_values  = gdf[match_col].astype(str).tolist()
        matched_plots  = [v for v in shp_values if v in plot_codes]
        matched_fields = [v for v in shp_values if v in field_names]

        col2.metric("Plots matched",  f"{len(matched_plots)} / {len(shp_values)}")

        if matched_plots:
            st.success(f"Matched {len(matched_plots)} shapefile features to database plots: {', '.join(matched_plots[:10])}")
        elif matched_fields:
            st.success(f"Matched {len(matched_fields)} shapefile features to database fields.")
        else:
            st.info("No matches found. Make sure the shapefile values match your plot codes (e.g. 'A-01', 'B-04') or field names.")

    # ── EXPORT ───────────────────────────────
    st.markdown('<div class="section-header">Export</div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)

    # GeoJSON export
    geojson_str = gdf.to_json()
    col1.download_button(
        "Download as GeoJSON",
        data=geojson_str,
        file_name="farm_shapefile.geojson",
        mime="application/json"
    )

    # CSV export
    csv_str = display_df.to_csv(index=False)
    col2.download_button(
        "Download Attribute Table (CSV)",
        data=csv_str,
        file_name="farm_attributes.csv",
        mime="text/csv"
    )

else:
    # ── EMPTY STATE ──────────────────────────
    st.markdown("""
    <div style="background:white;border:1px solid #e0ece4;border-radius:12px;
                padding:48px 24px;text-align:center;color:#aaa;margin-top:12px">
      <div style="font-size:3rem;margin-bottom:16px">📂</div>
      <div style="font-size:1rem;font-weight:600;color:#555;margin-bottom:8px">No shapefile loaded</div>
      <div style="font-size:0.85rem;color:#aaa;max-width:400px;margin:0 auto">
        Upload a .zip file containing your .shp, .dbf, and .shx files above.<br/>
        Once loaded, you will see your field boundaries on an interactive satellite map
        with full attribute inspection and database matching.
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── WHAT TO EXPECT ───────────────────────
    st.markdown('<div class="section-header">What This Page Does</div>', unsafe_allow_html=True)
    cols = st.columns(3)
    cols[0].markdown("""
    <div class="info-card">
      <div style="font-size:1.5rem;margin-bottom:8px">🛰️</div>
      <div style="font-weight:700;margin-bottom:4px">Satellite Map</div>
      <div style="font-size:0.82rem;color:#555">Renders your actual field and plot boundaries on a satellite basemap. Click any polygon to inspect its attributes.</div>
    </div>
    """, unsafe_allow_html=True)
    cols[1].markdown("""
    <div class="info-card">
      <div style="font-size:1.5rem;margin-bottom:8px">🎨</div>
      <div style="font-weight:700;margin-bottom:4px">Color by Attribute</div>
      <div style="font-size:0.82rem;color:#555">Color-code plots by variety, crop type, treatment, or any field in your shapefile. Auto-generates a legend.</div>
    </div>
    """, unsafe_allow_html=True)
    cols[2].markdown("""
    <div class="info-card">
      <div style="font-size:1.5rem;margin-bottom:8px">🔗</div>
      <div style="font-weight:700;margin-bottom:4px">Database Matching</div>
      <div style="font-size:0.82rem;color:#555">Links shapefile features to your farm database by plot code or field name, connecting geometry to inventory and treatment data.</div>
    </div>
    """, unsafe_allow_html=True)
