# Step 3 — Stock Accounting & History Preservation

Goal: stop the app from silently corrupting inventory quantities, and stop it from destroying historical usage logs when an inventory item is removed. The reorder-AI pipeline depends on that history, so this also protects the work from Step 1.

Three bugs to fix, each with a specific pathology:

| # | File | Bug |
|---|------|-----|
| 1 | `server.py:598` | `log_usage` silently clamps stock to 0 on oversize logs instead of rejecting |
| 2 | `server.py:636` | `log_delete` unconditionally re-adds logged quantity to current stock, double-counting after any restock |
| 3 | `models.py:269-270` + `:312` | Deleting an `InventoryItem` cascades and destroys every `UsageLog` row for that item |

---

## Fix 1 — `server.py:598`: reject oversize usage logs

### Why this matters

Right now `log_usage` does:

```python
item.quantity_on_hand = max(0, item.quantity_on_hand - qty_used)
```

If stock is 10 and someone logs 500, stock becomes 0 — but the `UsageLog` row still records 500 units used. Your history shows 500 consumed, your stock pretends nothing's wrong, the reorder-AI's burn-rate calculation inflates, and the usage total doesn't tie back to stock changes. A fat-fingered entry quietly corrupts the audit trail.

### The edit

**Before** (lines 593-598):

```python
        item = s.query(InventoryItem).get(item_id)
        if not item:
            flash("Inventory item not found.", "error")
            return redirect(url_for("log_usage"))

        item.quantity_on_hand = max(0, item.quantity_on_hand - qty_used)
```

**After**:

```python
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
```

The FastAPI endpoint (`api.py:201-205`) already does this correctly — you're just bringing the Flask path in line.

---

## Fix 2 — `server.py:636`: don't restore stock on log deletion

### Why this matters

When you delete a usage log, the code adds the logged quantity back to current stock. That only works if stock hasn't moved between the original log and the delete. Consider:

1. Stock starts at 500 L of herbicide.
2. Someone logs 100 L used → stock drops to 400.
3. A shipment arrives → someone restocks by adding 200 L → stock is now 600.
4. The original log was wrong; delete it.
5. With current code: stock becomes 600 + 100 = **700** (wrong — the 100 L really *was* used, the restock already accounted for reality).

The "stock restore" pattern assumes the log is the last thing that happened to the inventory item. It rarely is.

### The cleaner behavior

Deleting a log is a history correction, not a physical reversal. It should:
- Remove the log row (audit trail: who deleted what, when — out of scope for this step).
- Leave current stock alone.
- Warn the user they may need to manually correct the stock count if the log was wrong.

### The edit

**Before** (lines 625-640):

```python
@app.route("/log/<int:lid>/delete", methods=["POST"])
def log_delete(lid):
    guard = _require_manager_or_admin()
    if guard:
        return guard
    s   = db()
    log = s.query(UsageLog).get(lid)
    if log:
        # restore stock
        item = log.inventory_item
        if item:
            item.quantity_on_hand += log.quantity_used
        s.delete(log)
        s.commit()
        flash("Log entry deleted and stock restored.", "success")
    return redirect(request.referrer or url_for("log_usage"))
```

**After**:

```python
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
```

If you find yourself wanting to "undo" recent logs often, the proper answer is a separate "correct entry" action that edits the log's quantity and applies the delta to stock, not a delete+restore. That's out of scope for Step 3.

---

## Fix 3 — `models.py`: stop deleting usage history when an inventory item is removed

### Why this matters

Right now, `InventoryItem.usage_logs` cascades `delete-orphan`, and `UsageLog.inventory_item_id` has `ondelete="CASCADE"` at the DB level. So deleting one inventory item — say, "Roundup PowerMAX" — silently destroys every log that mentions it. Two years of spraying records, gone.

The reorder-AI's burn-rate calculation (`reorder_ai._burn_rate`) reads those logs. So every inventory delete quietly poisons every future reorder suggestion. It also destroys audit history that research data will probably need to reference.

### The approach

