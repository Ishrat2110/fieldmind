"""
models.py
---------
Database schema for the AI-Powered Research Farm Manager.
"""

from datetime import datetime, timezone
import enum
import sqlite3

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    DateTime, ForeignKey, Text, Enum, UniqueConstraint, event
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# ── enforce FK constraints on every SQLite connection ──────────────────────────
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# ─────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────

class UserRole(str, enum.Enum):
    admin   = "admin"
    manager = "manager"
    viewer  = "viewer"

class FieldStatus(str, enum.Enum):
    active    = "active"
    fallow    = "fallow"
    harvested = "harvested"

class TreatmentType(str, enum.Enum):
    scheduled = "scheduled"
    reactive  = "reactive"

class NotificationStatus(str, enum.Enum):
    pending   = "pending"
    approved  = "approved"
    dismissed = "dismissed"


# ─────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True)
    name          = Column(String(120), nullable=False)
    email         = Column(String(200), unique=True, nullable=False)
    nuid          = Column(String(20),  unique=True, nullable=True)
    password_hash = Column(String(256), nullable=False)
    role          = Column(Enum(UserRole), default=UserRole.manager, nullable=False)
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active     = Column(Boolean, default=True)

    farm_memberships = relationship("FarmMember", back_populates="user",
                                    cascade="all, delete-orphan")
    usage_logs       = relationship("UsageLog",   back_populates="logged_by_user")

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


# ─────────────────────────────────────────────
# FARMS & MEMBERSHIP
# ─────────────────────────────────────────────

