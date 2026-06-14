from __future__ import annotations

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_startup_activates_manifest_before_registry_start() -> None:
    source = _read("src/api/presentation/rest/app.py")

    activate_pos = source.index("await activator.activate(manifest)")
    register_pos = source.index("register_manifest_nodes(")
    start_pos = source.index("await registry.start()")

    assert "load_tool_catalog_snapshot(settings.PIPELINE_CONFIG_PATH)" in source
    assert "ManifestActivator" in source
    assert activate_pos < register_pos < start_pos


def test_pipeline_provider_does_not_read_yaml_for_registry() -> None:
    source = _read("src/api/application/di.py")
    provider_block = source[source.index("class PipelineProvider"):]

    assert "register_yaml_nodes" not in provider_block
    assert "PIPELINE_CONFIG_PATH" not in provider_block
    assert "return NodeRegistry(bus, settings, container)" in provider_block


def test_builder_can_register_nodes_from_manifest_json() -> None:
    source = _read("src/api/application/pipeline/builder.py")

    assert "def register_manifest_nodes" in source
    assert "PipelineConfig.model_validate(manifest_json)" in source
    assert "def register_config_nodes" in source


def test_runtime_manifest_activator_owns_postgres_activation() -> None:
    source = _read("src/api/infrastructure/runtime_manifest.py")

    assert "class ManifestActivator" in source
    assert "async def activate" in source
    assert "async def active_manifest" in source
    assert "tool_catalog_snapshots" in source
    assert "tool_catalog_entries" in source