Three model changes, one route change, and a one-time database migration:

1. Change the ORM cascade so SQLAlchemy does not auto-delete logs.
2. Change the FK `ondelete` from `CASCADE` to `RESTRICT` so the DB also refuses.
3. Update `inventory_delete` to handle the restriction gracefully — if logs exist, show a message instead of erroring out.
4. Apply the schema change (SQLite specifics below).

### Model edits

**`models.py` — `InventoryItem.usage_logs` relationship (lines 269-270)**

**Before**:

```python
    usage_logs = relationship("UsageLog", back_populates="inventory_item",
                              cascade="all, delete-orphan")
```

**After**:

```python
    usage_logs = relationship("UsageLog", back_populates="inventory_item",
                              passive_deletes=True)
```

`passive_deletes=True` tells SQLAlchemy not to manage the delete chain in Python — the DB enforces it instead.

**`models.py` — `UsageLog.inventory_item_id` column (line 312)**

**Before**:

```python
    inventory_item_id     = Column(Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"),  nullable=False)
```

**After**:

```python
    inventory_item_id     = Column(Integer, ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False)
```

### Route edit

**`server.py:443` — `inventory_delete`**

Currently if someone tries to delete an item that has usage logs, SQLAlchemy will raise an IntegrityError. We want to catch that and show a friendly message.

Read the existing function first to see the exact shape, then replace the `s.delete(item); s.commit()` lines with a try/except that catches `IntegrityError`:

**Before** (around lines 443-460 — open the file and find your actual `inventory_delete` body):

```python
@app.route("/inventory/<int:iid>/delete", methods=["POST"])
def inventory_delete(iid):
    guard = _require_manager_or_admin()
    if guard:
        return guard
    s = db()
    item = s.query(InventoryItem).get(iid)
    if item:
        s.delete(item)
        s.commit()
        flash(f"Deleted {item.name}.", "success")
    return redirect(url_for("inventory"))
```

**After**:

```python
@app.route("/inventory/<int:iid>/delete", methods=["POST"])
def inventory_delete(iid):
    guard = _require_manager_or_admin()
    if guard:
        return guard
    s = db()
    item = s.query(InventoryItem).get(iid)
    if not item:
        return redirect(url_for("inventory"))

    # Refuse delete if usage history exists — research data must be preserved.
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
```

Compare the *before* to what's actually in your file — the function body may have extra handling that I'm not seeing. The key insertion is the `log_count` check between "item exists" and `s.delete(item)`. Everything else stays.

Also update `templates/inventory.html` — the delete-button confirm text still says "*This will also delete all usage logs for this item.*" That's no longer true. Change to:

```jinja
onsubmit="return confirm('Delete {{ item.name }}? Only allowed if no usage logs reference it.')"
```

### Applying the schema change

SQLite doesn't support `ALTER TABLE ... ALTER COLUMN`, so you can't change a foreign-key `ondelete` rule in place. Two realistic options:

