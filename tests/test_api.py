"""Tests for api.py — uses FastAPI TestClient with in-memory SQLite."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api import app, get_db, sessions
from models import Base, User, Farm, FarmMember, Field, Plot, Equipment, InventoryItem, UsageLog
from werkzeug.security import generate_password_hash

# ── IN-MEMORY DB FIXTURE ──────────────────────────────────────────────────────
# StaticPool ensures all connections share the same in-memory SQLite database.
TEST_DB_URL = "sqlite:///:memory:"

@pytest.fixture(autouse=True)
def clear_sessions():
    """Clear in-memory session store before each test to prevent state leakage."""
    sessions.clear()
    yield
    sessions.clear()


@pytest.fixture(scope="function")
def db_session():
    _engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(_engine)
    TestingSession = sessionmaker(bind=_engine)
    session = TestingSession()
    yield session
    session.rollback()
    session.close()
    Base.metadata.drop_all(_engine)
    _engine.dispose()


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def seeded_db(db_session):
    """Minimal seed: 1 user, 1 farm, 1 field, 1 plot, 1 equipment, 1 inventory item."""
    from models import UserRole, FieldStatus, CropSpecies, CropVariety
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


def test_login_inactive_user(client, seeded_db, db_session):
    seeded_db["user"].is_active = False
    db_session.commit()
    response = client.post("/auth/login", json={"nuid": "11111111", "password": "testpass"})
    assert response.status_code == 401


def test_logout(client, seeded_db):
    login = client.post("/auth/login", json={"nuid": "11111111", "password": "testpass"})
    token = login.json()["token"]
    response = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"status": "logged out"}
    # Verify token is removed from sessions store
    # Try to log out again with same token - should get 401
    response2 = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert response2.status_code == 401


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
    assert len(items) == 1
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


# ── PROTECTED ENDPOINT WITHOUT TOKEN ──────────────────────────────────────────
def test_protected_endpoint_without_token(client, seeded_db):
    response = client.get("/api/fields")
    assert response.status_code == 401  # missing Authorization header


# ── USAGE LOG SUBMISSION ──────────────────────────────────────────────────────
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
