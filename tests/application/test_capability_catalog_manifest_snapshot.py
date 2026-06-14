from copy import deepcopy

from api.application.capability_catalog import (
    CATALOG_SCHEMA_VERSION,
    build_tool_catalog_snapshot,
    load_tool_catalog_snapshot,
)
from api.application.pipeline.yaml_config import DEFAULT_PIPELINE_CONFIG_PATH, load_pipeline_config


def test_catalog_snapshot_is_manifest_first_and_deterministic() -> None:
    config = load_pipeline_config(DEFAULT_PIPELINE_CONFIG_PATH)

    first = build_tool_catalog_snapshot(config)
    second = build_tool_catalog_snapshot(config)

    assert first.schema_version == CATALOG_SCHEMA_VERSION
    assert first.catalog_hash == second.catalog_hash
    assert first.source_hash == second.source_hash
    assert len(first.entries) == sum(
        len(capability.profiles) for capability in config.capabilities.values()
    )


def test_catalog_hash_changes_when_manifest_options_change() -> None:
    config = load_pipeline_config(DEFAULT_PIPELINE_CONFIG_PATH)
    original = build_tool_catalog_snapshot(config)
    mutated_payload = deepcopy(config.model_dump(mode="json"))

    capability_id = next(iter(mutated_payload["capabilities"]))
    profile_id = next(iter(mutated_payload["capabilities"][capability_id]["profiles"]))
    mutated_payload["capabilities"][capability_id]["profiles"][profile_id][
        "allowed_options"
    ].append("__test_option__")

    mutated_config = config.__class__.model_validate(mutated_payload)
    mutated = build_tool_catalog_snapshot(mutated_config)

    assert mutated.catalog_hash != original.catalog_hash


def test_catalog_entry_validates_profile_options() -> None:
    snapshot = load_tool_catalog_snapshot(DEFAULT_PIPELINE_CONFIG_PATH)
    entry = next(item for item in snapshot.entries if item.allowed_options)
    allowed_option = entry.allowed_options[0]

    accepted, unknown = snapshot.validate_options(
        capability_id=entry.capability_id,
        profile_id=entry.profile_id,
        options={allowed_option: True},
    )
    rejected, rejected_unknown = snapshot.validate_options(
        capability_id=entry.capability_id,
        profile_id=entry.profile_id,
        options={"definitely_not_allowed": True},
    )

    assert accepted is True
    assert unknown == ()
    assert rejected is False
    assert rejected_unknown == ("definitely_not_allowed",)


def test_catalog_uses_profile_entries_not_second_source_of_truth() -> None:
    snapshot = load_tool_catalog_snapshot(DEFAULT_PIPELINE_CONFIG_PATH)

    assert all(entry.manifest_fragment for entry in snapshot.entries)
    assert all(entry.capability_id for entry in snapshot.entries)
    assert all(entry.profile_id for entry in snapshot.entries)
