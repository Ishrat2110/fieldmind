# Step 2 — Role Enforcement on Mutation Routes

Goal: viewers (role = `viewer`) can browse the app, but cannot mutate inventory, treatments, or usage logs. Only `admin` and `manager` can write.

Right now your `_require_manager_or_admin()` helper in `server.py` (line 752) exists and is used on the three `/suggestions/*` routes. This step applies the same helper to the seven mutation routes that are still unprotected.

---

## The pattern

The helper returns a redirect response when the user lacks permission, and `None` when they're authorized. Insertion looks like this:

```python
@app.route("/whatever", methods=["POST"])
def whatever():
    guard = _require_manager_or_admin()
    if guard:
        return guard
    s = db()
    # ... existing body ...
```

Two lines, always inserted as the first lines inside the function body (right after `def ...():`). Do not put them before route decorators.

---

## The seven routes

Apply the two-line guard insertion to each of these.

### Fix 1 — `server.py:356` `inventory_add`

**Before** (lines 355-357):

```python
@app.route("/inventory/add", methods=["POST"])
def inventory_add():
    s    = db()
```

**After**:

```python
@app.route("/inventory/add", methods=["POST"])
def inventory_add():
    guard = _require_manager_or_admin()
    if guard:
        return guard
    s    = db()
```

### Fix 2 — `server.py:395` `inventory_edit`

**Before** (lines 394-396):

```python
@app.route("/inventory/<int:iid>/edit", methods=["POST"])
def inventory_edit(iid):
    s = db()
```

**After**:

```python
@app.route("/inventory/<int:iid>/edit", methods=["POST"])
def inventory_edit(iid):
    guard = _require_manager_or_admin()
    if guard:
        return guard
    s = db()
```

### Fix 3 — `server.py:437` `inventory_delete`

**Before** (lines 436-438):

```python
@app.route("/inventory/<int:iid>/delete", methods=["POST"])
def inventory_delete(iid):
    s = db()
```

**After**:

```python
@app.route("/inventory/<int:iid>/delete", methods=["POST"])
def inventory_delete(iid):
    guard = _require_manager_or_admin()
    if guard:
        return guard
    s = db()
```

### Fix 4 — `server.py:508` `treatment_apply`

**Before** (lines 507-509):

```python
@app.route("/treatments/<int:tid>/apply", methods=["POST"])
def treatment_apply(tid):
    s = db()
```

**After**:

```python
@app.route("/treatments/<int:tid>/apply", methods=["POST"])
def treatment_apply(tid):
    guard = _require_manager_or_admin()
    if guard:
        return guard
    s = db()
```

### Fix 5 — `server.py:520` `treatment_apply_bulk`

**Before** (lines 519-521):

```python
@app.route("/treatments/apply-bulk", methods=["POST"])
def treatment_apply_bulk():
    s     = db()
```

**After**:

```python
@app.route("/treatments/apply-bulk", methods=["POST"])
def treatment_apply_bulk():
    guard = _require_manager_or_admin()
    if guard:
        return guard
    s     = db()
```

### Fix 6 — `server.py:553` `log_usage` (POST branch only)

This route handles both `GET` (show the form) and `POST` (submit a log). Viewers should be able to *see* the log page but not submit. Put the guard inside the `if request.method == "POST":` branch, not at the top of the function.

**Before** (lines 553-554):

```python
    if request.method == "POST":
        try:
```

**After**:

```python
    if request.method == "POST":
        guard = _require_manager_or_admin()
        if guard:
            return guard
        try:
```

### Fix 7 — `server.py:608` `log_delete`

**Before** (lines 607-609):

```python
@app.route("/log/<int:lid>/delete", methods=["POST"])
def log_delete(lid):
    s   = db()
```

**After**:

```python
@app.route("/log/<int:lid>/delete", methods=["POST"])
def log_delete(lid):
    guard = _require_manager_or_admin()
    if guard:
        return guard
    s   = db()
```

---

## Optional but recommended — hide the buttons in templates

The server-side guards above are the real protection. But viewers will still *see* Add/Edit/Delete/Apply buttons and get a flash error when they click. Cleaner UX: hide the buttons when `current_user_role == 'viewer'`. Your nav_context already passes `current_user_role` to every template (server.py:115), so it's just wrapping existing markup in an `{% if %}` block.

### `templates/inventory.html` — hide the Delete button (around line 124)

