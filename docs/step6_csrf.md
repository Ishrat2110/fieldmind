# Step 6 — CSRF Protection

Goal: close the last major web-security gap. Right now, if an admin is logged into the Flask app in one tab and visits a malicious page in another, that page can POST to `/inventory/1/delete` and the browser will happily send the session cookie along with the request. The Step 2 role guards don't help here — the attacker is riding the admin's session, not a viewer's.

Flask-WTF's `CSRFProtect` blocks this by requiring every POST to carry a signed token that only your own pages can mint.

There are three parts: install the package, initialize `CSRFProtect` in `server.py`, and add one hidden input to each of your 18 forms across 7 templates. No route code changes needed — the protection is applied globally by the extension.

---

## 1. Install Flask-WTF

```bash
pip install "flask-wtf>=1.2,<2.0"
```

Then add it to `requirements.txt`. Insert this line under `werkzeug>=3.0,<4.0`:

```
flask-wtf>=1.2,<2.0
```

`flask-wtf` pulls in `wtforms` as a transitive dependency — you don't need to pin it separately.

---

## 2. Initialize `CSRFProtect` in `server.py`

Add the import and the one-line init right after the existing `app.secret_key = _secret` block. `CSRFProtect` needs the secret key to sign tokens, so init has to happen *after* the key is set.

### Fix — `server.py` top of file

**Before** (lines 11-30):

```python
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, g, Response, session as flask_session)
from markupsafe import Markup
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from werkzeug.security import check_password_hash
from database import get_session
from models import (Farm, InventoryItem, UsageLog, Plot, Equipment,
                    User, TreatmentPlan, Notification, NotificationStatus)
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
```

**After**:

```python
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, g, Response, session as flask_session)
from flask_wtf.csrf import CSRFProtect
from markupsafe import Markup
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from werkzeug.security import check_password_hash
from database import get_session
from models import (Farm, InventoryItem, UsageLog, Plot, Equipment,
                    User, TreatmentPlan, Notification, NotificationStatus)
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
```

That's the only code change. From the moment you add `CSRFProtect(app)`, every POST (and PUT/DELETE/PATCH) without a valid `csrf_token` form field gets a 400 Bad Request with "The CSRF token is missing." response.

GET requests are unaffected, so browsing the app still works. Your `/login` form will break until you add the token in step 3 below — so apply step 3 in the same session, don't half-apply this one.

---

## 3. Add the hidden token input to every form

The pattern is one line, inserted as the first child of every `<form method="POST">`:

```jinja
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

That's it. Same line, same spot, 18 times. I've listed every form below so you don't miss one. Line numbers are from your current working tree.

### `templates/base.html`

Two forms.

**Form 1 — logout button (line 1029)**:

```jinja
<form method="POST" action="{{ url_for('logout') }}" style="margin-top:8px;">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <button type="submit" class="btn btn-ghost btn-xs">Sign out</button>
</form>
```

**Form 2 — quick-panel log entry (line 1049)**:

```jinja
<form method="POST" action="{{ url_for('log_usage') }}" class="form-grid">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <div class="field">
    <label>Inventory Item</label>
    ...
```

### `templates/login.html` (line 250)

```jinja
<form method="POST" action="{{ url_for('login') }}">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <div class="field">
    <label>NUID or UNL Email</label>
    ...
```

Note: the login page has no session yet, but `csrf_token()` still works — Flask-WTF creates a session on first access and stores the token there. The login POST then validates it against the same session. No special handling required.

### `templates/dashboard.html`

Three forms.

- **Line 92** — `treatment_apply` (inside the Needs Attention card)
- **Line 189** — `suggestion_approve`
- **Line 192** — `suggestion_dismiss`

Insert the hidden input as the first line inside each form.

### `templates/inventory.html`

Three forms.

- **Line 125** — `inventory_delete` (the Delete button form)
- **Line 143** — `inventory_add` (the Add Item form)
- **Line 190** — `inventory_edit` (the edit modal form)

The edit modal's `action` attribute is set dynamically by JS when you click Edit — that's fine, the hidden token input goes inside the `<form>` and travels with the submit regardless of what `action` is.

### `templates/log.html`

Two forms.

- **Line 22** — `log_usage` (main log form)
- **Line 100** — `log_delete` (Delete button per row)

### `templates/treatments.html`

Five forms. All have the same treatment-apply pattern; same one-line insertion for each.

- **Line 19** — `treatment_apply_bulk` (top action bar)
- **Line 36** — `treatment_apply`
- **Line 69** — `treatment_apply`
- **Line 135** — `treatment_apply`
- **Line 149** — `treatment_apply_bulk`

### `templates/suggestions.html`

Three forms.

- **Line 92** — `suggestions_refresh`
- **Line 144** — `suggestion_approve`
- **Line 147** — `suggestion_dismiss`

---

## 4. Optional — cleaner pattern via a Jinja macro

If you'd rather not repeat the same `<input>` 18 times, define a macro once in `base.html` and call it from every form. Not required, but keeps templates tidier if you add more forms later.

Add at the top of `base.html` (right after `{% block title %}` or the first `<style>` block):

```jinja
{% macro csrf() -%}
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
{%- endmacro %}
```

Then each form becomes:

```jinja
<form method="POST" action="...">
  {{ csrf() }}
  ...
