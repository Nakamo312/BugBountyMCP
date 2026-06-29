from __future__ import annotations

from pathlib import Path

from api.config import Settings
from api.infrastructure.adapters.orm import campaigns


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "alembic"
    / "versions"
    / "g3h4i5j6k7l8_add_campaign_expansion_budgets.py"
)


def test_campaigns_table_has_bounded_expansion_budget_fields() -> None:
    assert {
        "max_runs",
        "max_targets",
        "runs_consumed",
        "targets_consumed",
        "token_capacity",
        "tokens_available",
        "token_refill_per_second",
        "tokens_refilled_at",
    }.issubset(campaigns.c.keys())


def test_campaign_budget_system_defaults_are_positive() -> None:
    settings = Settings()

    assert settings.CAMPAIGN_MAX_RUNS > 0
    assert settings.CAMPAIGN_MAX_TARGETS > 0
    assert settings.CAMPAIGN_TOKEN_CAPACITY > 0
    assert settings.CAMPAIGN_TOKEN_REFILL_PER_SECOND > 0


def test_campaign_budget_migration_extends_existing_campaigns_table() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "down_revision = \"f2g3h4i5j6k7\"" in source
    assert "op.add_column(" in source
    assert '"campaigns",' in source
    assert '"tokens_refilled_at"' in source
    assert "ck_campaigns_runs_consumed_nonnegative" in source
    assert "ck_campaigns_targets_consumed_nonnegative" in source
    assert "ck_campaigns_tokens_available_nonnegative" in source
