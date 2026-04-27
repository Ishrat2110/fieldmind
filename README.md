<div align="center">

<img src="Nebraska_N_RGB.png" alt="UNL" width="80" />

# FieldMind

### AI-Powered Research Farm Manager

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-Backend-000000?style=for-the-badge&logo=flask)](https://flask.palletsprojects.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-REST_API-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Gemini](https://img.shields.io/badge/Google_Gemini-AI_Engine-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev)
[![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)
[![UNL](https://img.shields.io/badge/UNL-Biological_Systems_Engineering-D00000?style=for-the-badge)](https://engineering.unl.edu/bse/)

---

*Track inventory, plan treatments, log usage, and predict stockouts across research farm plots — powered by AI.*

Built for the **University of Nebraska–Lincoln** Department of Biological Systems Engineering.

</div>

---

## :sparkles: Features

<table>
<tr>
<td width="50%">

### :package: Inventory Management
Track fertilizers, herbicides, fungicides, fuel, and seed with reorder thresholds, supplier info, unit costs, and 7-day sparkline consumption trends.

### :calendar: Treatment Planning
Schedule plot-level treatments tied to crop growth stages. Overdue and upcoming treatments surface automatically on the dashboard.

### :memo: Usage Logging Wizard
4-step guided flow: select item → pick plot → choose equipment → confirm. AI pre-fills estimated quantities. Logs auto-deplete inventory.

### :bar_chart: History & Export
Filterable usage history with pagination and CSV export. Filter by item, time period, and source (manual vs. AI-estimated).

</td>
<td width="50%">

### :brain: AI Estimation Engine
Google Gemini predicts daily consumption rates, forecasts stockout dates, generates plain-English alerts, and learns from farmer corrections over time.

### :world_map: Interactive Farm Map
Plotly-powered plot visualization — click any plot for variety details, treatment history, and growth stage info. Includes inventory depletion forecast curves.

### :globe_with_meridians: Shapefile Analyzer
Upload farm shapefiles to visualize field boundaries, color polygons by any attribute, view the full attribute table, and match to database records.

### :lock: Role-Based Auth
UNL email authentication with admin / manager / viewer roles, session management, and per-request authorization.

</td>
</tr>
</table>

---

## :building_construction: Architecture

```mermaid
graph TB
    subgraph Frontend
        A[index.html<br/>Landing Page] --> B[Jinja2 Templates<br/>Dashboard · Inventory · Treatments · Logs]
        B --> C[Tailwind CSS + Vanilla JS]
    end

    subgraph Backend
        D[Flask — server.py<br/>Web App · Auth · CRUD]
        E[FastAPI — api.py<br/>REST API · Usage Wizard]
    end

    subgraph AIViz["AI & Visualization"]
        F[Gemini — ai_engine.py<br/>Predictions · Alerts]
        G[Plotly — farm_map.py<br/>Plot Map · Forecasts]
        H[Geopandas — shapefile_analyzer.py<br/>GIS Analysis]
    end

    subgraph Data
        I[(SQLite<br/>13 Tables)]
    end

    B --> D
    A --> E
    D --> I
    E --> I
    F --> I
    G --> I
    H --> I

    style Frontend fill:#fef3c7,stroke:#d97706,color:#000
    style Backend fill:#dbeafe,stroke:#2563eb,color:#000
    style AIViz fill:#ede9fe,stroke:#7c3aed,color:#000
    style Data fill:#dcfce7,stroke:#16a34a,color:#000
```

---

## :toolbox: Tech Stack

<table>
<tr>
<th align="left">Layer</th>
<th align="left">Technology</th>
</tr>
<tr><td><b>Web Server</b></td><td>Flask + Jinja2</td></tr>
<tr><td><b>REST API</b></td><td>FastAPI + Uvicorn + Pydantic</td></tr>
<tr><td><b>AI</b></td><td>Google Gemini <code>google-generativeai</code></td></tr>
<tr><td><b>ORM</b></td><td>SQLAlchemy</td></tr>
<tr><td><b>Database</b></td><td>SQLite</td></tr>
<tr><td><b>Frontend</b></td><td>Tailwind CSS, vanilla JS</td></tr>
<tr><td><b>Visualization</b></td><td>Streamlit, Plotly, Matplotlib</td></tr>
<tr><td><b>GIS</b></td><td>Geopandas, Shapely, Folium</td></tr>
</table>

---

## :rocket: Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+

### Installation

```bash
# Clone the repo
git clone https://github.com/Ishrat2110/fieldmind.git
cd fieldmind

# Install Python dependencies
pip install flask fastapi uvicorn sqlalchemy werkzeug \
    google-generativeai streamlit plotly geopandas shapely \
    folium python-dotenv pydantic

# Install Node dependencies
npm install

# Set up environment variables
cp .env.example .env
# Then edit .env with your API keys
```

### Environment Variables

| Variable | Description |
|----------|------------|
| `GEMINI_API_KEY` | Google Gemini API key for AI predictions |
| `SECRET_KEY` | Flask session secret |

### Initialize Database

```bash
python database.py
```

> Seeds a realistic UNL research farm: 10 users, 2 fields, 16 plots, 8 crop varieties, 7 inventory items, 40 treatment plans, and 14 days of usage history.

### Run

| Service | Command | URL |
|---------|---------|-----|
| :globe_with_meridians: **Web App** | `python server.py` | `http://localhost:5001` |
| :zap: **REST API** | `python api.py` | `http://localhost:8000` |
| :brain: **AI Engine** | `streamlit run ai_engine.py` | `http://localhost:8501` |
| :world_map: **Farm Map** | `streamlit run farm_map.py` | `http://localhost:8502` |
| :satellite: **Shapefile Analyzer** | `streamlit run shapefile_analyzer.py` | `http://localhost:8503` |

### Default Credentials

| Role | NUID | Password |
|------|------|----------|
| :red_circle: Admin | `12345678` | `admin123` |
| :large_blue_circle: Manager | `87654321` | `manager123` |

---

## :card_file_box: Database Schema

13 tables organized into four domains:

```
Users & Access          Crops & Land             Inputs & Equipment       Tracking
─────────────          ──────────────           ──────────────────       ────────
users                  crop_species             inventory_items          usage_logs
farms                  crop_varieties           equipment                treatment_plans
farm_members           growth_stages                                     activity_logs
                       fields                                            notifications
                       plots
```

---

## :file_folder: Project Structure

```
fieldmind/
│
├── server.py                  # Flask web app
├── api.py                     # FastAPI REST endpoints
├── models.py                  # SQLAlchemy models (13 tables)
├── database.py                # DB init + seed script
│
├── ai_engine.py               # Gemini AI predictions (Streamlit)
├── farm_map.py                # Interactive plot map (Streamlit)
├── shapefile_analyzer.py      # GIS shapefile tool (Streamlit)
├── seed_usage.py              # Extra usage data seeding
│
├── index.html                 # Frontend landing page
├── landing.html               # Info page
├── templates/
│   ├── base.html              # Sidebar layout
│   ├── dashboard.html         # Main dashboard + charts
│   ├── inventory.html         # Stock management
│   ├── treatments.html        # Treatment schedules
│   ├── log.html               # Usage logging form
│   ├── history.html           # Usage history + export
│   ├── login.html             # Authentication
│   └── users.html             # User management
│
├── Nebraska_N_RGB.png         # UNL brand mark
├── Nebraska_N_RGB.svg
└── .gitignore
```

---

<div align="center">

### Built at the University of Nebraska–Lincoln

Department of Biological Systems Engineering

<img src="Nebraska_N_RGB.png" alt="UNL" width="40" />

</div>