</form>
```

Two characters shorter per form. Pure style preference — if you're staying at 18 forms, the explicit `<input>` line is more grep-able.

---

## 5. Verify

```bash
# 1. Start the app
python server.py &
sleep 2

# 2. GET the login page — should include a csrf_token input now
curl -s http://127.0.0.1:5001/login | grep -c 'name="csrf_token"'
# Expected: 1

# 3. Simulate a CSRF attack — POST without a token.
#    First log in normally to get a session cookie:
curl -s -c /tmp/admin.cookie \
  -d "identifier=ijandu@unl.edu&password=admin123&csrf_token=$(curl -s -c /tmp/admin.cookie http://127.0.0.1:5001/login | grep -oE 'name="csrf_token" value="[^"]+"' | head -1 | cut -d'"' -f4)" \
  http://127.0.0.1:5001/login -o /dev/null

# Now try to delete inventory item 1 with that cookie but NO token:
curl -s -b /tmp/admin.cookie -w '\nstatus: %{http_code}\n' \
  -X POST http://127.0.0.1:5001/inventory/1/delete
# Expected: 400. Body contains "CSRF token is missing". No DB change.

# 4. Confirm the item still exists:
sqlite3 farm_manager.db "SELECT id, name FROM inventory_items WHERE id = 1;"
# Expected: 1 row returned.

# 5. Real browser test — open http://127.0.0.1:5001, log in, click around.
#    Add an inventory item, log a usage, apply a treatment, delete a log.
#    Expected: every form submits normally. If any form 400s with "CSRF token
#    is missing", you missed adding the hidden input to that template.

kill %1 2>/dev/null
```

### Quick sanity grep

Before starting the server, confirm every POST form has a token input:

```bash
# Count POST forms
grep -rn --include="*.html" 'method="POST"' templates/ | wc -l
# Expected: 18

# Count csrf_token inputs in templates
grep -rn --include="*.html" 'name="csrf_token"' templates/ | wc -l
# Expected: 18 (one per form)
```

If the two counts don't match, you missed a form. The grep will show you where the forms are; cross-reference against the `csrf_token` grep to find the gap.

---

## 6. A note on the JSON-ish routes

None of your current routes accept JSON bodies — everything is HTML form posts. If you ever add a `/api/v1/*` JSON endpoint hit by a non-browser client (mobile app, a teammate's script), CSRF protection will reject it too, because browsers-only is the whole point of CSRF tokens.

When that day comes, the right pattern is:

```python
# For a specific route
@csrf.exempt
@app.route("/api/v1/something", methods=["POST"])
def api_something():
    ...
```

Exempting requires the route to have its own auth mechanism (API key, OAuth token, etc.) — don't blanket-exempt anything that relies on cookie-based auth.

For today, every route stays protected. No exemptions.

---

## What this buys you

Before: a logged-in admin visiting any malicious page on the web could have their session silently used to delete inventory, submit usage logs, or apply treatments. The Step 2 role guards didn't help because the attacker had admin privileges.

After: POSTs without a valid, server-signed token are rejected at the extension layer before any route code runs. Legitimate form submits from your own pages include the token automatically. The attack surface for session-riding CSRF attacks goes to zero.

Combined with Steps 1–5, the app now has: fail-loud secrets, shared DB between services, role enforcement, correct stock accounting, safe cascade behavior, one consolidated UI, and CSRF protection. That's a defensible semester submission.

Still outstanding if you ever want to keep going: Alembic migrations (next time the schema changes), audit logging (who did what), async Gemini (Gemini calls off the request path). None of those are security issues — just polish for a longer-lived app.
