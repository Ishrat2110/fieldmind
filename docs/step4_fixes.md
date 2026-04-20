# Step 4 — Frontend Consolidation

Goal: one UI, one source of truth. Flask + Jinja (`server.py` + `templates/`) becomes the only customer-facing app. Streamlit GIS tools (`ai_engine.py`, `farm_map.py`, `shapefile_analyzer.py`) stay as standalone scripts. Everything else competing for the same users/data goes.

I verified before writing this that `server.py` has **zero** imports from the files in the delete list — `api.py`, `app.py`, `index.html`, `landing.html` are all isolated. So the deletions won't break anything Flask does. The Streamlit tools you're keeping import from `database.py` and `models.py`, which stay.

---

## What to delete

| File / Folder | Size | Why it goes |
|---|---|---|
| `index.html` | 1,586 lines | Static HTML frontend — calls FastAPI; we're dropping FastAPI |
| `v2/index.html` | 1,587 lines | Newer static HTML — also calls `http://localhost:8000` (line 1196). Delete the whole `v2/` dir |
| `landing.html` | 293 lines | Standalone marketing page; not wired into Flask |
| `app.py` | 1,175 lines | Original Streamlit dashboard — duplicates the Flask UI (inventory, logs, treatments, auth) |
| `api.py` | 264 lines | FastAPI backend — its only consumer was `index.html` / `v2/`. Flask already handles all the same operations |
| `tests/test_api.py` | 276 lines | Tests for `api.py` |
| `serve.mjs` | — | Node HTTP server for the static HTML |
| `serve2.mjs` | — | Second Node HTTP server (for v2/) |
| `screenshot.mjs` | — | Puppeteer script for screenshots — only useful if you're still generating them for docs. Delete unless you use it |
| `package.json`, `package-lock.json` | — | Only exist for the three `.mjs` files |
| `node_modules/` | — | Only exists for the three `.mjs` files |

Total dead code removed: **~6,600 lines of Python/HTML + the entire Node toolchain**.

### The commands

Run from the project directory (`/Users/ishratjandu/AI_Pitla/Semester_project/farm_manager_step1`):

```bash
# 1. Make a safety commit first, so you can recover if anything goes wrong
git add -A && git commit -m "checkpoint before Step 4 frontend cleanup"

# 2. Delete the files with `git rm` so they leave the index too
git rm index.html
git rm landing.html
git rm app.py
git rm api.py
git rm tests/test_api.py
git rm serve.mjs
git rm serve2.mjs
git rm screenshot.mjs      # skip this line if you still use it for docs screenshots
git rm package.json
git rm package-lock.json
git rm -r v2/

# 3. node_modules/ should already be in .gitignore; just remove from disk
rm -rf node_modules/

# 4. Commit the cleanup
git commit -m "Step 4: remove competing frontends (static HTML, FastAPI, Streamlit app)"
```

---

## What to keep

These are your single source of truth going forward:

```
server.py              # Flask app (port 5001)
templates/             # Jinja templates
database.py            # DB session factory
models.py              # SQLAlchemy models
reorder_ai.py          # Gemini reorder service
tests/                 # Everything except test_api.py
docs/                  # All remediation docs, design docs
.env                   # Secrets (already gitignored)
.env.example           # Template for teammates
.gitignore
README.md
requirements.txt       # (with edits below)
farm_manager.db        # Local dev DB
```

And the standalone Streamlit tools (run individually with `streamlit run <file>`):

```
ai_engine.py           # Gemini-powered query console
farm_map.py            # Field / plot visualization
shapefile_analyzer.py  # Shapefile ingest + analysis
```

---

## `requirements.txt` cleanup

Delete the two packages that only `api.py` used:

**Before**:

```
sqlalchemy>=2.0,<3.0
streamlit>=1.32,<2.0
pandas>=2.0,<3.0
flask>=3.0,<4.0
werkzeug>=3.0,<4.0
python-dotenv>=1.0,<2.0
google-generativeai>=0.7,<1.0
plotly>=5.0,<6.0
geopandas>=0.14,<1.0
folium>=0.16,<1.0
streamlit-folium>=0.18,<1.0
pyogrio>=0.7
fastapi>=0.110,<1.0
uvicorn>=0.29,<1.0
```

**After**:

