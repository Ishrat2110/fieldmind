# Step 1 — Security & Config Fixes

Goal: make the app runnable by someone other than you, without leaking session cookies or opening the API to the internet.

There are six edits across three files. Each one is tiny. Apply them in order, then run the verification commands at the bottom.

**Status of `.env`:** already updated. It now contains a real `SECRET_KEY`, a single `DATABASE_URL`, and new `FLASK_DEBUG` / `API_CORS_ORIGINS` / `API_HOST` / `API_PORT` variables. The code changes below wire those env vars into the app.

---

## Fix 1 — `server.py` line 23: remove the default secret key

The current fallback string `"change-me-in-production"` is identical on every machine. Anyone who knows the default can forge a logged-in session cookie. We want the app to refuse to start if `SECRET_KEY` is missing.

**Before** (line 23):

```python
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
```

**After**:

```python
_secret = os.environ.get("SECRET_KEY")
if not _secret:
    raise RuntimeError(
        "SECRET_KEY is not set. Generate one with "
        "`python -c \"import secrets; print(secrets.token_hex(32))\"` "
        "and put it in your .env file."
    )
app.secret_key = _secret
```

---

## Fix 2 — `server.py` line 854: stop running in debug mode by default

`debug=True` exposes the Werkzeug interactive debugger, which allows arbitrary Python execution if anyone reaches a stack trace page. We want debug mode to be opt-in via env var so production never accidentally runs it.

**Before** (lines 853-854):

```python
if __name__ == "__main__":
    app.run(debug=True, port=5001)
```

**After**:

```python
if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1", "yes")
    app.run(debug=debug, port=5001)
```

When you actively need the debugger, set `FLASK_DEBUG=true` in `.env`. Default is off.

---

## Fix 3 — `database.py` line 26: read `DATABASE_URL` from env

Right now Flask and FastAPI point at different SQLite files. Once both read the same env var, they'll read/write the same database and your stock counts stop disagreeing.

**Before** (line 26):

```python
DATABASE_URL = "sqlite:////Users/ishratjandu/AI_Pitla/results/farm_manager.db"
```

**After**:

```python
import os

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Add it to your .env file, e.g.\n"
        "  DATABASE_URL=sqlite:////Users/ishratjandu/AI_Pitla/"
        "Semester_project/farm_manager_step1/farm_manager.db"
    )
```

Also: add `from dotenv import load_dotenv; load_dotenv()` near the top of `database.py` (right after the module docstring) so it picks up `.env` when run directly as `python database.py`. `server.py` and `api.py` already trigger `load_dotenv` indirectly via imports, but `database.py` is often run standalone.

---

## Fix 4 — `api.py` line 27: drop the custom default path

Same idea as Fix 3. Don't compute a relative path; just fail loudly if the env var isn't there. FastAPI and Flask should read the exact same value.

**Before** (lines 26-29):

```python
# ── DB ────────────────────────────────────────────────────────────────────────
_DEFAULT_DB = Path(__file__).parent.parent.parent / "results" / "farm_manager.db"
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{_DEFAULT_DB}")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
```

**After**:

```python
# ── DB ────────────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Add it to .env — must match the value "
        "used by server.py / database.py so both services share one file."
    )
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
```

You can delete the unused `from pathlib import Path` import if nothing else in `api.py` uses it — check with a quick search.

---

## Fix 5 — `api.py` lines 48-54: lock down CORS

`allow_origins=["*"]` means any website in the world can make authenticated calls to your API from the user's browser. We want it restricted to the Flask origin.

**Before** (lines 48-54):

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**After**:

```python
_origins_env = os.environ.get("API_CORS_ORIGINS", "")
_allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
if not _allowed_origins:
    raise RuntimeError(
        "API_CORS_ORIGINS is empty. Set it in .env to a comma-separated "
        "list of allowed origins, e.g. http://127.0.0.1:5001"
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
```

This also narrows `allow_methods` and `allow_headers` to just what the code actually uses. Wildcards in those fields leak information about your API surface to anyone probing.

---

## Fix 6 — `api.py` line 250: don't bind 0.0.0.0 and don't reload in production

`host="0.0.0.0"` means the API listens on every network interface — anyone on your wifi can hit it. `reload=True` watches files for changes, which you only want during development. We want both controlled by env vars.

**Before** (lines 249-250):

```python
if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
```

**After**:

```python
if __name__ == "__main__":
    host = os.environ.get("API_HOST", "127.0.0.1")
    port = int(os.environ.get("API_PORT", "8000"))
    reload_flag = os.environ.get("API_RELOAD", "false").lower() in ("true", "1", "yes")
    uvicorn.run("api:app", host=host, port=port, reload=reload_flag)
```

Default bind is now `127.0.0.1` (localhost only). Set `API_HOST=0.0.0.0` in `.env` only when you need LAN access. Set `API_RELOAD=true` during active development.

---

## Verify everything

After applying all six edits, from the project directory on your Mac:

```bash
# 1. Confirm .env is loaded correctly
python -c "
from dotenv import load_dotenv; load_dotenv()
import os
for k in ['SECRET_KEY', 'DATABASE_URL', 'GEMINI_API_KEY', 'FLASK_DEBUG', 'API_CORS_ORIGINS', 'API_HOST']:
    v = os.environ.get(k, '(missing)')
    print(f'{k}: {v[:40]}{\"...\" if len(v) > 40 else \"\"}')
"

# 2. Confirm Flask refuses to start with no SECRET_KEY
SECRET_KEY= python -c "import server" 2>&1 | tail -3
# Expected: RuntimeError about SECRET_KEY being unset.

# 3. Confirm Flask starts normally with the real .env
python server.py &
sleep 2
curl -s -o /dev/null -w 'flask: %{http_code}\n' http://127.0.0.1:5001/
kill %1 2>/dev/null
# Expected: flask: 200 or 302 (redirect to /login). NOT a connection error.

# 4. Confirm FastAPI starts on 127.0.0.1 only
python api.py &
sleep 2
curl -s -o /dev/null -w 'localhost: %{http_code}\n' http://127.0.0.1:8000/health
# From another machine on your LAN, this should fail to connect:
# curl http://<your-mac-lan-ip>:8000/health
kill %1 2>/dev/null
# Expected: localhost: 200. LAN call: connection refused.

# 5. Confirm both services read the same DB
python -c "
from dotenv import load_dotenv; load_dotenv()
import os, sqlite3, re
m = re.match(r'sqlite:////(.+)', os.environ['DATABASE_URL'])
path = '/' + m.group(1)
conn = sqlite3.connect(path)
print('DB:', path)
print('inventory rows:', conn.execute('SELECT COUNT(*) FROM inventory_items').fetchone()[0])
"
# Expected: 7 rows (matches what you have in the seeded DB).
```

---

## What this buys you

Before: default session key, any origin can call the API, API exposed to the LAN, Flask and FastAPI writing to different databases, debug mode exposes RCE.

After: sessions are genuinely signed, API only accepts calls from your own Flask origin, API only listens on localhost, both services guaranteed to read the same database, debugger off unless you explicitly opt in.

None of this solves the viewer-role enforcement, stock-accounting, or cascade-delete problems — those are Step 2 and Step 3. But after Step 1 the app is no longer trivially compromiseable on a shared machine, and the two backends agree on state.
