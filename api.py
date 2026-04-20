"""
api.py
------
FastAPI backend for the FarmOS usage logging wizard.
Run with: python3 api.py  (starts on http://localhost:8000)
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, TypedDict

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
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Add it to .env — must match the value "
        "used by server.py / database.py so both services share one file."
    )
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

# Single-farm deployment assumption; used by inventory/log endpoints
FARM_ID = 1


# ── SESSION STORE ─────────────────────────────────────────────────────────────
class SessionUser(TypedDict):
    user_id: int
    name: str
    session_id: str  # stored for future audit log correlation; not yet used by endpoints

# In-memory: token -> SessionUser; cleared on process restart (tab-session contract)
sessions: dict[str, SessionUser] = {}

# ── APP ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="FarmOS API")

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


# ── DB DEPENDENCY ─────────────────────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── AUTH DEPENDENCY ───────────────────────────────────────────────────────────
def get_current_user(authorization: Optional[str] = Header(default=None)) -> SessionUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if token not in sessions:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return sessions[token]


# ── PYDANTIC MODELS ───────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    nuid: str
    password: str


# ── HEALTH ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


# ── AUTH ENDPOINTS ────────────────────────────────────────────────────────────
@app.post("/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(nuid=req.nuid, is_active=True).first()
    if not user or not check_password_hash(user.password_hash, req.password):
        raise HTTPException(status_code=401, detail="Invalid NUID or password")
    token = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    sessions[token] = SessionUser(user_id=user.id, name=user.name, session_id=session_id)
    return {"token": token, "user_id": user.id, "name": user.name}


@app.post("/auth/logout")
def logout(authorization: str = Header(...), current_user: SessionUser = Depends(get_current_user)):
    token = authorization.removeprefix("Bearer ").strip()
    sessions.pop(token, None)
    return {"status": "logged out"}


# ── READ ENDPOINTS ────────────────────────────────────────────────────────────

@app.get("/api/inventory")
def get_inventory(
    category: Optional[str] = None,
    search: Optional[str] = None,
    current_user: SessionUser = Depends(get_current_user),
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
    current_user: SessionUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fields = db.query(Field).filter_by(farm_id=FARM_ID).order_by(Field.name).all()
    return [{"id": f.id, "name": f.name, "area_ha": f.area_ha} for f in fields]


@app.get("/api/plots")
def get_plots(
    field_id: int,
    current_user: SessionUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plots = (
        db.query(Plot)
        .join(Field, Plot.field_id == Field.id)
        .filter(Field.farm_id == FARM_ID, Plot.field_id == field_id)
        .order_by(Plot.plot_code)
        .all()
    )
    return [
        {"id": p.id, "plot_code": p.plot_code, "area_ha": p.area_ha, "replication": p.replication}
        for p in plots
    ]


@app.get("/api/equipment")
def get_equipment(
    current_user: SessionUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    equip = db.query(Equipment).filter_by(farm_id=FARM_ID).order_by(Equipment.name).all()
    return [
        {
            "id": e.id,
            "name": e.name,
            "equipment_type": e.equipment_type,
            "chemical_rate_l_per_ha": e.chemical_rate_l_per_ha,
        }
        for e in equip
    ]


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
    current_user: SessionUser = Depends(get_current_user),
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


if __name__ == "__main__":
    host = os.environ.get("API_HOST", "127.0.0.1")
    port = int(os.environ.get("API_PORT", "8000"))
    reload_flag = os.environ.get("API_RELOAD", "false").lower() in ("true", "1", "yes")
    uvicorn.run("api:app", host=host, port=port, reload=reload_flag)
