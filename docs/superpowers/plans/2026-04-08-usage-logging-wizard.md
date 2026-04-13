# Usage Logging Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a NUID-authenticated usage logging wizard to the FarmOS HTML frontend (localhost:3000) that auto-estimates quantity from equipment rate × plot area, depletes inventory, and writes a full audit log.

**Architecture:** FastAPI backend (`api.py`) on port 8000 exposes REST endpoints reusing existing SQLAlchemy models and `farm_manager.db`. The static HTML frontend (`v2/index.html`) on port 3000 gains a login modal and 4-step wizard that calls the API via `fetch()`. CORS is enabled for localhost:3000.

**Tech Stack:** FastAPI, uvicorn, SQLAlchemy (existing), werkzeug (existing, for password verification), vanilla JS + existing Tailwind CDN in HTML

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `api.py` | Create | FastAPI app — all endpoints, session management, DB transactions |
| `tests/test_api.py` | Create | Endpoint tests using FastAPI TestClient + in-memory SQLite |
| `requirements.txt` | Modify | Add fastapi, uvicorn |
| `v2/index.html` | Modify | Login modal + 4-step wizard UI + fetch() wiring |

---

## Task 1: Install Dependencies and api.py Skeleton

**Files:**
- Modify: `requirements.txt`
- Create: `api.py`
- Create: `tests/__init__.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Install fastapi and uvicorn**

```bash
cd /Users/ishratjandu/AI_Pitla/Semester_project/farm_manager_step1
pip3 install fastapi uvicorn --break-system-packages
```

Expected: Successfully installed fastapi-x.x.x uvicorn-x.x.x

- [ ] **Step 2: Add to requirements.txt**

Open `requirements.txt` and append:
```
fastapi>=0.110,<1.0
uvicorn>=0.29,<1.0
```

- [ ] **Step 3: Create tests directory**

```bash
mkdir -p tests
touch tests/__init__.py
```

- [ ] **Step 4: Write failing health check test**

Create `tests/test_api.py`:

```python
"""Tests for api.py — uses FastAPI TestClient with in-memory SQLite."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# We'll import app and override DB after api.py exists
# For now just a placeholder import test
def test_placeholder():
    assert True
```

- [ ] **Step 5: Run test to confirm test harness works**

```bash
cd /Users/ishratjandu/AI_Pitla/Semester_project/farm_manager_step1
python3 -m pytest tests/test_api.py -v
```

Expected: `1 passed`

- [ ] **Step 6: Create api.py skeleton with health check**

Create `api.py`:

```python
"""
api.py
------
FastAPI backend for the FarmOS usage logging wizard.
Run with: python3 api.py  (starts on http://localhost:8000)
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from models import (
    Base, User, Farm, Field, Plot, Equipment,
    InventoryItem, UsageLog, ActivityLog
)
from werkzeug.security import check_password_hash

# ── DB ────────────────────────────────────────────────────────────────────────
DATABASE_URL = "sqlite:////Users/ishratjandu/AI_Pitla/results/farm_manager.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

FARM_ID = 1

# ── SESSION STORE ─────────────────────────────────────────────────────────────
# In-memory: token -> {user_id, name, session_id}
# Cleared on process restart (satisfies tab-session requirement)
sessions: dict[str, dict] = {}

# ── APP ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="FarmOS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── DB DEPENDENCY ─────────────────────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── AUTH DEPENDENCY ───────────────────────────────────────────────────────────
def get_current_user(authorization: str = Header(...)) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if token not in sessions:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return sessions[token]


# ── HEALTH ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
```

- [ ] **Step 7: Write and run health check test**

Replace `tests/test_api.py` with:

```python
"""Tests for api.py — uses FastAPI TestClient with in-memory SQLite."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api import app, get_db
from models import Base, User, Farm, FarmMember, Field, Plot, Equipment, InventoryItem
from werkzeug.security import generate_password_hash

# ── IN-MEMORY DB FIXTURE ──────────────────────────────────────────────────────
TEST_DB_URL = "sqlite:///:memory:"

@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def seeded_db(db_session):
    """Minimal seed: 1 user, 1 farm, 1 field, 1 plot, 1 equipment, 1 inventory item."""
    from models import UserRole, FieldStatus
    user = User(
        name="Test User", email="test@unl.edu", nuid="11111111",
        password_hash=generate_password_hash("testpass"), role=UserRole.manager
    )
    db_session.add(user)
    db_session.flush()

    farm = Farm(name="Test Farm", location="Lincoln, NE", total_area_ha=10.0)
    db_session.add(farm)
    db_session.flush()

    member = FarmMember(farm_id=farm.id, user_id=user.id, role=UserRole.manager)
    db_session.add(member)

    field = Field(farm_id=farm.id, name="Field A", area_ha=5.0,
                  soil_type="silt loam", status=FieldStatus.active)
    db_session.add(field)
    db_session.flush()

    from models import CropSpecies, CropVariety
    species = CropSpecies(common_name="Corn", scientific_name="Zea mays", typical_season_days=120)
    db_session.add(species)
    db_session.flush()

    variety = CropVariety(species_id=species.id, variety_code="TEST-VAR", variety_name="Test Variety")
    db_session.add(variety)
    db_session.flush()

    plot = Plot(field_id=field.id, variety_id=variety.id,
                plot_code="A-01", replication=1, area_ha=2.5)
    db_session.add(plot)
    db_session.flush()

    equipment = Equipment(
        farm_id=farm.id, name="Test Sprayer", equipment_type="sprayer",
        fuel_rate_l_per_hr=14.0, chemical_rate_l_per_ha=150.0
    )
    db_session.add(equipment)

    item = InventoryItem(
        farm_id=farm.id, name="Test Herbicide", category="herbicide",
        unit="L", quantity_on_hand=100.0
    )
    db_session.add(item)
    db_session.commit()
    return {"user": user, "farm": farm, "field": field, "plot": plot,
            "equipment": equipment, "item": item}


# ── HEALTH ────────────────────────────────────────────────────────────────────
def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

Run:
```bash
python3 -m pytest tests/test_api.py::test_health -v
```

Expected: `PASSED`

- [ ] **Step 8: Commit**

```bash
git init  # if not already a git repo
git add api.py tests/__init__.py tests/test_api.py requirements.txt
git commit -m "feat: add FastAPI skeleton with health check and test harness"
```

---

## Task 2: Auth Endpoints

**Files:**
- Modify: `api.py` (add `/auth/login`, `/auth/logout`)
- Modify: `tests/test_api.py` (add auth tests)

- [ ] **Step 1: Write failing auth tests**

Append to `tests/test_api.py`:

```python
# ── AUTH ──────────────────────────────────────────────────────────────────────
def test_login_success(client, seeded_db):
    response = client.post("/auth/login", json={"nuid": "11111111", "password": "testpass"})
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert data["name"] == "Test User"
    assert "user_id" in data


def test_login_wrong_password(client, seeded_db):
    response = client.post("/auth/login", json={"nuid": "11111111", "password": "wrong"})
    assert response.status_code == 401


def test_login_unknown_nuid(client, seeded_db):
    response = client.post("/auth/login", json={"nuid": "99999999", "password": "x"})
    assert response.status_code == 401


def test_logout(client, seeded_db):
    login = client.post("/auth/login", json={"nuid": "11111111", "password": "testpass"})
    token = login.json()["token"]
    response = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    # token should be invalidated
    response2 = client.get("/api/fields", headers={"Authorization": f"Bearer {token}"})
    assert response2.status_code == 401


def test_protected_endpoint_without_token(client, seeded_db):
    response = client.get("/api/fields")
    assert response.status_code == 422  # missing required header
```

Run:
```bash
python3 -m pytest tests/test_api.py -k "auth" -v
```

Expected: all FAILED (endpoints don't exist yet)

- [ ] **Step 2: Add auth endpoints to api.py**

After the `health` endpoint in `api.py`, add:

```python
# ── PYDANTIC MODELS ───────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    nuid: str
    password: str


# ── AUTH ENDPOINTS ────────────────────────────────────────────────────────────
@app.post("/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(nuid=req.nuid, is_active=True).first()
    if not user or not check_password_hash(user.password_hash, req.password):
        raise HTTPException(status_code=401, detail="Invalid NUID or password")
    token = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    sessions[token] = {"user_id": user.id, "name": user.name, "session_id": session_id}
    return {"token": token, "user_id": user.id, "name": user.name}


@app.post("/auth/logout")
def logout(current_user: dict = Depends(get_current_user)):
    # Find and remove the token
    token_to_remove = None
    for token, data in sessions.items():
        if data["user_id"] == current_user["user_id"]:
            token_to_remove = token
            break
    if token_to_remove:
        del sessions[token_to_remove]
    return {"status": "logged out"}
```

- [ ] **Step 3: Run auth tests**

```bash
python3 -m pytest tests/test_api.py -k "auth or login or logout" -v
```

Expected: all PASSED

- [ ] **Step 4: Commit**

```bash
git add api.py tests/test_api.py
git commit -m "feat: add auth login/logout endpoints with session tokens"
```

---

## Task 3: Inventory, Fields, Plots, Equipment Endpoints

**Files:**
- Modify: `api.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_api.py`:

```python
# ── HELPER: get auth token ─────────────────────────────────────────────────────
def auth_headers(client, nuid="11111111", password="testpass"):
    r = client.post("/auth/login", json={"nuid": nuid, "password": password})
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ── INVENTORY ─────────────────────────────────────────────────────────────────
def test_get_inventory_all(client, seeded_db):
    headers = auth_headers(client)
    r = client.get("/api/inventory", headers=headers)
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    assert items[0]["name"] == "Test Herbicide"


def test_get_inventory_filter_category(client, seeded_db):
    headers = auth_headers(client)
    r = client.get("/api/inventory?category=herbicide", headers=headers)
    assert r.status_code == 200
    assert all(i["category"] == "herbicide" for i in r.json())


def test_get_inventory_search(client, seeded_db):
    headers = auth_headers(client)
    r = client.get("/api/inventory?search=herb", headers=headers)
    assert r.status_code == 200
    assert any("Herbicide" in i["name"] for i in r.json())


# ── FIELDS ────────────────────────────────────────────────────────────────────
def test_get_fields(client, seeded_db):
    headers = auth_headers(client)
    r = client.get("/api/fields", headers=headers)
    assert r.status_code == 200
    fields = r.json()
    assert len(fields) == 1
    assert fields[0]["name"] == "Field A"


# ── PLOTS ─────────────────────────────────────────────────────────────────────
def test_get_plots_for_field(client, seeded_db):
    headers = auth_headers(client)
    field_id = seeded_db["field"].id
    r = client.get(f"/api/plots?field_id={field_id}", headers=headers)
    assert r.status_code == 200
    plots = r.json()
    assert len(plots) == 1
    assert plots[0]["plot_code"] == "A-01"
    assert plots[0]["area_ha"] == 2.5


# ── EQUIPMENT ─────────────────────────────────────────────────────────────────
def test_get_equipment(client, seeded_db):
    headers = auth_headers(client)
    r = client.get("/api/equipment", headers=headers)
    assert r.status_code == 200
    equip = r.json()
    assert len(equip) == 1
    assert equip[0]["chemical_rate_l_per_ha"] == 150.0
```

Run:
```bash
python3 -m pytest tests/test_api.py -k "inventory or fields or plots or equipment" -v
```

Expected: all FAILED

- [ ] **Step 2: Add read endpoints to api.py**

After the auth endpoints in `api.py`, add:

```python
# ── READ ENDPOINTS ────────────────────────────────────────────────────────────

@app.get("/api/inventory")
def get_inventory(
    category: Optional[str] = None,
    search: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(InventoryItem).filter_by(farm_id=FARM_ID)
    if category:
        q = q.filter(InventoryItem.category == category.lower())
    if search:
        q = q.filter(InventoryItem.name.ilike(f"%{search}%"))
    items = q.order_by(InventoryItem.name).all()
    return [
        {
            "id": i.id,
            "name": i.name,
            "category": i.category,
            "unit": i.unit,
            "quantity_on_hand": i.quantity_on_hand,
        }
        for i in items
    ]


@app.get("/api/fields")
def get_fields(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fields = db.query(Field).filter_by(farm_id=FARM_ID).order_by(Field.name).all()
    return [{"id": f.id, "name": f.name, "area_ha": f.area_ha} for f in fields]


@app.get("/api/plots")
def get_plots(
    field_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plots = db.query(Plot).filter_by(field_id=field_id).order_by(Plot.plot_code).all()
    return [
        {"id": p.id, "plot_code": p.plot_code, "area_ha": p.area_ha, "replication": p.replication}
        for p in plots
    ]


@app.get("/api/equipment")
def get_equipment(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    equip = db.query(Equipment).filter_by(farm_id=FARM_ID).all()
    return [
        {
            "id": e.id,
            "name": e.name,
            "equipment_type": e.equipment_type,
            "chemical_rate_l_per_ha": e.chemical_rate_l_per_ha,
        }
        for e in equip
    ]
```

- [ ] **Step 3: Run tests**

```bash
python3 -m pytest tests/test_api.py -k "inventory or fields or plots or equipment" -v
```

Expected: all PASSED

- [ ] **Step 4: Commit**

```bash
git add api.py tests/test_api.py
git commit -m "feat: add inventory, fields, plots, equipment read endpoints"
```

---

## Task 4: POST /api/logs — Usage Log Submission

**Files:**
- Modify: `api.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_api.py`:

```python
# ── USAGE LOG SUBMISSION ──────────────────────────────────────────────────────
def test_submit_log_depletes_inventory(client, seeded_db):
    headers = auth_headers(client)
    item = seeded_db["item"]
    plot = seeded_db["plot"]
    equipment = seeded_db["equipment"]
    initial_qty = item.quantity_on_hand  # 100.0

    r = client.post("/api/logs", headers=headers, json={
        "inventory_item_id": item.id,
        "plot_id": plot.id,
        "equipment_id": equipment.id,
        "quantity_used": 10.0,
        "ai_estimated": True,
        "ai_estimate_corrected": False,
        "notes": "test log"
    })
    assert r.status_code == 201

    # Verify inventory depleted
    from sqlalchemy.orm import Session as SASession
    db = next(iter(client.app.dependency_overrides[get_db]()))
    from models import InventoryItem as II
    updated = db.query(II).filter_by(id=item.id).first()
    assert updated.quantity_on_hand == initial_qty - 10.0


def test_submit_log_creates_usage_log(client, seeded_db):
    headers = auth_headers(client)
    item = seeded_db["item"]
    plot = seeded_db["plot"]
    equipment = seeded_db["equipment"]

    client.post("/api/logs", headers=headers, json={
        "inventory_item_id": item.id,
        "plot_id": plot.id,
        "equipment_id": equipment.id,
        "quantity_used": 5.0,
        "ai_estimated": True,
        "ai_estimate_corrected": False,
        "notes": ""
    })

    db = next(iter(client.app.dependency_overrides[get_db]()))
    from models import UsageLog as UL
    log = db.query(UL).filter_by(inventory_item_id=item.id).first()
    assert log is not None
    assert log.quantity_used == 5.0
    assert log.ai_estimated is True


def test_submit_log_insufficient_stock(client, seeded_db):
    headers = auth_headers(client)
    item = seeded_db["item"]
    plot = seeded_db["plot"]
    equipment = seeded_db["equipment"]

    r = client.post("/api/logs", headers=headers, json={
        "inventory_item_id": item.id,
        "plot_id": plot.id,
        "equipment_id": equipment.id,
        "quantity_used": 9999.0,
        "ai_estimated": False,
        "ai_estimate_corrected": False,
        "notes": ""
    })
    assert r.status_code == 400
    assert "Insufficient" in r.json()["detail"]
```

Run:
```bash
python3 -m pytest tests/test_api.py -k "log" -v
```

Expected: all FAILED

- [ ] **Step 2: Add LogRequest model and POST /api/logs to api.py**

After the read endpoints in `api.py`, add:

```python
# ── PYDANTIC — LOG REQUEST ────────────────────────────────────────────────────
class LogRequest(BaseModel):
    inventory_item_id: int
    plot_id: int
    equipment_id: int
    quantity_used: float
    ai_estimated: bool = True
    ai_estimate_corrected: bool = False
    notes: str = ""


# ── LOG SUBMISSION ────────────────────────────────────────────────────────────
@app.post("/api/logs", status_code=201)
def submit_log(
    req: LogRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.query(InventoryItem).filter_by(id=req.inventory_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    if (item.quantity_on_hand or 0) < req.quantity_used:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient stock: {item.quantity_on_hand} {item.unit} available"
        )

    try:
        # 1. Deplete inventory
        item.quantity_on_hand = (item.quantity_on_hand or 0) - req.quantity_used

        # 2. Create usage log
        plot = db.query(Plot).filter_by(id=req.plot_id).first()
        log = UsageLog(
            inventory_item_id=req.inventory_item_id,
            plot_id=req.plot_id,
            equipment_id=req.equipment_id,
            logged_by=current_user["user_id"],
            quantity_used=req.quantity_used,
            log_date=datetime.now(timezone.utc),
            ai_estimated=req.ai_estimated,
            ai_estimate_corrected=req.ai_estimate_corrected,
            notes=req.notes or None,
        )
        db.add(log)

        # 3. Create activity log
        plot_code = plot.plot_code if plot else f"plot#{req.plot_id}"
        activity = ActivityLog(
            user_id=current_user["user_id"],
            session_id=current_user["session_id"],
            action="log_usage",
            detail=(
                f"Logged {req.quantity_used} {item.unit} of '{item.name}' "
                f"on plot {plot_code} "
                f"[{'AI estimate' if req.ai_estimated and not req.ai_estimate_corrected else 'manual'}]"
            ),
            timestamp=datetime.now(timezone.utc),
        )
        db.add(activity)

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "logged", "remaining_stock": item.quantity_on_hand}
```

- [ ] **Step 3: Fix test helpers to properly access DB after request**

The tests above access the DB after the request. Replace the log tests in `tests/test_api.py` with these corrected versions that use a shared session:

```python
def test_submit_log_depletes_inventory(client, seeded_db, db_session):
    headers = auth_headers(client)
    item_id = seeded_db["item"].id
    plot_id = seeded_db["plot"].id
    equip_id = seeded_db["equipment"].id
    initial_qty = seeded_db["item"].quantity_on_hand  # 100.0

    r = client.post("/api/logs", headers=headers, json={
        "inventory_item_id": item_id,
        "plot_id": plot_id,
        "equipment_id": equip_id,
        "quantity_used": 10.0,
        "ai_estimated": True,
        "ai_estimate_corrected": False,
        "notes": "test log"
    })
    assert r.status_code == 201
    assert r.json()["remaining_stock"] == initial_qty - 10.0

    db_session.expire_all()
    updated = db_session.query(InventoryItem).filter_by(id=item_id).first()
    assert updated.quantity_on_hand == initial_qty - 10.0


def test_submit_log_creates_usage_log(client, seeded_db, db_session):
    headers = auth_headers(client)
    item_id = seeded_db["item"].id

    client.post("/api/logs", headers=headers, json={
        "inventory_item_id": item_id,
        "plot_id": seeded_db["plot"].id,
        "equipment_id": seeded_db["equipment"].id,
        "quantity_used": 5.0,
        "ai_estimated": True,
        "ai_estimate_corrected": False,
        "notes": ""
    })

    db_session.expire_all()
    log = db_session.query(UsageLog).filter_by(inventory_item_id=item_id).first()
    assert log is not None
    assert log.quantity_used == 5.0
    assert log.ai_estimated is True


def test_submit_log_insufficient_stock(client, seeded_db):
    headers = auth_headers(client)

    r = client.post("/api/logs", headers=headers, json={
        "inventory_item_id": seeded_db["item"].id,
        "plot_id": seeded_db["plot"].id,
        "equipment_id": seeded_db["equipment"].id,
        "quantity_used": 9999.0,
        "ai_estimated": False,
        "ai_estimate_corrected": False,
        "notes": ""
    })
    assert r.status_code == 400
    assert "Insufficient" in r.json()["detail"]
```

Also add `UsageLog` to the imports at the top of `tests/test_api.py`:
```python
from models import (
    Base, User, Farm, FarmMember, Field, Plot, Equipment, InventoryItem,
    UsageLog, CropSpecies, CropVariety
)
```

- [ ] **Step 4: Run log tests**

```bash
python3 -m pytest tests/test_api.py -k "log" -v
```

Expected: all PASSED

- [ ] **Step 5: Run full test suite**

```bash
python3 -m pytest tests/test_api.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add api.py tests/test_api.py
git commit -m "feat: add POST /api/logs with inventory depletion and audit trail"
```

---

## Task 5: Frontend — Login Modal

**Files:**
- Modify: `v2/index.html`

The `v2/index.html` uses: `bg=#080d10`, `surface=#111820`, `orange=#F55014`, Albert Sans font.

- [ ] **Step 1: Read the current v2/index.html**

Open `v2/index.html` in your editor and identify:
- Where the `<body>` tag opens
- Where the main `<nav>` or top-level wrapper starts
- The existing font import (Albert Sans) and color variables

- [ ] **Step 2: Add API base URL constant and session helpers before `</body>`**

Find the closing `</body>` tag in `v2/index.html`. Just before it, insert a new `<script>` block:

```html
<!-- ── FarmOS API Integration ──────────────────────────────────── -->
<script>
const API = 'http://localhost:8000';

function getToken() { return sessionStorage.getItem('farmos_token'); }
function getUser()  { return JSON.parse(sessionStorage.getItem('farmos_user') || 'null'); }

function setSession(token, user) {
  sessionStorage.setItem('farmos_token', token);
  sessionStorage.setItem('farmos_user', JSON.stringify(user));
}

function clearSession() {
  sessionStorage.removeItem('farmos_token');
  sessionStorage.removeItem('farmos_user');
}

async function apiFetch(path, options = {}) {
  const token = getToken();
  const res = await fetch(API + path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  if (res.status === 401) { showLoginModal(); throw new Error('Unauthorized'); }
  return res;
}
</script>
```

- [ ] **Step 3: Add login modal HTML**

After the opening `<body>` tag (or inside the top-level wrapper), add:

```html
<!-- ── Login Modal ─────────────────────────────────────────────── -->
<div id="login-modal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.85); z-index:9999; display:flex; align-items:center; justify-content:center;">
  <div style="background:#111820; border:1px solid #1e2d3d; border-radius:12px; padding:40px; width:380px; max-width:90vw;">
    <h2 style="font-family:'Albert Sans',sans-serif; font-size:22px; font-weight:700; color:#fff; margin:0 0 6px;">FarmOS Login</h2>
    <p style="font-family:'Albert Sans',sans-serif; font-size:13px; color:#6b7a8d; margin:0 0 28px;">Enter your NUID and password to continue.</p>

    <label style="display:block; font-family:'Albert Sans',sans-serif; font-size:12px; font-weight:600; color:#8a9bb0; letter-spacing:.08em; text-transform:uppercase; margin-bottom:6px;">NUID</label>
    <input id="login-nuid" type="text" placeholder="e.g. 12345678"
      style="width:100%; box-sizing:border-box; background:#080d10; border:1px solid #1e2d3d; border-radius:8px; padding:10px 14px; color:#fff; font-family:'Albert Sans',sans-serif; font-size:14px; outline:none; margin-bottom:16px;"
      onkeydown="if(event.key==='Enter') handleLogin()"
    />

    <label style="display:block; font-family:'Albert Sans',sans-serif; font-size:12px; font-weight:600; color:#8a9bb0; letter-spacing:.08em; text-transform:uppercase; margin-bottom:6px;">Password</label>
    <input id="login-password" type="password" placeholder="Password"
      style="width:100%; box-sizing:border-box; background:#080d10; border:1px solid #1e2d3d; border-radius:8px; padding:10px 14px; color:#fff; font-family:'Albert Sans',sans-serif; font-size:14px; outline:none; margin-bottom:24px;"
      onkeydown="if(event.key==='Enter') handleLogin()"
    />

    <div id="login-error" style="display:none; color:#f55014; font-family:'Albert Sans',sans-serif; font-size:13px; margin-bottom:16px;"></div>

    <button onclick="handleLogin()"
      style="width:100%; background:#F55014; color:#fff; border:none; border-radius:8px; padding:12px; font-family:'Albert Sans',sans-serif; font-size:14px; font-weight:700; cursor:pointer; transition:opacity .15s;"
      onmouseover="this.style.opacity='.85'" onmouseout="this.style.opacity='1'"
      onfocus="this.style.outline='2px solid #F55014'" onblur="this.style.outline='none'"
      onmousedown="this.style.opacity='.7'" onmouseup="this.style.opacity='.85'"
    >Sign In</button>
  </div>
</div>
```

- [ ] **Step 4: Add login/logout JavaScript**

Inside the API script block from Step 2, append:

```javascript
function showLoginModal() {
  document.getElementById('login-modal').style.display = 'flex';
}

function hideLoginModal() {
  document.getElementById('login-modal').style.display = 'none';
}

async function handleLogin() {
  const nuid = document.getElementById('login-nuid').value.trim();
  const password = document.getElementById('login-password').value;
  const errEl = document.getElementById('login-error');
  errEl.style.display = 'none';

  try {
    const res = await fetch(`${API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nuid, password }),
    });
    if (!res.ok) {
      errEl.textContent = 'Invalid NUID or password.';
      errEl.style.display = 'block';
      return;
    }
    const data = await res.json();
    setSession(data.token, { user_id: data.user_id, name: data.name });
    hideLoginModal();
    updateUserNav();
  } catch (e) {
    errEl.textContent = 'Could not connect to server. Is api.py running?';
    errEl.style.display = 'block';
  }
}

async function handleLogout() {
  try { await apiFetch('/auth/logout', { method: 'POST' }); } catch {}
  clearSession();
  showLoginModal();
  updateUserNav();
}

function updateUserNav() {
  const user = getUser();
  const el = document.getElementById('user-nav');
  if (!el) return;
  if (user) {
    el.innerHTML = `<span style="color:#8a9bb0; font-size:13px;">${user.name}</span>
      <button onclick="handleLogout()" style="background:none; border:none; color:#F55014; font-size:13px; cursor:pointer; margin-left:12px;">Sign out</button>`;
  } else {
    el.innerHTML = '';
  }
}

// On page load: show modal if not authenticated
window.addEventListener('DOMContentLoaded', () => {
  if (!getToken()) showLoginModal();
  else updateUserNav();
});
```

- [ ] **Step 5: Add user nav element to the existing navbar**

Find the top `<nav>` element in `v2/index.html`. Inside it (near the right side), add:

```html
<div id="user-nav" style="display:flex; align-items:center;"></div>
```

- [ ] **Step 6: Start servers and verify login modal appears**

```bash
# Terminal 1
cd /Users/ishratjandu/AI_Pitla/Semester_project/farm_manager_step1
python3 api.py

# Terminal 2
cd /Users/ishratjandu/AI_Pitla/Semester_project/farm_manager_step1
node serve.mjs
```

Open `http://localhost:3000` — login modal should appear. Enter NUID `12345678` and password `admin123`. Should log in and show "Ishrat Jandu" in the nav.

- [ ] **Step 7: Commit**

```bash
git add v2/index.html
git commit -m "feat: add login modal with session-based auth to frontend"
```

---

## Task 6: Frontend — 4-Step Wizard UI

**Files:**
- Modify: `v2/index.html`

- [ ] **Step 1: Add "Log Usage" button to the navbar**

Inside the `<nav>` element, alongside the existing nav items, add:

```html
<button id="log-usage-btn" onclick="openWizard()"
  style="background:#F55014; color:#fff; border:none; border-radius:8px; padding:8px 18px; font-family:'Albert Sans',sans-serif; font-size:13px; font-weight:700; cursor:pointer; transition:opacity .15s;"
  onmouseover="this.style.opacity='.85'" onmouseout="this.style.opacity='1'"
  onmousedown="this.style.opacity='.7'" onmouseup="this.style.opacity='.85'"
  onfocus="this.style.outline='2px solid #F55014'" onblur="this.style.outline='none'"
>+ Log Usage</button>
```

- [ ] **Step 2: Add wizard panel HTML**

After the login modal in `v2/index.html`, add the wizard overlay:

```html
<!-- ── Usage Log Wizard ──────────────────────────────────────────── -->
<div id="wizard-overlay" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.75); z-index:9000; align-items:center; justify-content:center;">
  <div style="background:#111820; border:1px solid #1e2d3d; border-radius:14px; padding:36px; width:480px; max-width:94vw; max-height:90vh; overflow-y:auto;">

    <!-- Header -->
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:28px;">
      <h2 style="font-family:'Albert Sans',sans-serif; font-size:20px; font-weight:700; color:#fff; margin:0;">Log Usage</h2>
      <button onclick="closeWizard()" style="background:none; border:none; color:#6b7a8d; font-size:20px; cursor:pointer; line-height:1;">✕</button>
    </div>

    <!-- Step indicators -->
    <div style="display:flex; gap:8px; margin-bottom:28px;" id="wizard-steps">
      <div class="wstep" data-step="1" style="flex:1; height:4px; border-radius:2px; background:#F55014;"></div>
      <div class="wstep" data-step="2" style="flex:1; height:4px; border-radius:2px; background:#1e2d3d;"></div>
      <div class="wstep" data-step="3" style="flex:1; height:4px; border-radius:2px; background:#1e2d3d;"></div>
      <div class="wstep" data-step="4" style="flex:1; height:4px; border-radius:2px; background:#1e2d3d;"></div>
    </div>

    <!-- Step 1: Select Item -->
    <div id="wizard-step-1">
      <p style="font-family:'Albert Sans',sans-serif; font-size:12px; font-weight:600; color:#8a9bb0; letter-spacing:.08em; text-transform:uppercase; margin:0 0 12px;">Step 1 — Select Item</p>
      <div id="category-buttons" style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px;"></div>
      <input id="item-search" type="text" placeholder="Search by name…"
        style="width:100%; box-sizing:border-box; background:#080d10; border:1px solid #1e2d3d; border-radius:8px; padding:10px 14px; color:#fff; font-family:'Albert Sans',sans-serif; font-size:14px; outline:none; margin-bottom:8px;"
        oninput="filterItems()"
      />
      <div id="item-list" style="max-height:200px; overflow-y:auto; border:1px solid #1e2d3d; border-radius:8px; background:#080d10;"></div>
      <button onclick="wizardNext(2)" id="step1-next" disabled
        style="margin-top:16px; width:100%; background:#F55014; color:#fff; border:none; border-radius:8px; padding:11px; font-family:'Albert Sans',sans-serif; font-size:14px; font-weight:700; cursor:pointer; opacity:.4; transition:opacity .15s;"
      >Next →</button>
    </div>

    <!-- Step 2: Select Location -->
    <div id="wizard-step-2" style="display:none;">
      <p style="font-family:'Albert Sans',sans-serif; font-size:12px; font-weight:600; color:#8a9bb0; letter-spacing:.08em; text-transform:uppercase; margin:0 0 12px;">Step 2 — Select Location</p>
      <label style="display:block; font-family:'Albert Sans',sans-serif; font-size:12px; color:#8a9bb0; margin-bottom:6px;">Field</label>
      <select id="field-select" onchange="loadPlots()"
        style="width:100%; background:#080d10; border:1px solid #1e2d3d; border-radius:8px; padding:10px 14px; color:#fff; font-family:'Albert Sans',sans-serif; font-size:14px; outline:none; margin-bottom:16px;">
        <option value="">— Select field —</option>
      </select>
      <label style="display:block; font-family:'Albert Sans',sans-serif; font-size:12px; color:#8a9bb0; margin-bottom:6px;">Plot</label>
      <select id="plot-select" onchange="onPlotSelect()"
        style="width:100%; background:#080d10; border:1px solid #1e2d3d; border-radius:8px; padding:10px 14px; color:#fff; font-family:'Albert Sans',sans-serif; font-size:14px; outline:none; margin-bottom:16px;">
        <option value="">— Select plot —</option>
      </select>
      <div style="display:flex; gap:10px;">
        <button onclick="wizardNext(1)" style="flex:1; background:#1e2d3d; color:#fff; border:none; border-radius:8px; padding:11px; font-family:'Albert Sans',sans-serif; font-size:14px; cursor:pointer;">← Back</button>
        <button onclick="wizardNext(3)" id="step2-next" disabled
          style="flex:2; background:#F55014; color:#fff; border:none; border-radius:8px; padding:11px; font-family:'Albert Sans',sans-serif; font-size:14px; font-weight:700; cursor:pointer; opacity:.4;">Next →</button>
      </div>
    </div>

    <!-- Step 3: Confirm Quantity -->
    <div id="wizard-step-3" style="display:none;">
      <p style="font-family:'Albert Sans',sans-serif; font-size:12px; font-weight:600; color:#8a9bb0; letter-spacing:.08em; text-transform:uppercase; margin:0 0 12px;">Step 3 — Confirm Quantity</p>
      <label style="display:block; font-family:'Albert Sans',sans-serif; font-size:12px; color:#8a9bb0; margin-bottom:6px;">Equipment</label>
      <select id="equipment-select" onchange="updateEstimate()"
        style="width:100%; background:#080d10; border:1px solid #1e2d3d; border-radius:8px; padding:10px 14px; color:#fff; font-family:'Albert Sans',sans-serif; font-size:14px; outline:none; margin-bottom:16px;">
        <option value="">— No equipment —</option>
      </select>
      <div id="estimate-hint" style="font-family:'Albert Sans',sans-serif; font-size:12px; color:#6b7a8d; margin-bottom:8px;"></div>
      <label style="display:block; font-family:'Albert Sans',sans-serif; font-size:12px; color:#8a9bb0; margin-bottom:6px;">Quantity used <span id="qty-unit" style="color:#F55014;"></span></label>
      <div style="position:relative;">
        <input id="qty-input" type="number" step="0.1" min="0"
          style="width:100%; box-sizing:border-box; background:#080d10; border:1px solid #1e2d3d; border-radius:8px; padding:10px 14px; color:#fff; font-family:'Albert Sans',sans-serif; font-size:14px; outline:none; margin-bottom:4px;"
          oninput="onQtyEdit()"
        />
        <span id="manual-tag" style="display:none; position:absolute; right:12px; top:11px; font-size:11px; color:#F55014; font-family:'Albert Sans',sans-serif;">Manual entry</span>
      </div>
      <div style="display:flex; gap:10px; margin-top:16px;">
        <button onclick="wizardNext(2)" style="flex:1; background:#1e2d3d; color:#fff; border:none; border-radius:8px; padding:11px; font-family:'Albert Sans',sans-serif; font-size:14px; cursor:pointer;">← Back</button>
        <button onclick="wizardNext(4)"
          style="flex:2; background:#F55014; color:#fff; border:none; border-radius:8px; padding:11px; font-family:'Albert Sans',sans-serif; font-size:14px; font-weight:700; cursor:pointer;">Next →</button>
      </div>
    </div>

    <!-- Step 4: Confirm & Submit -->
    <div id="wizard-step-4" style="display:none;">
      <p style="font-family:'Albert Sans',sans-serif; font-size:12px; font-weight:600; color:#8a9bb0; letter-spacing:.08em; text-transform:uppercase; margin:0 0 12px;">Step 4 — Confirm & Submit</p>
      <div id="summary-card" style="background:#080d10; border:1px solid #1e2d3d; border-radius:10px; padding:18px; margin-bottom:20px; font-family:'Albert Sans',sans-serif; font-size:14px; line-height:1.8; color:#c8d4e0;"></div>
      <div style="display:flex; gap:10px;">
        <button onclick="wizardNext(3)" style="flex:1; background:#1e2d3d; color:#fff; border:none; border-radius:8px; padding:11px; font-family:'Albert Sans',sans-serif; font-size:14px; cursor:pointer;">← Back</button>
        <button onclick="submitLog()" id="submit-btn"
          style="flex:2; background:#F55014; color:#fff; border:none; border-radius:8px; padding:11px; font-family:'Albert Sans',sans-serif; font-size:14px; font-weight:700; cursor:pointer;">Confirm & Log</button>
      </div>
    </div>

  </div>
</div>

<!-- Toast -->
<div id="toast" style="display:none; position:fixed; bottom:28px; right:28px; background:#1a3a1a; border:1px solid #2d6a2d; color:#6fcf6f; padding:14px 22px; border-radius:10px; font-family:'Albert Sans',sans-serif; font-size:14px; z-index:9999; transition:opacity .3s;"></div>
```

- [ ] **Step 3: Add wizard JavaScript**

Inside the API script block, append:

```javascript
// ── Wizard State ──────────────────────────────────────────────────
const wiz = {
  selectedItem: null,      // {id, name, category, unit, quantity_on_hand}
  selectedPlot: null,      // {id, plot_code, area_ha}
  selectedField: null,     // {id, name}
  selectedEquipment: null, // {id, name, chemical_rate_l_per_ha}
  quantity: 0,
  aiEstimated: true,
  aiCorrected: false,
  allItems: [],
  activeCategory: null,
};

function openWizard() {
  if (!getToken()) { showLoginModal(); return; }
  resetWizard();
  document.getElementById('wizard-overlay').style.display = 'flex';
  loadWizardData();
}

function closeWizard() {
  document.getElementById('wizard-overlay').style.display = 'none';
}

function resetWizard() {
  wiz.selectedItem = null; wiz.selectedPlot = null;
  wiz.selectedField = null; wiz.selectedEquipment = null;
  wiz.quantity = 0; wiz.aiEstimated = true; wiz.aiCorrected = false;
  wiz.activeCategory = null;
  wizardNext(1);
}

function wizardNext(step) {
  [1,2,3,4].forEach(n => {
    document.getElementById(`wizard-step-${n}`).style.display = n === step ? 'block' : 'none';
    const indicator = document.querySelector(`.wstep[data-step="${n}"]`);
    if (indicator) indicator.style.background = n <= step ? '#F55014' : '#1e2d3d';
  });
  if (step === 4) buildSummary();
}

// ── Step 1: Items ─────────────────────────────────────────────────
async function loadWizardData() {
  // Load items
  const r = await apiFetch('/api/inventory');
  wiz.allItems = await r.json();
  buildCategoryButtons();
  renderItemList(wiz.allItems);

  // Load fields
  const fr = await apiFetch('/api/fields');
  const fields = await fr.json();
  const sel = document.getElementById('field-select');
  sel.innerHTML = '<option value="">— Select field —</option>' +
    fields.map(f => `<option value="${f.id}" data-name="${f.name}">${f.name} (${f.area_ha} ha)</option>`).join('');

  // Load equipment
  const er = await apiFetch('/api/equipment');
  const equip = await er.json();
  const esel = document.getElementById('equipment-select');
  esel.innerHTML = '<option value="">— No equipment —</option>' +
    equip.map(e => `<option value="${e.id}" data-rate="${e.chemical_rate_l_per_ha || 0}">${e.name}</option>`).join('');
}

const CATEGORIES = ['herbicide', 'seed', 'fuel', 'fungicide', 'fertilizer', 'other'];

function buildCategoryButtons() {
  const container = document.getElementById('category-buttons');
  const all = document.createElement('button');
  all.textContent = 'All';
  all.onclick = () => setCategoryFilter(null, all);
  styleTabBtn(all, true);
  container.appendChild(all);

  const present = [...new Set(wiz.allItems.map(i => i.category).filter(Boolean))];
  CATEGORIES.filter(c => present.includes(c)).forEach(cat => {
    const btn = document.createElement('button');
    btn.textContent = cat.charAt(0).toUpperCase() + cat.slice(1);
    btn.onclick = () => setCategoryFilter(cat, btn);
    styleTabBtn(btn, false);
    container.appendChild(btn);
  });
}

function styleTabBtn(btn, active) {
  btn.style.cssText = `background:${active ? '#F55014' : '#1e2d3d'}; color:#fff; border:none; border-radius:6px; padding:6px 14px; font-family:'Albert Sans',sans-serif; font-size:12px; font-weight:600; cursor:pointer; transition:background .15s;`;
}

function setCategoryFilter(cat, btnEl) {
  wiz.activeCategory = cat;
  document.querySelectorAll('#category-buttons button').forEach(b => styleTabBtn(b, false));
  styleTabBtn(btnEl, true);
  filterItems();
}

function filterItems() {
  const search = document.getElementById('item-search').value.toLowerCase();
  let filtered = wiz.allItems;
  if (wiz.activeCategory) filtered = filtered.filter(i => i.category === wiz.activeCategory);
  if (search) filtered = filtered.filter(i => i.name.toLowerCase().includes(search));
  renderItemList(filtered);
}

function renderItemList(items) {
  const container = document.getElementById('item-list');
  if (items.length === 0) {
    container.innerHTML = '<div style="padding:12px 14px; color:#6b7a8d; font-family:\'Albert Sans\',sans-serif; font-size:13px;">No items found</div>';
    return;
  }
  container.innerHTML = items.map(item => `
    <div onclick="selectItem(${item.id})" data-item-id="${item.id}"
      style="padding:10px 14px; cursor:pointer; border-bottom:1px solid #1e2d3d; font-family:'Albert Sans',sans-serif; transition:background .1s;"
      onmouseover="this.style.background='#1e2d3d'" onmouseout="this.style.background='transparent'">
      <div style="font-size:14px; color:#fff;">${item.name}</div>
      <div style="font-size:12px; color:#6b7a8d;">${item.category} · ${item.quantity_on_hand} ${item.unit} in stock</div>
    </div>
  `).join('');
}

function selectItem(itemId) {
  wiz.selectedItem = wiz.allItems.find(i => i.id === itemId);
  document.querySelectorAll('#item-list [data-item-id]').forEach(el => {
    el.style.background = el.dataset.itemId == itemId ? '#1e2d3d' : 'transparent';
    el.style.borderLeft = el.dataset.itemId == itemId ? '3px solid #F55014' : '3px solid transparent';
  });
  const btn = document.getElementById('step1-next');
  btn.disabled = false;
  btn.style.opacity = '1';
  document.getElementById('qty-unit').textContent = `(${wiz.selectedItem.unit})`;
}

// ── Step 2: Location ──────────────────────────────────────────────
async function loadPlots() {
  const sel = document.getElementById('field-select');
  const fieldId = sel.value;
  wiz.selectedField = fieldId ? { id: parseInt(fieldId), name: sel.options[sel.selectedIndex].dataset.name } : null;
  const psel = document.getElementById('plot-select');
  psel.innerHTML = '<option value="">— Select plot —</option>';
  wiz.selectedPlot = null;
  const btn = document.getElementById('step2-next');
  btn.disabled = true; btn.style.opacity = '.4';
  if (!fieldId) return;
  const r = await apiFetch(`/api/plots?field_id=${fieldId}`);
  const plots = await r.json();
  psel.innerHTML = '<option value="">— Select plot —</option>' +
    plots.map(p => `<option value="${p.id}" data-code="${p.plot_code}" data-area="${p.area_ha}">${p.plot_code} (${p.area_ha} ha)</option>`).join('');
}

function onPlotSelect() {
  const sel = document.getElementById('plot-select');
  const opt = sel.options[sel.selectedIndex];
  wiz.selectedPlot = sel.value ? { id: parseInt(sel.value), plot_code: opt.dataset.code, area_ha: parseFloat(opt.dataset.area) } : null;
  const btn = document.getElementById('step2-next');
  btn.disabled = !wiz.selectedPlot;
  btn.style.opacity = wiz.selectedPlot ? '1' : '.4';
}

// ── Step 3: Quantity ──────────────────────────────────────────────
function updateEstimate() {
  const esel = document.getElementById('equipment-select');
  const opt = esel.options[esel.selectedIndex];
  const rate = esel.value ? parseFloat(opt.dataset.rate) : 0;
  wiz.selectedEquipment = esel.value ? { id: parseInt(esel.value), chemical_rate_l_per_ha: rate } : null;

  const area = wiz.selectedPlot ? wiz.selectedPlot.area_ha : 0;
  const isSeed = wiz.selectedItem && wiz.selectedItem.category === 'seed';
  const hint = document.getElementById('estimate-hint');
  const input = document.getElementById('qty-input');

  if (!isSeed && rate > 0 && area > 0) {
    const est = +(rate * area).toFixed(2);
    wiz.quantity = est;
    wiz.aiEstimated = true;
    wiz.aiCorrected = false;
    input.value = est;
    hint.textContent = `Estimated: ${rate} L/ha × ${area} ha = ${est} ${wiz.selectedItem ? wiz.selectedItem.unit : ''}`;
    document.getElementById('manual-tag').style.display = 'none';
  } else {
    wiz.quantity = 0;
    input.value = '';
    hint.textContent = isSeed ? 'Seeds: enter quantity manually.' : 'Select equipment with a chemical rate to auto-estimate.';
  }
}

function onQtyEdit() {
  const val = parseFloat(document.getElementById('qty-input').value);
  const estimatedWas = wiz.aiEstimated && !wiz.aiCorrected;
  if (!isNaN(val)) {
    wiz.quantity = val;
    if (estimatedWas && val !== parseFloat(document.getElementById('qty-input').dataset.estimate)) {
      wiz.aiCorrected = true;
      document.getElementById('manual-tag').style.display = 'inline';
    }
  }
}

// ── Step 4: Summary & Submit ──────────────────────────────────────
function buildSummary() {
  const user = getUser();
  const esel = document.getElementById('equipment-select');
  const equipName = esel.value ? esel.options[esel.selectedIndex].text : 'None';
  document.getElementById('summary-card').innerHTML = `
    <div><span style="color:#6b7a8d;">Item:</span> ${wiz.selectedItem ? wiz.selectedItem.name : '—'}</div>
    <div><span style="color:#6b7a8d;">Field:</span> ${wiz.selectedField ? wiz.selectedField.name : '—'}</div>
    <div><span style="color:#6b7a8d;">Plot:</span> ${wiz.selectedPlot ? wiz.selectedPlot.plot_code : '—'} (${wiz.selectedPlot ? wiz.selectedPlot.area_ha : '—'} ha)</div>
    <div><span style="color:#6b7a8d;">Quantity:</span> ${wiz.quantity} ${wiz.selectedItem ? wiz.selectedItem.unit : ''}</div>
    <div><span style="color:#6b7a8d;">Equipment:</span> ${equipName}</div>
    <div><span style="color:#6b7a8d;">Logged by:</span> ${user ? user.name : '—'}</div>
    <div><span style="color:#6b7a8d;">Estimate type:</span> ${wiz.aiCorrected ? 'Manual override' : wiz.aiEstimated ? 'AI estimated' : 'Manual'}</div>
  `;
}

async function submitLog() {
  const btn = document.getElementById('submit-btn');
  btn.disabled = true; btn.textContent = 'Logging…';
  try {
    const r = await apiFetch('/api/logs', {
      method: 'POST',
      body: JSON.stringify({
        inventory_item_id: wiz.selectedItem.id,
        plot_id: wiz.selectedPlot.id,
        equipment_id: wiz.selectedEquipment ? wiz.selectedEquipment.id : null,
        quantity_used: wiz.quantity,
        ai_estimated: wiz.aiEstimated,
        ai_estimate_corrected: wiz.aiCorrected,
        notes: '',
      }),
    });
    if (!r.ok) {
      const err = await r.json();
      showToast(`Error: ${err.detail}`, true);
    } else {
      closeWizard();
      showToast('Logged successfully');
    }
  } catch (e) {
    showToast('Failed to submit. Check API server.', true);
  }
  btn.disabled = false; btn.textContent = 'Confirm & Log';
}

function showToast(msg, isError = false) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.style.background = isError ? '#3a1a1a' : '#1a3a1a';
  el.style.borderColor = isError ? '#6a2d2d' : '#2d6a2d';
  el.style.color = isError ? '#cf6f6f' : '#6fcf6f';
  el.style.display = 'block';
  el.style.opacity = '1';
  setTimeout(() => {
    el.style.opacity = '0';
    setTimeout(() => { el.style.display = 'none'; }, 300);
  }, 3000);
}
```

- [ ] **Step 4: Verify wizard end-to-end**

Start both servers:
```bash
# Terminal 1
python3 api.py

# Terminal 2
node serve.mjs
```

1. Open `http://localhost:3000`
2. Log in with NUID `12345678` / password `admin123`
3. Click "+ Log Usage" in the nav
4. Select category → item → field → plot → confirm quantity → submit
5. Verify green toast appears
6. Check DB: `sqlite3 /Users/ishratjandu/AI_Pitla/results/farm_manager.db "SELECT * FROM usage_logs ORDER BY id DESC LIMIT 3;"`

- [ ] **Step 5: Commit**

```bash
git add v2/index.html
git commit -m "feat: add 4-step usage logging wizard to frontend"
```

---

## Task 7: Final Test Run

- [ ] **Step 1: Run full backend test suite**

```bash
cd /Users/ishratjandu/AI_Pitla/Semester_project/farm_manager_step1
python3 -m pytest tests/test_api.py -v
```

Expected: all PASSED (health + auth + inventory + fields + plots + equipment + log tests)

- [ ] **Step 2: Verify inventory depletion in real DB**

```bash
sqlite3 /Users/ishratjandu/AI_Pitla/results/farm_manager.db \
  "SELECT name, quantity_on_hand, unit FROM inventory_items LIMIT 10;"
```

- [ ] **Step 3: Verify usage and activity logs**

```bash
sqlite3 /Users/ishratjandu/AI_Pitla/results/farm_manager.db \
  "SELECT ul.id, ii.name, ul.quantity_used, ul.ai_estimated, ul.log_date
   FROM usage_logs ul JOIN inventory_items ii ON ul.inventory_item_id = ii.id
   ORDER BY ul.id DESC LIMIT 5;"
```

```bash
sqlite3 /Users/ishratjandu/AI_Pitla/results/farm_manager.db \
  "SELECT al.action, al.detail, al.timestamp FROM activity_logs al ORDER BY al.id DESC LIMIT 5;"
```

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "feat: complete usage logging wizard — backend + frontend"
```