**Before**:

```jinja
            <form method="POST" action="{{ url_for('inventory_delete', iid=item.id) }}" style="display:inline;" onsubmit="return confirm('Delete {{ item.name }}? This will also delete all usage logs for this item.')">
              <button class="btn btn-xs btn-danger" type="submit">Delete</button>
            </form>
```

**After**:

```jinja
            {% if current_user_role in ('admin', 'manager') %}
            <form method="POST" action="{{ url_for('inventory_delete', iid=item.id) }}" style="display:inline;" onsubmit="return confirm('Delete {{ item.name }}? This will also delete all usage logs for this item.')">
              <button class="btn btn-xs btn-danger" type="submit">Delete</button>
            </form>
            {% endif %}
```

Do the same wrapping around the Edit button and the Add Item form on the same page — search for `url_for('inventory_edit'` and `url_for('inventory_add'` and wrap each with the same `{% if %}` / `{% endif %}` pair.

### `templates/log.html` — hide the Delete button (around line 95)

**Before**:

```jinja
            <td>
              <form method="POST" action="{{ url_for('log_delete', lid=log.id) }}" onsubmit="return confirm('Delete this log entry and restore stock?')">
                <button class="btn btn-xs btn-danger" type="submit">Delete</button>
              </form>
            </td>
```

**After**:

```jinja
            <td>
              {% if current_user_role in ('admin', 'manager') %}
              <form method="POST" action="{{ url_for('log_delete', lid=log.id) }}" onsubmit="return confirm('Delete this log entry and restore stock?')">
                <button class="btn btn-xs btn-danger" type="submit">Delete</button>
              </form>
              {% else %}
              <span class="muted">—</span>
              {% endif %}
            </td>
```

Also wrap the main "log a usage" form at the top of `log.html` (the one at line 21) in the same `{% if %}` / `{% endif %}` block, replacing the form content with a "View only — contact an admin or manager to log usage" message in the else branch.

### `templates/treatments.html` — hide the Apply buttons

Search for `url_for('treatment_apply'` and `url_for('treatment_apply_bulk'` in `treatments.html` and wrap each matching form with:

```jinja
{% if current_user_role in ('admin', 'manager') %}
...existing form...
{% endif %}
```

---

## Verify

After applying the seven route guards and (optionally) the template gating, do this end-to-end check:

```bash
# 1. Start the app
python server.py

# In two browser tabs (or two private windows), log in as two different users.
# Admin:   ijandu@unl.edu  / admin123
# Viewer:  pnair@unl.edu   / pnair2024   (or any viewer from the seed data)

# 2. As the viewer, try each mutation:
#    - visit /inventory and click Delete on any item
#    - visit /log and submit the usage form
#    - visit /treatments and click Apply on a pending treatment
#
# Expected: red flash message "You do not have permission..." and redirect
#           back to the previous page. No DB change.

# 3. As the admin, repeat the same actions.
#    Expected: all succeed normally.
```

### Quick sanity test without a browser

```bash
# Start the app in background
python server.py &
sleep 2

# Log in as viewer and grab session cookie
curl -s -c /tmp/viewer.cookie \
  -d "email=pnair@unl.edu&password=pnair2024" \
  http://127.0.0.1:5001/login -o /dev/null

# Try to delete inventory item 1 as viewer — should redirect, not delete
curl -s -b /tmp/viewer.cookie -w '\nstatus: %{http_code}\n' \
  -X POST http://127.0.0.1:5001/inventory/1/delete
# Expected: 302 redirect. Then confirm item 1 still exists:
sqlite3 farm_manager.db "SELECT id, name FROM inventory_items WHERE id = 1;"
# Expected: 1 row returned. If the row is gone, the guard is not in place.

kill %1 2>/dev/null
```

---

## What this buys you

Before: the `viewer` role was honorary — viewers could add, edit, delete inventory; apply treatments; log and delete usage records. The role existed in the DB and the nav, but the server didn't enforce it anywhere except on the three `/suggestions/*` routes.

After: write operations are rejected server-side for any non-admin/non-manager, regardless of whether the UI shows the buttons. The template gating (optional) is defense-in-depth — it just stops viewers from being confused by buttons they can't use.

Still not solved in this step: CSRF protection (a malicious page can still POST to your routes if an admin is logged in), and there's no audit log of who attempted what. Those come later.