**Option A (easiest, fine if you don't mind re-seeding):**

```bash
cd /Users/ishratjandu/AI_Pitla/Semester_project/farm_manager_step1
python database.py --force
```

This drops every table, recreates them with the new schema, and re-runs the seed. Any logs you hand-added in the UI are gone, but all the seeded trials, plots, and historical usage logs come back.

**Option B (preserve current data):**

```bash
# From the project directory, with .env loaded
python -c "
from dotenv import load_dotenv; load_dotenv()
import os, re, sqlite3
m = re.match(r'sqlite:////(.+)', os.environ['DATABASE_URL'])
db_path = '/' + m.group(1)
conn = sqlite3.connect(db_path)
conn.executescript('''
PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

-- Rebuild usage_logs with ondelete=RESTRICT on inventory_item_id
CREATE TABLE usage_logs_new (
    id INTEGER PRIMARY KEY,
    inventory_item_id INTEGER NOT NULL REFERENCES inventory_items(id) ON DELETE RESTRICT,
    plot_id INTEGER REFERENCES plots(id) ON DELETE SET NULL,
    equipment_id INTEGER REFERENCES equipment(id) ON DELETE SET NULL,
    logged_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    quantity_used REAL NOT NULL,
    log_date DATETIME,
    ai_estimated BOOLEAN,
    ai_estimate_corrected BOOLEAN,
    notes TEXT
);
INSERT INTO usage_logs_new SELECT * FROM usage_logs;
DROP TABLE usage_logs;
ALTER TABLE usage_logs_new RENAME TO usage_logs;

COMMIT;
PRAGMA foreign_keys = ON;
''')
print('Migration complete. Rows preserved:', conn.execute('SELECT COUNT(*) FROM usage_logs').fetchone()[0])
"
```

Run option B exactly once. If it fails partway, restore from backup and retry (make a copy of `farm_manager.db` first).

SQLite also requires the `PRAGMA foreign_keys = ON` at runtime to enforce FK rules, which SQLAlchemy handles via connection event listeners — but it's worth verifying. From the project directory:

```bash
python -c "
from dotenv import load_dotenv; load_dotenv()
import os
from database import engine
from sqlalchemy import event
@event.listens_for(engine, 'connect')
def fk_on(conn, rec):
    conn.execute('PRAGMA foreign_keys=ON')
with engine.connect() as c:
    print('FK enforcement:', c.exec_driver_sql('PRAGMA foreign_keys').scalar())
"
```

If that prints `1`, you're good. If it prints `0`, add this snippet to `database.py` right after `engine = create_engine(...)`:

```python
from sqlalchemy import event
@event.listens_for(engine, "connect")
def _sqlite_fk_on(dbapi_conn, _):
    dbapi_conn.execute("PRAGMA foreign_keys=ON")
```

---

## Verify

### Test 1 — oversize log rejected

```bash
python server.py &
sleep 2

# log in as admin, try to log 99999 L of fungicide (stock = 95 L)
# Expected: red flash "Cannot log 99999.0 L: only 95.0 L on hand..."
# Expected: no change to stock, no new row in usage_logs.

kill %1
```

### Test 2 — log delete does not touch stock

```bash
python -c "
from dotenv import load_dotenv; load_dotenv()
from database import get_session
from models import InventoryItem, UsageLog
s = get_session()

# Pick any item, note current stock
item = s.query(InventoryItem).first()
print('Before delete, stock:', item.quantity_on_hand)

# Pick any log for that item
log = s.query(UsageLog).filter_by(inventory_item_id=item.id).first()
print('Log quantity:', log.quantity_used)
"
```

Then in the Flask UI, delete that log. Re-run the snippet — `item.quantity_on_hand` should be unchanged.

### Test 3 — inventory delete refuses when logs exist

```bash
# Confirm the fungicide has at least one usage log
python -c "
from dotenv import load_dotenv; load_dotenv()
from database import get_session
from models import UsageLog
s = get_session()
print('Fungicide logs:', s.query(UsageLog).filter_by(inventory_item_id=4).count())
"

# Try to delete the fungicide via the UI (inventory page, Delete button on 'Quilt Xcel Fungicide')
# Expected: red flash "Cannot delete 'Quilt Xcel Fungicide': N usage log entries reference it..."
# Expected: item still present in the list, logs untouched.
```

### Test 4 — inventory delete succeeds when no logs exist

```bash
# Add a fresh test item via the UI with no logs, then delete it.
# Expected: green flash, item gone.
```

---

## What this buys you

Before: a single fat-fingered log could silently zero out an item's stock. A log deletion could double-count against any restock. Deleting an inventory item nuked every log that ever referenced it, poisoning reorder suggestions and research data.

After: oversize logs are rejected, log deletes leave stock alone and warn the user, and inventory items with history cannot be accidentally wiped — you have to remove their logs first (which is now an explicit, visible step).

Still not solved: the `days_remaining()` formula is still wrong when data is sparse (Step 4), treatment applications don't decrement inventory (also Step 4 or later), and there's still no audit log of *who* deleted *what*. Those are separate concerns.
