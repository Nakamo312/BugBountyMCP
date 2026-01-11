"""
Pipeline graph visualization script.

Automatically discovers nodes from DI and generates Mermaid diagram.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock, MagicMock
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from api.config import Settings
from dishka import make_async_container
from api.application.di import (
    CLIRunnerProvider,
    BatchProcessorProvider,
    IngestorProvider,
    PipelineProvider,
)


def create_mock_provider(provider_class):
    """Create mock version of provider that returns mocks for all dependencies."""

    class MockProvider(provider_class):
        def __getattribute__(self, name):
            if name.startswith('get_') or name.startswith('provide_'):
                return lambda *args, **kwargs: Mock()
            return super().__getattribute__(name)

    return MockProvider()


async def generate_mermaid_diagram():
    """Generate Mermaid diagram by inspecting DI container."""

    settings = Settings()
    settings.USE_NODE_PIPELINE = True

    # Mock all infrastructure dependencies
    mock_bus = Mock()
    mock_container = Mock()
    mock_session_factory = Mock()

    # Create providers with mocks
    cli_runner_provider = CLIRunnerProvider()
    batch_processor_provider = BatchProcessorProvider()
    ingestor_provider = IngestorProvider()
    pipeline_provider = PipelineProvider()

    # Mock all provider methods to return Mock objects
    original_methods = {}
    for provider in [cli_runner_provider, batch_processor_provider, ingestor_provider]:
        for attr_name in dir(provider):
            if attr_name.startswith('get_'):
                attr = getattr(provider, attr_name)
                if callable(attr):
                    original_methods[f"{provider.__class__.__name__}.{attr_name}"] = attr
                    setattr(provider, attr_name, lambda *a, **k: Mock())

    # Call pipeline provider's get_node_registry with mocked dependencies
    from api.infrastructure.runners.httpx_cli import HTTPXCliRunner
    from api.infrastructure.runners.katana_cli import KatanaCliRunner
    from api.application.services.batch_processor import HTTPXBatchProcessor, KatanaBatchProcessor
    from api.infrastructure.ingestors.httpx_ingestor import HTTPXResultIngestor
    from api.infrastructure.ingestors.katana_ingestor import KatanaResultIngestor

    # Create mocked dependencies
    mock_httpx_runner = Mock(spec=HTTPXCliRunner)
    mock_katana_runner = Mock(spec=KatanaCliRunner)
    mock_httpx_processor = Mock(spec=HTTPXBatchProcessor)
    mock_katana_processor = Mock(spec=KatanaBatchProcessor)
    mock_httpx_ingestor = Mock(spec=HTTPXResultIngestor)
    mock_katana_ingestor = Mock(spec=KatanaResultIngestor)

    # Call the real get_node_registry method from PipelineProvider
    # Now it only needs bus, settings, container (no dependency instances)
    registry = pipeline_provider.get_node_registry(
        bus=mock_bus,
        settings=settings,
        container=mock_container,
    )

    # Generate Mermaid
    mermaid_lines = ["graph LR"]
    mermaid_lines.append("    %% Nodes")

    # Add all nodes
    for node_id, node in registry._nodes.items():
        mermaid_lines.append(f"    {node_id}[{node_id.upper()}]")

    mermaid_lines.append("")
    mermaid_lines.append("    %% Event flows")

    # Add edges based on event_in -> node -> event_out
    for node_id, node in registry._nodes.items():
        # Input events
        for event_in in node.event_in:
            event_name = event_in.value
            mermaid_lines.append(f"    {event_name}({event_name}) --> {node_id}")

        # Output events
        for event_out in node.event_out:
            event_name = event_out.value
            mermaid_lines.append(f"    {node_id} --> {event_name}({event_name})")

    mermaid_lines.append("")
    mermaid_lines.append("    %% Styling")
    mermaid_lines.append("    classDef nodeStyle fill:#2374ab,stroke:#1a5276,color:#fff")
    mermaid_lines.append("    classDef eventStyle fill:#28b463,stroke:#1e8449,color:#fff")

    if registry._nodes:
        mermaid_lines.append("    class " + ",".join(registry._nodes.keys()) + " nodeStyle")

    # Collect all unique events
    all_events = set()
    for node in registry._nodes.values():
        all_events.update(e.value for e in node.event_in)
        all_events.update(e.value for e in node.event_out)

    if all_events:
        mermaid_lines.append("    class " + ",".join(all_events) + " eventStyle")

    mermaid = "\n".join(mermaid_lines)

    print("\n" + "="*80)
    print("PIPELINE GRAPH (Mermaid)")
    print("="*80)
    print(mermaid)
    print("="*80)
    print(f"\nTotal nodes: {len(registry._nodes)}")
    print(f"Total events: {len(all_events)}")
    print("\nCopy the Mermaid markup above to https://mermaid.live/ to visualize")
    print("="*80 + "\n")

    # Save to file
    output_file = Path(__file__).parent.parent / "pipeline_graph.mmd"
    output_file.write_text(mermaid, encoding="utf-8")
    print(f"Saved to: {output_file}")


if __name__ == "__main__":
    asyncio.run(generate_mermaid_diagram())
