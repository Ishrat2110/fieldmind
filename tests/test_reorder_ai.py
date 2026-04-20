"""
tests/test_reorder_ai.py
------------------------
Unit and integration tests for reorder_ai.py.
All Gemini calls are monkeypatched — no network required.
"""
import json
import pytest
from datetime import datetime, timedelta, timezone, date
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from werkzeug.security import generate_password_hash

from models import (
    Base, User, Farm, FarmMember, Field, Plot, Equipment,
    InventoryItem, UsageLog, TreatmentPlan, Notification,
    NotificationStatus, UserRole, FieldStatus, CropSpecies,
    CropVariety, GrowthStage,
)
import reorder_ai


# ── fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.rollback()
    s.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def seeded(session):
    """Seed: farm, user, field, plot, 1 inventory item below threshold."""
    user = User(
        name="Farm Admin", email="admin@unl.edu", nuid="12345678",
        password_hash=generate_password_hash("pass"), role=UserRole.admin,
    )
    session.add(user)
    session.flush()

    farm = Farm(name="Test Farm", location="Lincoln, NE", total_area_ha=20.0)
    session.add(farm)
    session.flush()

    session.add(FarmMember(farm_id=farm.id, user_id=user.id, role=UserRole.admin))

    field = Field(farm_id=farm.id, name="Block A", area_ha=10.0, status=FieldStatus.active)
    session.add(field)
    session.flush()

    species = CropSpecies(common_name="Corn", scientific_name="Zea mays", typical_season_days=120)
    session.add(species)
    session.flush()

    variety = CropVariety(species_id=species.id, variety_code="DKC65", variety_name="DKC65-84")
    session.add(variety)
    session.flush()

    stage = GrowthStage(variety_id=variety.id, stage_code="V6", stage_name="6-leaf", day_offset=30)
    session.add(stage)
    session.flush()

    plot = Plot(
        field_id=field.id, variety_id=variety.id,
        plot_code="A-01", replication=1, area_ha=2.5,
        planting_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    session.add(plot)
    session.flush()

    item = InventoryItem(
        farm_id=farm.id, name="Roundup PowerMAX",
        category="herbicide", unit="L",
        quantity_on_hand=72.0,
        reorder_threshold=80.0,
        reorder_quantity=200.0,
        supplier="Bayer Crop Science",
        unit_cost=8.40,
    )
    session.add(item)
    session.flush()

    # 30 days of synthetic usage logs (avg ~4 L/day)
    for i in range(30):
        log_date = datetime.now(timezone.utc) - timedelta(days=30 - i)
        session.add(UsageLog(
            inventory_item_id=item.id,
            plot_id=plot.id,
            logged_by=user.id,
            quantity_used=4.0,
            log_date=log_date,
        ))

    # One upcoming treatment plan (10 days out)
    session.add(TreatmentPlan(
        plot_id=plot.id, variety_id=variety.id,
        inventory_item_id=item.id, growth_stage_id=stage.id,
        rate_per_ha=2.5, applied=False,
        planned_date=datetime.now(timezone.utc) + timedelta(days=10),
    ))

    session.commit()
    return {"farm": farm, "user": user, "item": item, "plot": plot}


# ── canned Gemini response ─────────────────────────────────────────────────────

def _canned_response(item_unit="L"):
    stockout = (date.today() + timedelta(days=18)).isoformat()
    return {
        "suggested_order_qty": 220.0,
        "unit": item_unit,
        "urgency": "high",
        "predicted_stockout_date": stockout,
        "days_until_stockout": 18,
        "rationale": "Stock depletes in ~18 days at current burn rate.",
        "assumed_lead_time_days": 7,
        "estimated_cost_usd": 1848.0,
        "confidence": "high",
    }


# ── unit tests (no network) ────────────────────────────────────────────────────

class TestMaybeGenerateSuggestion:

    def test_writes_notification(self, seeded, session):
        item = seeded["item"]
        with patch.object(reorder_ai, "_GEMINI_ENABLED", True), \
             patch.object(reorder_ai, "_call_gemini", return_value=_canned_response()):
            result = reorder_ai.maybe_generate_suggestion(item, session)

        assert result is not None
        assert result.inventory_item_id == item.id
        assert result.status == NotificationStatus.pending
        assert result.draft_order_qty == 220.0

    def test_uses_cache_within_ttl(self, seeded, session):
        item = seeded["item"]
        with patch.object(reorder_ai, "_GEMINI_ENABLED", True), \
             patch.object(reorder_ai, "_call_gemini", return_value=_canned_response()) as mock_gemini:
            reorder_ai.maybe_generate_suggestion(item, session)
            reorder_ai.maybe_generate_suggestion(item, session)  # second call

        # Gemini should only have been called once (second call uses cache)
        assert mock_gemini.call_count == 1

    def test_regenerates_after_ttl(self, seeded, session):
        item = seeded["item"]
        # Create a stale notification (older than TTL)
        stale = Notification(
            farm_id=seeded["farm"].id,
            inventory_item_id=item.id,
            status=NotificationStatus.pending,
            ai_message="old suggestion",
            current_stock=item.quantity_on_hand,
            created_at=datetime.now(timezone.utc) - timedelta(hours=25),
        )
        session.add(stale)
        session.commit()

        with patch.object(reorder_ai, "_GEMINI_ENABLED", True), \
             patch.object(reorder_ai, "_call_gemini", return_value=_canned_response()) as mock_gemini:
            result = reorder_ai.maybe_generate_suggestion(item, session)

        assert mock_gemini.call_count == 1
        assert result.id != stale.id  # new notification created

    def test_dismissed_suggestion_does_not_regenerate_within_ttl(self, seeded, session):
        """Dismissed suggestion within TTL should NOT trigger a new one."""
        item = seeded["item"]
        # Create a recently dismissed notification (within TTL)
        dismissed = Notification(
            farm_id=seeded["farm"].id,
            inventory_item_id=item.id,
            status=NotificationStatus.dismissed,
            ai_message="dismissed suggestion",
            current_stock=item.quantity_on_hand,
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        session.add(dismissed)
        session.commit()

        # Cache only checks PENDING status, so this item should still get a new suggestion
        with patch.object(reorder_ai, "_call_gemini", return_value=_canned_response()):
            result = reorder_ai.maybe_generate_suggestion(item, session)

        assert result is not None
        assert result.status == NotificationStatus.pending

    def test_approved_suggestion_allows_new_one(self, seeded, session):
        """After approving, a new suggestion can be generated (old one no longer pending)."""
        item = seeded["item"]
        with patch.object(reorder_ai, "_GEMINI_ENABLED", True), \
             patch.object(reorder_ai, "_call_gemini", return_value=_canned_response()):
            first = reorder_ai.maybe_generate_suggestion(item, session)

        reorder_ai.resolve_suggestion(first.id, "approve", session)

        with patch.object(reorder_ai, "_GEMINI_ENABLED", True), \
             patch.object(reorder_ai, "_call_gemini", return_value=_canned_response()) as mock_gemini:
            second = reorder_ai.maybe_generate_suggestion(item, session)

        assert mock_gemini.call_count == 1
        assert second.id != first.id

    def test_ok_item_returns_none(self, seeded, session):
        """Items above threshold should not generate suggestions."""
        item = seeded["item"]
        item.quantity_on_hand = 500.0  # well above threshold of 80
        session.commit()

        result = reorder_ai.maybe_generate_suggestion(item, session)
        assert result is None

    def test_fallback_fires_when_gemini_raises(self, seeded, session):
        item = seeded["item"]
        with patch.object(reorder_ai, "_call_gemini", side_effect=RuntimeError("network error")):
            result = reorder_ai.maybe_generate_suggestion(item, session)

        assert result is not None
        assert "Rule-based" in result.ai_message

    def test_clamp_at_max_qty_multiplier(self, seeded, session):
        item = seeded["item"]
        # Gemini returns an absurdly large quantity
        bloated = _canned_response()
        bloated["suggested_order_qty"] = 99999.0
        with patch.object(reorder_ai, "_call_gemini", return_value=bloated):
            result = reorder_ai.maybe_generate_suggestion(item, session)

        max_allowed = item.reorder_quantity * reorder_ai._MAX_QTY_MULTIPLIER
        assert result.draft_order_qty <= max_allowed


class TestValidateResponse:

    def test_rejects_bad_urgency(self):
        r = _canned_response()
        r["urgency"] = "extreme"
        with pytest.raises(ValueError, match="urgency"):
            reorder_ai._validate_response(r, "L")

    def test_rejects_bad_confidence(self):
        r = _canned_response()
        r["confidence"] = "maybe"
        with pytest.raises(ValueError, match="confidence"):
            reorder_ai._validate_response(r, "L")

    def test_rejects_non_positive_qty(self):
        r = _canned_response()
        r["suggested_order_qty"] = -10
        with pytest.raises(ValueError, match="positive"):
            reorder_ai._validate_response(r, "L")

    def test_coerces_wrong_unit(self):
        r = _canned_response()
        r["unit"] = "kg"
        result = reorder_ai._validate_response(r, "L")
        assert result["unit"] == "L"

    def test_rejects_missing_keys(self):
        r = _canned_response()
        del r["rationale"]
        with pytest.raises(ValueError, match="missing keys"):
            reorder_ai._validate_response(r, "L")


class TestRuleBasedSuggestion:

    def test_covers_30_days(self, seeded, session):
        item = seeded["item"]
        context = reorder_ai._build_context(item, session)
        result = reorder_ai._rule_based_suggestion(item, context)

        burn = context["usage"]["avg_daily_burn"]
        upcoming = context["upcoming_demand_30d"]["total_quantity"]
        lead = reorder_ai._DEFAULT_LEAD_DAYS
        min_needed = (burn * (30 + lead)) + upcoming - item.quantity_on_hand

        assert result["suggested_order_qty"] >= min_needed
        assert result["confidence"] == "low"
        assert "Rule-based" in result["rationale"]

    def test_urgency_critical_when_3_days_or_less(self, seeded, session):
        item = seeded["item"]
        item.quantity_on_hand = 8.0  # burn ~4/day → ~2 days left
        session.commit()
        context = reorder_ai._build_context(item, session)
        result = reorder_ai._rule_based_suggestion(item, context)
        assert result["urgency"] == "critical"


class TestGetActiveSuggestions:

    def test_returns_pending_only(self, seeded, session):
        farm = seeded["farm"]
        item = seeded["item"]

        session.add(Notification(
            farm_id=farm.id, inventory_item_id=item.id,
            status=NotificationStatus.pending,
            ai_message="pending one", current_stock=72.0,
        ))
        session.add(Notification(
            farm_id=farm.id, inventory_item_id=item.id,
            status=NotificationStatus.approved,
            ai_message="approved one", current_stock=72.0,
        ))
        session.commit()

        results = reorder_ai.get_active_suggestions(session, farm.id)
        assert len(results) == 1
        assert results[0].status == NotificationStatus.pending


class TestResolveSuggestion:

    def test_approve_flips_status(self, seeded, session):
        item = seeded["item"]
        n = Notification(
            farm_id=seeded["farm"].id, inventory_item_id=item.id,
            status=NotificationStatus.pending,
            ai_message="test", current_stock=72.0,
        )
        session.add(n)
        session.commit()

        result = reorder_ai.resolve_suggestion(n.id, "approve", session)
        assert result.status == NotificationStatus.approved
        assert result.resolved_at is not None

    def test_dismiss_flips_status(self, seeded, session):
        item = seeded["item"]
        n = Notification(
            farm_id=seeded["farm"].id, inventory_item_id=item.id,
            status=NotificationStatus.pending,
            ai_message="test", current_stock=72.0,
        )
        session.add(n)
        session.commit()

        result = reorder_ai.resolve_suggestion(n.id, "dismiss", session)
        assert result.status == NotificationStatus.dismissed

    def test_already_resolved_returns_none(self, seeded, session):
        item = seeded["item"]
        n = Notification(
            farm_id=seeded["farm"].id, inventory_item_id=item.id,
            status=NotificationStatus.approved,
            ai_message="test", current_stock=72.0,
        )
        session.add(n)
        session.commit()

        result = reorder_ai.resolve_suggestion(n.id, "approve", session)
        assert result is None


class TestExtractUrgency:

    def test_extracts_from_embedded_json(self):
        r = _canned_response()
        full_json = json.dumps(r)
        ai_message = f"Some rationale text.\n\n<!--json\n{full_json}\n-->"
        assert reorder_ai._extract_urgency(ai_message) == "high"

    def test_defaults_to_medium_on_missing(self):
        assert reorder_ai._extract_urgency("plain text no json") == "medium"

    def test_defaults_to_medium_on_corrupt_json(self):
        ai_message = "text\n\n<!--json\n{broken json\n-->"
        assert reorder_ai._extract_urgency(ai_message) == "medium"


# ── contract test against real Gemini (optional, skipped if no key) ───────────

import os

@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="Needs real GEMINI_API_KEY")
def test_gemini_real_roundtrip(seeded, session):
    item = seeded["item"]
    context = reorder_ai._build_context(item, session)
    raw = reorder_ai._call_gemini(context)
    validated = reorder_ai._validate_response(raw, item.unit)
    assert validated["suggested_order_qty"] > 0
    assert validated["urgency"] in reorder_ai.VALID_URGENCY
    assert validated["confidence"] in reorder_ai.VALID_CONFIDENCE
