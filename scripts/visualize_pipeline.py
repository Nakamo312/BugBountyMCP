#!/usr/bin/env python3
"""
Pipeline visualization script.

Usage:
    python scripts/visualize_pipeline.py --format mermaid
    python scripts/visualize_pipeline.py --format graphviz > pipeline.dot
    python scripts/visualize_pipeline.py --format text
    python scripts/visualize_pipeline.py --stats
"""

import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from api.application.pipeline.bootstrap import build_node_registry
from api.application.pipeline.visualizer import PipelineVisualizer
from api.infrastructure.events.event_bus import EventBus
from api.config import Settings
from dishka import make_async_container
from unittest.mock import AsyncMock


def create_mock_registry():
    """Create registry with mocked dependencies for visualization"""
    # Mock EventBus and container
    mock_bus = AsyncMock(spec=EventBus)
    mock_container = AsyncMock()

    # Real settings
    settings = Settings()

    # Build registry
    registry = build_node_registry(mock_bus, mock_container, settings)

    return registry


def main():
    parser = argparse.ArgumentParser(description="Visualize pipeline graph")
    parser.add_argument(
        "--format",
        choices=["mermaid", "graphviz", "text"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show pipeline statistics",
    )
    parser.add_argument(
        "--find-path",
        nargs=2,
        metavar=("START", "END"),
        help="Find paths from START event to END event",
    )

    args = parser.parse_args()

    # Create registry
    registry = create_mock_registry()
    visualizer = PipelineVisualizer(registry)

    if args.stats:
        stats = visualizer.get_pipeline_stats()
        print("\n📊 Pipeline Statistics:")
        print(f"   Total Nodes: {stats['total_nodes']}")
        print(f"   Total Edges: {stats['total_edges']}")
        print(f"   DNS Track: {stats['dns_track_nodes']} nodes")
        print(f"   ASN Track: {stats['asn_track_nodes']} nodes")
        print(f"   Shared: {stats['shared_nodes']} nodes")
        print(f"\n🚀 Entry Points: {', '.join(stats['entry_points'])}")
        print(f"🏁 Terminal Nodes: {', '.join(stats['terminal_nodes'])}\n")

        tracks = visualizer.get_tracks()
        print("🔵 DNS Track:")
        for event in tracks['dns_track']:
            print(f"   - {event}")
        print("\n🟢 ASN Track:")
        for event in tracks['asn_track']:
            print(f"   - {event}")

    elif args.find_path:
        from api.infrastructure.events.event_types import EventType

        start_str, end_str = args.find_path
        try:
            start = EventType(start_str)
            end = EventType(end_str)
            paths = visualizer.find_path(start, end)

            if paths:
                print(f"\n🔍 Found {len(paths)} path(s) from {start_str} to {end_str}:\n")
                for i, path in enumerate(paths, 1):
                    print(f"Path {i}: {' → '.join(path)}")
            else:
                print(f"\n❌ No path found from {start_str} to {end_str}")
        except ValueError as e:
            print(f"❌ Error: Invalid event type - {e}")
            print(f"Available events: {[e.value for e in EventType]}")

    elif args.format == "mermaid":
        print(visualizer.to_mermaid())

    elif args.format == "graphviz":
        print(visualizer.to_graphviz())

    else:  # text
        print(visualizer.to_text())


if __name__ == "__main__":
    main()
