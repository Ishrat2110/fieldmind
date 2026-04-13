"""
database.py
-----------
Database initialization and connection management.
Run this file directly to create and seed the database with
a realistic research farm scenario.

Usage:
    python database.py
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta, timezone
from models import (
    Base, User, UserRole, Farm, FarmMember,
    CropSpecies, CropVariety, GrowthStage,
    Field, FieldStatus, Plot,
    Equipment, InventoryItem,
    TreatmentPlan, TreatmentType,
    UsageLog, Notification
)
import sys
from werkzeug.security import generate_password_hash

DATABASE_URL = "sqlite:////Users/ishratjandu/AI_Pitla/results/farm_manager.db"

engine = create_engine(DATABASE_URL, echo=False)
Session = sessionmaker(bind=engine)


def get_session():
    return Session()


def init_db():
    """Create all tables."""
    Base.metadata.create_all(engine)
    print("✓ Database tables created.")


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def seed_db():
    """
    Seed the database with a realistic UNL research farm scenario:
      - 2 users (admin + manager)
      - 1 research farm
      - 2 fields, 8 plots
      - 2 crop species (Corn, Soybean), 4 varieties each
      - Growth stages for each variety
      - Equipment (tractor + sprayer)
      - Inventory (fertilizer, herbicide, fuel, seed)
      - Treatment plans per plot per growth stage
      - Some historical usage logs
    """
    session = get_session()

    # Skip seeding if data already exists (pass --force to re-seed)
    force = "--force" in sys.argv
    if force:
        print("⚠ --force: dropping and recreating tables...")
        session.close()
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        session = get_session()
    elif session.query(User).filter_by(email="ijandu@unl.edu").first():
        print("✓ Database already seeded, skipping. Use --force to re-seed.")
        session.close()
        return

    # ── USERS ──────────────────────────────────────
    users_data = [
        # (name,                  email,                   nuid,       password,       role)
        ("Ishrat Jandu",          "ijandu@unl.edu",        "12345678", "admin123",     UserRole.admin),
        ("Marcus Webb",           "mwebb2@unl.edu",        "87654321", "manager123",   UserRole.manager),
        ("Sara Okonkwo",          "sokonkwo@unl.edu",      "23456789", "sara2024",     UserRole.manager),
        ("Daniel Reyes",          "dreyes3@unl.edu",       "34567890", "dreyes2024",   UserRole.viewer),
        ("Priya Nair",            "pnair@unl.edu",         "45678901", "pnair2024",    UserRole.viewer),
        ("Tom Hartmann",          "thartmann@unl.edu",     "56789012", "tomh2024",     UserRole.viewer),
        ("Aisha Kamara",          "akamara2@unl.edu",      "67890123", "aisha2024",    UserRole.viewer),
        ("Levi Schultz",          "lschultz4@unl.edu",     "78901234", "levi2024",     UserRole.viewer),
        ("Mei-Ling Chen",         "mchen5@unl.edu",        "89012345", "meiling2024",  UserRole.viewer),
        ("James Oduya",           "joduya@unl.edu",        "90123456", "james2024",    UserRole.viewer),
    ]

    user_objects = []
    for name, email, nuid, password, role in users_data:
        u = User(
            name=name,
            email=email,
            nuid=nuid,
            password_hash=hash_password(password),
            role=role,
        )
        user_objects.append(u)
        session.add(u)

    session.flush()
    admin   = user_objects[0]
    manager = user_objects[1]
    print(f"✓ {len(user_objects)} users created.")

    # ── FARM ───────────────────────────────────────
    farm = Farm(
        name="UNL Research Farm — East Campus",
        location="Lincoln, NE",
        total_area_ha=48.5,
        notes="Primary variety trial farm for BSE/AGEN research programs."
    )
    session.add(farm)
    session.flush()

    for u in user_objects:
        session.add(FarmMember(farm_id=farm.id, user_id=u.id, role=u.role))
    print("✓ Farm and memberships created.")

    # ── CROP SPECIES ────────────────────────────────
    corn = CropSpecies(
        common_name="Corn",
        scientific_name="Zea mays",
        typical_season_days=120
    )
    soy = CropSpecies(
        common_name="Soybean",
        scientific_name="Glycine max",
        typical_season_days=100
    )
    session.add_all([corn, soy])
    session.flush()
    print("✓ Crop species created.")

    # ── CROP VARIETIES ──────────────────────────────
    corn_vars = [
        CropVariety(species_id=corn.id, variety_code="DKC65-84",  variety_name="DeKalb 65-84",         is_experimental=False, season_days=118),
        CropVariety(species_id=corn.id, variety_code="P1197AM",   variety_name="Pioneer P1197AM",        is_experimental=False, season_days=114),
        CropVariety(species_id=corn.id, variety_code="UNL-X23",   variety_name="UNL Experimental Line 23", is_experimental=True,  season_days=122),
        CropVariety(species_id=corn.id, variety_code="UNL-X24",   variety_name="UNL Experimental Line 24", is_experimental=True,  season_days=119),
    ]
    soy_vars = [
        CropVariety(species_id=soy.id,  variety_code="AG36X6",    variety_name="Asgrow AG36X6",          is_experimental=False, season_days=98),
        CropVariety(species_id=soy.id,  variety_code="NK-S38",    variety_name="NK S38-H8",              is_experimental=False, season_days=102),
        CropVariety(species_id=soy.id,  variety_code="UNL-SX1",   variety_name="UNL Soy Experimental 1", is_experimental=True,  season_days=96),
        CropVariety(species_id=soy.id,  variety_code="UNL-SX2",   variety_name="UNL Soy Experimental 2", is_experimental=True,  season_days=104),
    ]
    all_varieties = corn_vars + soy_vars
    session.add_all(all_varieties)
    session.flush()
    print("✓ Crop varieties created.")

    # ── GROWTH STAGES ───────────────────────────────
    # Corn growth stages (same schedule for all corn varieties here,
    # in production each variety can have its own offsets)
    corn_stages_data = [
        ("VE",  "Emergence",            7),
        ("V3",  "Three-leaf stage",    18),
        ("V6",  "Six-leaf stage",      35),
        ("V10", "Ten-leaf stage",      50),
        ("VT",  "Tasseling",           65),
        ("R1",  "Silking",             70),
        ("R3",  "Milk stage",          85),
        ("R6",  "Physiological maturity", 110),
    ]
    soy_stages_data = [
        ("VE",  "Emergence",            6),
        ("V2",  "Second node",         16),
        ("V4",  "Fourth node",         28),
        ("R1",  "Beginning bloom",     45),
        ("R3",  "Beginning pod",       60),
        ("R5",  "Beginning seed",      75),
        ("R7",  "Physiological maturity", 92),
    ]

    for var in corn_vars:
        for code, name, offset in corn_stages_data:
            session.add(GrowthStage(variety_id=var.id, stage_code=code, stage_name=name, day_offset=offset))

    for var in soy_vars:
        for code, name, offset in soy_stages_data:
            session.add(GrowthStage(variety_id=var.id, stage_code=code, stage_name=name, day_offset=offset))

    session.flush()
    print("✓ Growth stages created.")

    # ── FIELDS ──────────────────────────────────────
    field_a = Field(farm_id=farm.id, name="Block A — Corn Trials", area_ha=20.0, soil_type="Hastings silt loam", status=FieldStatus.active)
    field_b = Field(farm_id=farm.id, name="Block B — Soybean Trials", area_ha=18.0, soil_type="Crete silt loam",    status=FieldStatus.active)
    session.add_all([field_a, field_b])
    session.flush()
    print("✓ Fields created.")

    # ── PLOTS ───────────────────────────────────────
    planting_date = datetime(2025, 5, 1)
    corn_plots = []
    for i, var in enumerate(corn_vars):
        for rep in range(1, 3):   # 2 reps per variety = 8 corn plots
            plot = Plot(
                field_id=field_a.id,
                variety_id=var.id,
                plot_code=f"A-{(i*2)+rep:02d}",
                replication=rep,
                area_ha=2.5,
                planting_date=planting_date
            )
            corn_plots.append(plot)
            session.add(plot)

    soy_plots = []
    for i, var in enumerate(soy_vars):
        for rep in range(1, 3):   # 2 reps per variety = 8 soy plots
            plot = Plot(
                field_id=field_b.id,
                variety_id=var.id,
                plot_code=f"B-{(i*2)+rep:02d}",
                replication=rep,
                area_ha=2.25,
                planting_date=planting_date
            )
            soy_plots.append(plot)
            session.add(plot)

    session.flush()
    print("✓ Plots created (8 corn + 8 soybean).")

    # ── EQUIPMENT ───────────────────────────────────
    tractor = Equipment(
        farm_id=farm.id,
        name="John Deere 8R 310",
        equipment_type="tractor",
        fuel_rate_l_per_hr=28.5,
        notes="Primary field tractor"
    )
    sprayer = Equipment(
        farm_id=farm.id,
        name="John Deere R4045 Sprayer",
        equipment_type="sprayer",
        fuel_rate_l_per_hr=14.0,
        chemical_rate_l_per_ha=150.0,
        notes="90-ft boom sprayer"
    )
    session.add_all([tractor, sprayer])
    session.flush()
    print("✓ Equipment created.")

    # ── INVENTORY ───────────────────────────────────
    urea       = InventoryItem(farm_id=farm.id, name="Urea (46-0-0)",         category="fertilizer", unit="kg", quantity_on_hand=2400.0, reorder_threshold=500.0, reorder_quantity=2000.0, unit_cost=0.72, supplier="Nutrien Ag Solutions")
    anhydrous  = InventoryItem(farm_id=farm.id, name="Anhydrous Ammonia",     category="fertilizer", unit="kg", quantity_on_hand=1800.0, reorder_threshold=400.0, reorder_quantity=1500.0, unit_cost=0.55, supplier="Nutrien Ag Solutions")
    herbicide  = InventoryItem(farm_id=farm.id, name="Roundup PowerMAX",     category="herbicide",  unit="L",  quantity_on_hand=320.0,  reorder_threshold=80.0,  reorder_quantity=200.0,  unit_cost=8.40, supplier="Bayer Crop Science")
    fungicide  = InventoryItem(farm_id=farm.id, name="Quilt Xcel Fungicide", category="fungicide",  unit="L",  quantity_on_hand=95.0,   reorder_threshold=30.0,  reorder_quantity=100.0,  unit_cost=24.50,supplier="Syngenta")
    diesel     = InventoryItem(farm_id=farm.id, name="Diesel Fuel",           category="fuel",       unit="L",  quantity_on_hand=3200.0, reorder_threshold=800.0, reorder_quantity=3000.0, unit_cost=1.05, supplier="Bosselman Energy")
    corn_seed  = InventoryItem(farm_id=farm.id, name="Corn Seed — Mixed Trials", category="seed",   unit="bags", quantity_on_hand=48.0, reorder_threshold=10.0, reorder_quantity=40.0,   unit_cost=285.0,supplier="Various")
    soy_seed   = InventoryItem(farm_id=farm.id, name="Soybean Seed — Mixed Trials", category="seed", unit="bags", quantity_on_hand=36.0, reorder_threshold=8.0,  reorder_quantity=32.0,   unit_cost=52.0, supplier="Various")

    all_inventory = [urea, anhydrous, herbicide, fungicide, diesel, corn_seed, soy_seed]
    session.add_all(all_inventory)
    session.flush()
    print("✓ Inventory items created.")

    # ── TREATMENT PLANS ─────────────────────────────
    # For each corn plot: herbicide at V3, urea at V6, fungicide at VT
    for plot in corn_plots:
        # get stages for this variety
        stages = {s.stage_code: s for s in plot.variety.growth_stages}
        planned_base = planting_date

        if "V3" in stages:
            session.add(TreatmentPlan(
                plot_id=plot.id, variety_id=plot.variety_id,
                inventory_item_id=herbicide.id,
                growth_stage_id=stages["V3"].id,
                treatment_type=TreatmentType.scheduled,
                rate_per_ha=2.5,
                planned_date=planned_base + timedelta(days=stages["V3"].day_offset)
            ))
        if "V6" in stages:
            session.add(TreatmentPlan(
                plot_id=plot.id, variety_id=plot.variety_id,
                inventory_item_id=urea.id,
                growth_stage_id=stages["V6"].id,
                treatment_type=TreatmentType.scheduled,
                rate_per_ha=120.0,
                planned_date=planned_base + timedelta(days=stages["V6"].day_offset)
            ))
        if "VT" in stages:
            session.add(TreatmentPlan(
                plot_id=plot.id, variety_id=plot.variety_id,
                inventory_item_id=fungicide.id,
                growth_stage_id=stages["VT"].id,
                treatment_type=TreatmentType.scheduled,
                rate_per_ha=0.75,
                planned_date=planned_base + timedelta(days=stages["VT"].day_offset)
            ))

    # For each soy plot: herbicide at V2, anhydrous at R1
    for plot in soy_plots:
        stages = {s.stage_code: s for s in plot.variety.growth_stages}
        planned_base = planting_date

        if "V2" in stages:
            session.add(TreatmentPlan(
                plot_id=plot.id, variety_id=plot.variety_id,
                inventory_item_id=herbicide.id,
                growth_stage_id=stages["V2"].id,
                treatment_type=TreatmentType.scheduled,
                rate_per_ha=2.0,
                planned_date=planned_base + timedelta(days=stages["V2"].day_offset)
            ))
        if "R1" in stages:
            session.add(TreatmentPlan(
                plot_id=plot.id, variety_id=plot.variety_id,
                inventory_item_id=anhydrous.id,
                growth_stage_id=stages["R1"].id,
                treatment_type=TreatmentType.scheduled,
                rate_per_ha=60.0,
                planned_date=planned_base + timedelta(days=stages["R1"].day_offset)
            ))

    session.flush()
    print("✓ Treatment plans created.")

    # ── USAGE LOGS (historical) ──────────────────────
    # Simulate 2 weeks of usage
    today = datetime.now(timezone.utc)
    for days_ago in range(14, 0, -1):
        log_date = today - timedelta(days=days_ago)
        # daily diesel use from tractor fieldwork
        session.add(UsageLog(
            inventory_item_id=diesel.id,
            equipment_id=tractor.id,
            logged_by=manager.id,
            quantity_used=round(tractor.fuel_rate_l_per_hr * 6, 1),  # ~6 hrs/day
            log_date=log_date,
            notes="Daily field operations"
        ))
        # herbicide spray every 4 days
        if days_ago % 4 == 0:
            session.add(UsageLog(
                inventory_item_id=herbicide.id,
                equipment_id=sprayer.id,
                plot_id=corn_plots[0].id,
                logged_by=manager.id,
                quantity_used=round(2.5 * corn_plots[0].area_ha, 1),
                log_date=log_date,
                notes="V3 herbicide application — Block A"
            ))

    session.flush()
    print("✓ Historical usage logs created.")

    session.commit()
    print("\n✅ Database seeded successfully.")
    print(f"   Farm:       {farm.name}")
    print(f"   Users:      {session.query(User).count()}")
    print(f"   Varieties:  {session.query(CropVariety).count()} ({len(corn_vars)} corn + {len(soy_vars)} soybean)")
    print(f"   Plots:      {session.query(Plot).count()} ({len(corn_plots)} corn + {len(soy_plots)} soy)")
    print(f"   Inventory:  {session.query(InventoryItem).count()} items")
    print(f"   Treatments: {session.query(TreatmentPlan).count()} planned applications")
    print(f"   Usage logs: {session.query(UsageLog).count()} records")
    session.close()


if __name__ == "__main__":
    print("Initializing Farm Manager database...\n")
    init_db()
    seed_db()