class Farm(Base):
    __tablename__ = "farms"

    id            = Column(Integer, primary_key=True)
    name          = Column(String(200), nullable=False)
    location      = Column(String(300))
    total_area_ha = Column(Float)
    notes         = Column(Text)
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    members       = relationship("FarmMember",    back_populates="farm",
                                 cascade="all, delete-orphan")
    fields        = relationship("Field",         back_populates="farm",
                                 cascade="all, delete-orphan")
    inventory     = relationship("InventoryItem", back_populates="farm",
                                 cascade="all, delete-orphan")
    equipment     = relationship("Equipment",     back_populates="farm",
                                 cascade="all, delete-orphan")
    notifications = relationship("Notification",  back_populates="farm",
                                 cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Farm '{self.name}' ({self.total_area_ha} ha)>"


class FarmMember(Base):
    __tablename__ = "farm_members"
    __table_args__ = (UniqueConstraint("farm_id", "user_id", name="uq_farm_member"),)

    id      = Column(Integer, primary_key=True)
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role    = Column(Enum(UserRole), default=UserRole.manager)

    farm = relationship("Farm", back_populates="members")
    user = relationship("User", back_populates="farm_memberships")


# ─────────────────────────────────────────────
# CROPS & VARIETIES
# ─────────────────────────────────────────────

class CropSpecies(Base):
    __tablename__ = "crop_species"

    id                  = Column(Integer, primary_key=True)
    common_name         = Column(String(100), nullable=False)
    scientific_name     = Column(String(200))
    typical_season_days = Column(Integer)
    notes               = Column(Text)

    varieties = relationship("CropVariety", back_populates="species",
                             cascade="all, delete-orphan")

    def __repr__(self):
        return f"<CropSpecies '{self.common_name}'>"


class CropVariety(Base):
    __tablename__ = "crop_varieties"

    id              = Column(Integer, primary_key=True)
    species_id      = Column(Integer, ForeignKey("crop_species.id", ondelete="CASCADE"), nullable=False)
    variety_code    = Column(String(100), nullable=False)
    variety_name    = Column(String(200))
    is_experimental = Column(Boolean, default=False)
    season_days     = Column(Integer)
    notes           = Column(Text)

    species          = relationship("CropSpecies",    back_populates="varieties")
    plots            = relationship("Plot",           back_populates="variety")
    growth_stages    = relationship("GrowthStage",    back_populates="variety",
                                   cascade="all, delete-orphan")
    treatment_plans  = relationship("TreatmentPlan",  back_populates="variety")

    def __repr__(self):
        return f"<CropVariety '{self.variety_code}'>"


class GrowthStage(Base):
    __tablename__ = "growth_stages"

    id         = Column(Integer, primary_key=True)
    variety_id = Column(Integer, ForeignKey("crop_varieties.id", ondelete="CASCADE"), nullable=False)
    stage_code = Column(String(20),  nullable=False)
    stage_name = Column(String(100))
    day_offset = Column(Integer, nullable=False)
    notes      = Column(Text)

    variety = relationship("CropVariety", back_populates="growth_stages")

    def __repr__(self):
        return f"<GrowthStage {self.stage_code} @ day {self.day_offset}>"


# ─────────────────────────────────────────────
# FIELDS & PLOTS
# ─────────────────────────────────────────────

class Field(Base):
    __tablename__ = "fields"

    id        = Column(Integer, primary_key=True)
    farm_id   = Column(Integer, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False)
    name      = Column(String(100), nullable=False)
    area_ha   = Column(Float)
    soil_type = Column(String(100))
    status    = Column(Enum(FieldStatus), default=FieldStatus.active)
    notes     = Column(Text)

    farm  = relationship("Farm",  back_populates="fields")
    plots = relationship("Plot",  back_populates="field",
                         cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Field '{self.name}' ({self.area_ha} ha)>"


class Plot(Base):
    __tablename__ = "plots"
    __table_args__ = (UniqueConstraint("field_id", "plot_code", name="uq_plot_field_code"),)

    id            = Column(Integer, primary_key=True)
    field_id      = Column(Integer, ForeignKey("fields.id",        ondelete="CASCADE"), nullable=False)
    variety_id    = Column(Integer, ForeignKey("crop_varieties.id", ondelete="RESTRICT"), nullable=False)
    plot_code     = Column(String(50), nullable=False)
    replication   = Column(Integer, default=1)
    area_ha       = Column(Float)
    planting_date = Column(DateTime)
    harvest_date  = Column(DateTime)
    notes         = Column(Text)

    field           = relationship("Field",         back_populates="plots")
    variety         = relationship("CropVariety",   back_populates="plots")
    treatment_plans = relationship("TreatmentPlan", back_populates="plot",
                                   cascade="all, delete-orphan")
    usage_logs      = relationship("UsageLog",      back_populates="plot")

    def __repr__(self):
        return f"<Plot '{self.plot_code}' rep{self.replication}>"


# ─────────────────────────────────────────────
# EQUIPMENT
# ─────────────────────────────────────────────

class Equipment(Base):
    __tablename__ = "equipment"

    id                     = Column(Integer, primary_key=True)
    farm_id                = Column(Integer, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False)
    name                   = Column(String(150), nullable=False)
    equipment_type         = Column(String(100))
    fuel_rate_l_per_hr     = Column(Float)
    chemical_rate_l_per_ha = Column(Float)
    notes                  = Column(Text)

    farm       = relationship("Farm",     back_populates="equipment")
    usage_logs = relationship("UsageLog", back_populates="equipment")

    def __repr__(self):
        return f"<Equipment '{self.name}' ({self.equipment_type})>"


# ─────────────────────────────────────────────
# INVENTORY
# ─────────────────────────────────────────────

class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (UniqueConstraint("farm_id", "name", name="uq_inventory_farm_name"),)

    id                = Column(Integer, primary_key=True)
    farm_id           = Column(Integer, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False)
    name              = Column(String(200), nullable=False)
    category          = Column(String(100))
    unit              = Column(String(30),  nullable=False)
    quantity_on_hand  = Column(Float, default=0.0)
    reorder_threshold = Column(Float)
    reorder_quantity  = Column(Float)
    supplier          = Column(String(200))
    unit_cost         = Column(Float)
    notes             = Column(Text)
    last_updated      = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                               onupdate=lambda: datetime.now(timezone.utc))

    farm       = relationship("Farm",     back_populates="inventory")
    usage_logs = relationship("UsageLog", back_populates="inventory_item",
                              cascade="all, delete-orphan")

    def __repr__(self):
        return f"<InventoryItem '{self.name}' — {self.quantity_on_hand} {self.unit}>"


# ─────────────────────────────────────────────
# TREATMENT PLANS
# ─────────────────────────────────────────────

class TreatmentPlan(Base):
    __tablename__ = "treatment_plans"

    id                = Column(Integer, primary_key=True)
    plot_id           = Column(Integer, ForeignKey("plots.id",           ondelete="CASCADE"),  nullable=False)
    variety_id        = Column(Integer, ForeignKey("crop_varieties.id",  ondelete="RESTRICT"), nullable=False)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False)
    growth_stage_id   = Column(Integer, ForeignKey("growth_stages.id",   ondelete="RESTRICT"), nullable=False)
    treatment_type    = Column(Enum(TreatmentType), default=TreatmentType.scheduled)
    rate_per_ha       = Column(Float, nullable=False)
    planned_date      = Column(DateTime)
    applied           = Column(Boolean, default=False)
    applied_date      = Column(DateTime)
    notes             = Column(Text)

    plot           = relationship("Plot",          back_populates="treatment_plans")
    variety        = relationship("CropVariety",   back_populates="treatment_plans")
    inventory_item = relationship("InventoryItem")
    growth_stage   = relationship("GrowthStage")

    def __repr__(self):
        return f"<TreatmentPlan plot={self.plot_id} item={self.inventory_item_id}>"


