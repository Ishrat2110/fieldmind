"""Tests for api.py — uses FastAPI TestClient with in-memory SQLite."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api import app, get_db, sessions
from models import Base, User, Farm, FarmMember, Field, Plot, Equipment, InventoryItem
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
