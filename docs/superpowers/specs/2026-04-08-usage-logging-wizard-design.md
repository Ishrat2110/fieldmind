# Usage Logging Wizard — Design Spec
Date: 2026-04-08  
Status: Approved

## Overview
Add a usage logging wizard to the FarmOS HTML frontend (`localhost:3000`) that authenticates users via NUID + password, walks them through selecting an inventory item and plot, auto-estimates quantity from equipment rate × plot area, depletes inventory, and writes a full audit log.

---

## Architecture

```
localhost:3000  (serve.mjs — static HTML)
    v2/index.html  →  fetch()  →  localhost:8000  (api.py — FastAPI)
                                          ↓
                                  SQLAlchemy + farm_manager.db
```

**New file:** `api.py` — FastAPI backend reusing existing `models.py` and `results/farm_manager.db`  
**Modified file:** `v2/index.html` — login modal + 4-step wizard panel added  
**No changes:** `app.py`, `models.py`, `serve.mjs`, DB schema

---

## Authentication

- **Type:** Session-based (tab lifetime)
- **Login modal** overlays the page on load if no session token in `sessionStorage`
- **Flow:**
  1. User enters NUID + password
  2. `POST /auth/login` → backend finds user by `nuid`, verifies `password_hash` (bcrypt)
  3. Returns `{ token, user_id, name }` — token is a UUID in a server-side in-memory dict
  4. Frontend stores token in `sessionStorage`
  5. All API calls send `Authorization: Bearer <token>`
  6. 401 → re-show login modal
- **Logout:** name shown in nav top-right, "Sign out" clears `sessionStorage` and re-shows modal

---

## Wizard UI — 4 Steps

### Step 1: Select Item
- Category filter buttons: `Herbicide | Seed | Fuel | Fungicide | Other`
- Search box with live-filtered dropdown by item name
- Dropdown shows item name + current `quantity_on_hand`

### Step 2: Select Location
- Field dropdown (all fields for the farm)
- Plot dropdown filtered by selected field (shows `plot_code` + `area_ha`)

### Step 3: Confirm Quantity
- Equipment selector dropdown (equipment with `chemical_rate_l_per_ha`)
- Auto-filled quantity: `equipment.chemical_rate_l_per_ha × plot.area_ha`
- Quantity field is editable — shows "Manual entry" tag if changed
- Display: "Estimated usage: X L for Y ha plot"
- **Edge case:** If item category is `seed` or no equipment has a `chemical_rate_l_per_ha` set, quantity defaults to 0 and requires manual entry (no estimate shown)

### Step 4: Submit
- Summary card: item, field, plot, quantity, equipment, logged-by name
- "Confirm & Log" button
- On success: green toast "Logged successfully", form resets to Step 1

---

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/auth/login` | Verify NUID + password, return session token |
| `POST` | `/auth/logout` | Invalidate session token |
| `GET` | `/api/inventory` | List items (`?category=herbicide&search=aatrex`) |
| `GET` | `/api/fields` | List all fields for the farm |
| `GET` | `/api/plots?field_id=X` | List plots for a field |
| `GET` | `/api/equipment` | List equipment with `chemical_rate_l_per_ha` |
| `POST` | `/api/logs` | Submit usage log entry |

**`POST /api/logs` payload:**
```json
{
  "inventory_item_id": 12,
  "plot_id": 4,
  "equipment_id": 2,
  "quantity_used": 3.5,
  "ai_estimated": true,
  "ai_estimate_corrected": false,
  "notes": ""
}
```

---

## Inventory Depletion Logic (single DB transaction)

1. Verify session token → get `user_id`
2. Fetch `InventoryItem` → check `quantity_on_hand >= quantity_used` (400 if insufficient)
3. `UPDATE inventory_items SET quantity_on_hand = quantity_on_hand - quantity_used`
4. `INSERT` into `usage_logs` (item, plot, equipment, logged_by, quantity, ai flags, notes)
5. `INSERT` into `activity_logs` (user, session_id, action="log_usage", full detail string)
6. `COMMIT` — rollback on any failure → 500

**Estimate flags:**
- User accepts estimate → `ai_estimated=true, ai_estimate_corrected=false`
- User edits quantity → `ai_estimated=true, ai_estimate_corrected=true`

---

## Constraints
- CORS enabled on FastAPI for `http://localhost:3000`
- Session tokens live in server memory — cleared on process restart (satisfies tab-session requirement)
- No DB schema changes required
- `farm_id = 1` (single farm, hardcoded for now)
