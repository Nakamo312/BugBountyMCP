from __future__ import annotations

from api.application.pipeline.yaml_config import load_pipeline_config
from api.config import Settings


def test_first_runner_profiles_have_typed_options_and_budgets() -> None:
    config = load_pipeline_config()

    for capability_id in ("httpx", "katana", "ffuf", "naabu"):
        capability = config.capabilities[capability_id]
        for profile in capability.profiles.values():
            assert profile.options
            assert profile.allowed_options == []
            assert profile.budgets.max_duration_seconds
            assert profile.budgets.max_targets
            assert profile.budgets.rate_per_second
            assert profile.budgets.concurrency


def test_naabu_profiles_define_distinct_safe_modes() -> None:
    profiles = load_pipeline_config().capabilities["naabu"].profiles

    assert profiles["passive-ports"].options["scan_mode"].default == "passive"
    assert profiles["connect-top-100"].options["scan_mode"].default == "active"
    assert profiles["connect-top-100"].options["top_ports"].default == "100"


def test_system_execution_ceilings_are_positive() -> None:
    settings = Settings()

    assert settings.MAX_ACTION_DURATION_SECONDS > 0
    assert settings.MAX_ACTION_TARGETS > 0
    assert settings.MAX_ACTION_RATE_PER_SECOND > 0
    assert settings.ORCHESTRATOR_MAX_CONCURRENT > 0