```
sqlalchemy>=2.0,<3.0
streamlit>=1.32,<2.0
pandas>=2.0,<3.0
flask>=3.0,<4.0
werkzeug>=3.0,<4.0
python-dotenv>=1.0,<2.0
google-generativeai>=0.7,<1.0
plotly>=5.0,<6.0
geopandas>=0.14,<1.0
folium>=0.16,<1.0
streamlit-folium>=0.18,<1.0
pyogrio>=0.7
```

Keep `streamlit` and `streamlit-folium` — the GIS tools still need them.

Don't bother uninstalling `fastapi` / `uvicorn` from your current venv; they'll just go unused. They'll drop out the next time someone sets up the venv from scratch.

---

## `.env` cleanup

The following variables were added in Step 1 specifically for `api.py` and can come out:

**Delete these lines from `.env`**:

```
API_CORS_ORIGINS=http://127.0.0.1:5001
API_HOST=127.0.0.1
API_PORT=8000
```

Also delete the same three from `.env.example`. Leave `FLASK_DEBUG`, `DATABASE_URL`, `SECRET_KEY`, `GEMINI_API_KEY`, and the three `REORDER_AI_*` variables.

---

## README + docs cleanup

Search the README and any top-level docs for mentions of the deleted pieces and either remove them or flag them for a rewrite:

```bash
grep -rn --include="*.md" -e "fastapi\|api.py\|index.html\|app.py.*streamlit\|v2/\|serve.mjs\|port 8000\|:8000" README.md docs/
```

Expected targets:
- Any "Architecture" section listing Flask + FastAPI + Streamlit as three tiers — rewrite as "Flask monolith with optional Streamlit research tools".
- Any "How to run" section with `python api.py` or `npm run serve` — delete those lines.
- The two older design docs in `docs/superpowers/` that reference the usage-logging wizard — either delete them or move them into a `docs/archive/` folder with a note that they describe the now-removed FastAPI wizard.

Your Step 1-3 fix docs mention `api.py` — those are historical records of what you did, leave them as-is.

---

## Verify

```bash
# 1. Flask app starts and runs cleanly with no api.py in sight
python server.py &
sleep 2
curl -s -o /dev/null -w 'flask: %{http_code}\n' http://127.0.0.1:5001/
kill %1

# Expected: flask: 302 (redirect to /login). No ImportError, no ModuleNotFoundError.

# 2. Tests still pass (minus the deleted test_api.py)
pytest tests/ -v
# Expected: test_reorder_ai.py passes, no errors about missing api module.

# 3. Streamlit GIS tools still run standalone
streamlit run farm_map.py &
sleep 3
curl -s -o /dev/null -w 'streamlit: %{http_code}\n' http://127.0.0.1:8501/
kill %1

# Expected: streamlit: 200. The tools don't depend on anything you deleted.

# 4. No dangling imports anywhere
grep -rn --include="*.py" -e "from api import\|import api$\|from app import\|import app$" .
# Expected: no output. If anything matches, investigate before committing.
```

---

## One thing worth noting for the future

You're deleting a working-ish REST API. If you later need Claude/mobile/another team hitting your data programmatically, you'll want an API again. When that happens, don't resurrect the old `api.py` — its known issues (`FARM_ID=1` hardcoded, in-memory session store, separate auth from Flask) are exactly the kind of split-brain problem Step 1 just fixed.

The clean path when the need arises: add Flask-based JSON endpoints to `server.py` under an `/api/v1/` prefix, reusing the same session, same role helper, same DB session. That keeps one app, one auth, one set of routes.

---

## What this buys you

Before: four separate UIs (Jinja, static HTML v1, static HTML v2, Streamlit) drifting against one DB. Security fixes landed in Flask didn't propagate. Adding a feature meant picking a UI and hoping it was the right one.

After: one UI for humans (Flask), three standalone research tools (Streamlit) that read the DB but don't try to be the whole app. Future work has an unambiguous target. Repository shrinks by ~6,600 lines, Node toolchain disappears entirely, `requirements.txt` drops two packages.

Still outstanding after Step 4: CSRF protection, Alembic migrations (so the next schema change doesn't need hand-written SQL), audit logging of who-did-what, and moving the Gemini call off the request path so slow responses don't block the dashboard. Those are Step 5+ territory.
