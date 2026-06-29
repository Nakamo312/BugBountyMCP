from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.orm import clear_mappers, configure_mappers

from api.domain.models import (
    ASNModel,
    CIDRModel,
    JavaScriptReferenceModel,
    OrganizationModel,
    RawBodyModel,
)
from api.infrastructure.adapters.mappers import get_mapped_classes, start_mappers


def test_legacy_classical_mappers_configure_cleanly() -> None:
    clear_mappers()
    start_mappers()
    configure_mappers()

    mapped = get_mapped_classes()
    assert RawBodyModel in mapped
    assert JavaScriptReferenceModel in mapped
    assert OrganizationModel in mapped
    assert ASNModel in mapped
    assert CIDRModel in mapped

    clear_mappers()


def test_legacy_classical_mappers_do_not_include_orchestration_read_models() -> None:
    clear_mappers()
    start_mappers()
    configure_mappers()

    mapped_table_names = {inspect(model).local_table.name for model in get_mapped_classes()}
    forbidden_fragments = (
        "action_",
        "agent_",
        "allowed_action",
        "campaign",
        "event_store",
        "node_run",
        "projection",
        "proposal",
        "workflow",
    )

    assert not {
        table_name
        for table_name in mapped_table_names
        if any(fragment in table_name for fragment in forbidden_fragments)
    }

    clear_mappers()