# ─────────────────────────────────────────────
# USAGE LOGS
# ─────────────────────────────────────────────

class UsageLog(Base):
    __tablename__ = "usage_logs"

    id                    = Column(Integer, primary_key=True)
    inventory_item_id     = Column(Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"),  nullable=False)
    plot_id               = Column(Integer, ForeignKey("plots.id",           ondelete="SET NULL"))
    equipment_id          = Column(Integer, ForeignKey("equipment.id",       ondelete="SET NULL"))
    logged_by             = Column(Integer, ForeignKey("users.id",           ondelete="RESTRICT"), nullable=False)
    quantity_used         = Column(Float, nullable=False)
    log_date              = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ai_estimated          = Column(Boolean, default=False)
    ai_estimate_corrected = Column(Boolean, default=False)
    notes                 = Column(Text)

    inventory_item = relationship("InventoryItem", back_populates="usage_logs")
    plot           = relationship("Plot",          back_populates="usage_logs")
    equipment      = relationship("Equipment",     back_populates="usage_logs")
    logged_by_user = relationship("User",          back_populates="usage_logs")

    def __repr__(self):
        return f"<UsageLog item={self.inventory_item_id} qty={self.quantity_used}>"


# ─────────────────────────────────────────────
# NOTIFICATIONS
# ─────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    id                  = Column(Integer, primary_key=True)
    farm_id             = Column(Integer, ForeignKey("farms.id",           ondelete="CASCADE"),  nullable=False)
    inventory_item_id   = Column(Integer, ForeignKey("inventory_items.id", ondelete="SET NULL"))
    status              = Column(Enum(NotificationStatus), default=NotificationStatus.pending)
    predicted_stockout  = Column(DateTime)
    days_until_stockout = Column(Integer)
    current_stock       = Column(Float)
    ai_message          = Column(Text, nullable=False)
    draft_order_qty     = Column(Float)
    draft_order_sent    = Column(Boolean, default=False)
    created_at          = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at         = Column(DateTime)

    farm           = relationship("Farm",          back_populates="notifications")
    inventory_item = relationship("InventoryItem")

    def __repr__(self):
        return f"<Notification item={self.inventory_item_id} [{self.status}]>"


# ─────────────────────────────────────────────
# ACTIVITY LOG
# ─────────────────────────────────────────────

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    session_id = Column(String(36), nullable=False)   # UUID per login session
    action     = Column(String(80), nullable=False)   # e.g. "login", "log_usage"
    detail     = Column(Text)                          # human-readable description
    timestamp  = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")

    def __repr__(self):
        return f"<ActivityLog user={self.user_id} action={self.action}>"
