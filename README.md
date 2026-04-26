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
