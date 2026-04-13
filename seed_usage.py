"""
seed_usage.py
-------------
Seeds 30 days of realistic usage logs for all inventory items
so the depletion forecast chart has data to work with.

Run once:
    python3 seed_usage.py
"""

from datetime import datetime, timedelta, timezone
import random
from database import get_session
from models import InventoryItem, UsageLog, Equipment, Plot, User, Farm

session = get_session()

farm     = session.query(Farm).first()
user     = session.query(User).first()
equip    = session.query(Equipment).all()
plots    = session.query(Plot).all()
items    = session.query(InventoryItem).filter_by(farm_id=farm.id).all()

tractor  = next((e for e in equip if e.equipment_type == "tractor"), equip[0])
sprayer  = next((e for e in equip if e.equipment_type == "sprayer"), equip[0])

# Daily usage profiles per category (realistic Nebraska research farm)
USAGE_PROFILES = {
    "fuel":       {"mean": 171.0, "std": 30.0,  "days_active": 0.9, "equipment": tractor},
    "fertilizer": {"mean": 80.0,  "std": 20.0,  "days_active": 0.3, "equipment": tractor},
    "herbicide":  {"mean": 12.0,  "std": 4.0,   "days_active": 0.25,"equipment": sprayer},
    "fungicide":  {"mean": 3.5,   "std": 1.0,   "days_active": 0.15,"equipment": sprayer},
    "seed":       {"mean": 2.0,   "std": 0.5,   "days_active": 0.1, "equipment": tractor},
}

today = datetime.now()
added = 0

for item in items:
    profile = USAGE_PROFILES.get(item.category)
    if not profile:
        continue

    # Check how many logs already exist
    existing = session.query(UsageLog).filter_by(inventory_item_id=item.id).count()

    for days_ago in range(30, 0, -1):
        # Only log on active days based on profile
        if random.random() > profile["days_active"]:
            continue

        qty = max(0.1, random.gauss(profile["mean"], profile["std"]))
        qty = round(qty, 1)

        log_date = today - timedelta(days=days_ago)
        plot = random.choice(plots) if plots else None

        session.add(UsageLog(
            inventory_item_id=item.id,
            plot_id=plot.id if plot else None,
            equipment_id=profile["equipment"].id if profile["equipment"] else None,
            logged_by=user.id,
            quantity_used=qty,
            log_date=log_date,
            notes=f"Seeded sample log — {item.category}"
        ))
        added += 1

session.commit()
print(f"✓ Added {added} sample usage logs across {len(items)} inventory items.")
print("  Refresh the farm map to see depletion forecasts.")
