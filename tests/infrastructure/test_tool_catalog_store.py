from __future__ import annotations

from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")

from api.infrastructure.tool_catalog.store import SqlActionCatalogStore


def test_catalog_store_rebuilds_typed_profile_contract_from_manifest_fragment() -> None:
    row = {
        "id": uuid4(),
        "snapshot_id": uuid4(),
        "capability_id": "katana",
        "profile_id": "safe-crawl",
        "capability_label": "Katana",
        "profile_label": "Safe crawl",
        "request_event": "katana_scan_requested",
        "queue": "analysis",
        "default_profile": "safe-crawl",
        "mode": "routed",
        "scope_policy": "confidence",
        "safety_class": "safe_active",
        "allowed_options": ["depth", "timeout"],
        "requires_approval": False,
        "frontend": {},
        "manifest_fragment": {
            "profile": {
                "label": "Safe crawl",
                "safety_level": "safe_active",
                "options": {
                    "depth": {
                        "type": "integer",
                        "default": 2,
                        "minimum": 1,
                        "maximum": 5,
                    },
                    "timeout": {
                        "type": "integer",
                        "default": 60,
                        "minimum": 1,
                        "maximum": 120,
                    },
                },
                "budgets": {
                    "max_duration_seconds": 120,
                    "max_targets": 20,
                    "rate_per_second": 10,
                    "concurrency": 2,
                },
            }
        },
    }

    detail = SqlActionCatalogStore._detail(row)

    assert detail.option_schema["depth"].default == 2
    assert detail.execution_budget.max_targets == 20
