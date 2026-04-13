# FieldMind

**AI-Powered Research Farm Manager** built for the University of Nebraska-Lincoln (UNL) Department of Biological Systems Engineering.

FieldMind tracks inventory, treatment plans, usage logs, and equipment across research farm plots -- then uses AI to predict stockouts and optimize input scheduling.

---

## What It Does

- **Inventory Management** -- Track fertilizers, herbicides, fungicides, fuel, and seed with reorder thresholds, supplier info, and sparkline consumption trends.
- **Treatment Planning** -- Schedule and track plot-level treatments tied to crop growth stages. Overdue and upcoming treatments surface on the dashboard.
- **Usage Logging** -- 4-step wizard (select item, pick plot, choose equipment, confirm) with AI-estimated quantities. Logs auto-deplete inventory.
- **AI Estimation Engine** -- Google Gemini predicts daily consumption rates, forecasts stockout dates, generates plain-English alerts, and learns from farmer corrections.
- **Interactive Farm Map** -- Plotly-powered plot map with click-for-details and inventory depletion forecast curves.
- **Shapefile Analyzer** -- Upload farm shapefiles to visualize boundaries, color by attribute, and match to database records.
- **History & Export** -- Filterable usage history with CSV export. Tracks manual vs. AI-estimated entries.
- **Role-Based Auth** -- UNL email login with admin/manager/viewer roles and session management.

## Architecture

```
Flask (server.py)          -- Full web app: dashboard, inventory, treatments, logs, history, users
FastAPI (api.py)           -- REST API for the frontend usage logging wizard
Streamlit (ai_engine.py)   -- AI estimation layer (Gemini)
Streamlit (farm_map.py)    -- Interactive farm plot map + depletion forecasts
Streamlit (shapefile_analyzer.py) -- Shapefile upload, parsing, and visualization
SQLAlchemy + SQLite        -- 13-table schema (models.py)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Flask, FastAPI, SQLAlchemy |
| Frontend | Jinja2 templates, Tailwind CSS, vanilla JS |
| AI | Google Gemini (via `google-generativeai`) |
| Visualization | Streamlit, Plotly, Matplotlib |
| Database | SQLite |
| GIS | Geopandas, Shapely, Folium |

## Database Schema

13 tables covering the full research farm domain:

- `users`, `farms`, `farm_members` -- Multi-user access control
- `crop_species`, `crop_varieties`, `growth_stages` -- Crop lifecycle modeling
- `fields`, `plots` -- Spatial hierarchy (farm > field > plot)
- `equipment` -- Tractors, sprayers with fuel/chemical rates
- `inventory_items` -- Stock tracking with reorder logic
- `treatment_plans` -- Growth-stage-linked treatment schedules
- `usage_logs` -- Per-application records with AI estimation flags
- `activity_logs`, `notifications` -- Audit trail and stockout alerts

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js (for the dev server and screenshot tooling)

### Setup

```bash
# Clone
git clone https://github.com/Ishrat2110/fieldmind.git
cd fieldmind

# Install Python dependencies
pip install flask fastapi uvicorn sqlalchemy werkzeug google-generativeai streamlit plotly geopandas shapely folium python-dotenv pydantic

# Install Node dependencies
npm install

# Create .env
echo "GEMINI_API_KEY=your-key-here" > .env
echo "SECRET_KEY=your-secret-key" >> .env

# Initialize and seed the database
python database.py
```

### Run

```bash
# Flask web app (main dashboard)
python server.py
# -> http://localhost:5001

# FastAPI backend (usage logging API)
python api.py
# -> http://localhost:8000

# AI engine (Streamlit)
streamlit run ai_engine.py

# Farm map (Streamlit)
streamlit run farm_map.py

# Shapefile analyzer (Streamlit)
streamlit run shapefile_analyzer.py
```

### Default Login

| Role | NUID | Password |
|------|------|----------|
| Admin | `12345678` | `admin123` |
| Manager | `87654321` | `manager123` |

## Project Structure

```
fieldmind/
├── server.py              # Flask web app (dashboard, inventory, treatments, logs)
├── api.py                 # FastAPI REST API (usage logging wizard)
├── ai_engine.py           # Gemini-powered estimation + alerts (Streamlit)
├── farm_map.py            # Interactive plot map + forecasts (Streamlit)
├── shapefile_analyzer.py  # Shapefile upload + visualization (Streamlit)
├── models.py              # SQLAlchemy schema (13 tables)
├── database.py            # DB init + seed script
├── seed_usage.py          # Additional usage data seeding
├── index.html             # Frontend landing page
├── landing.html           # Marketing/info page
├── templates/             # Jinja2 templates
│   ├── base.html          # Layout with sidebar navigation
│   ├── dashboard.html     # Main dashboard with charts
│   ├── inventory.html     # Inventory management
│   ├── treatments.html    # Treatment plan tracking
│   ├── log.html           # Usage logging form
│   ├── history.html       # Filterable usage history
│   ├── login.html         # Authentication
│   └── users.html         # User management
├── Nebraska_N_RGB.png     # UNL brand mark
└── Nebraska_N_RGB.svg
```

## Seed Data

Running `python database.py` creates a realistic UNL research farm scenario:

- **1 farm** -- UNL Research Farm, East Campus (48.5 ha)
- **10 users** -- Admin, managers, and viewers with UNL emails
- **2 fields** -- Corn trials (Block A) and soybean trials (Block B)
- **16 plots** -- 8 corn + 8 soybean, 2 replications per variety
- **8 crop varieties** -- 4 corn (incl. 2 UNL experimental lines) + 4 soybean
- **7 inventory items** -- Urea, anhydrous ammonia, herbicide, fungicide, diesel, corn seed, soy seed
- **40 treatment plans** -- Growth-stage-linked applications per plot
- **14 days of usage logs** -- Simulated daily diesel consumption and periodic spraying

## License

University of Nebraska-Lincoln -- Academic use.
