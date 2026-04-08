"""
api.py
------
FastAPI backend for the FarmOS usage logging wizard.
Run with: python3 api.py  (starts on http://localhost:8000)
"""
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
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
_DEFAULT_DB = Path(__file__).parent.parent / "results" / "farm_manager.db"
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{_DEFAULT_DB}")
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
def get_current_user(authorization: str = Header(...)) -> SessionUser:
    if not authorization.startswith("Bearer "):
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
    plots = db.query(Plot).filter_by(field_id=field_id).order_by(Plot.plot_code).all()
    return [
        {"id": p.id, "plot_code": p.plot_code, "area_ha": p.area_ha, "replication": p.replication}
        for p in plots
    ]


@app.get("/api/equipment")
def get_equipment(
    current_user: SessionUser = Depends(get_current_user),
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


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
