"""Pipeline visualization utilities - Node-centric view"""

from typing import Dict, List, Set
import logging

from .registry import NodeRegistry
from api.infrastructure.events.event_types import EventType

logger = logging.getLogger(__name__)


class PipelineVisualizer:
    """
    Node-centric pipeline visualizer.
    Nodes = PipelineNode
    Edges = EventType emitted from one node to another.

    Usage:
        visualizer = PipelineVisualizer(registry)
        print(visualizer.to_mermaid())
        print(visualizer.to_graphviz())
    """

    def __init__(self, registry: NodeRegistry):
        self.registry = registry

    def to_mermaid(self) -> str:
        """
        Mermaid flowchart: nodes as boxes, events as edge labels.
        Can be rendered at https://mermaid.live
        """
        lines = ["```mermaid", "flowchart TD", ""]

        # Создать все ноды
        for node in self.registry.list_nodes():
            node_name = node.__class__.__name__
            lines.append(f"{node_name}[{node_name}]")
        lines.append("")

        # Стрелки Node -> Node с событиями как подписи
        for node in self.registry.list_nodes():
            src_name = node.__class__.__name__
            for out_event in node.event_out:
                dst_node = self.registry.get(out_event)
                if dst_node:
                    dst_name = dst_node.__class__.__name__
                    lines.append(f"{src_name} --|{out_event.name}|--> {dst_name}")
        lines.append("```")
        return "\n".join(lines)

    def to_graphviz(self) -> str:
        """
        Graphviz DOT: nodes as boxes, edges labeled by EventType.
        Can render with: dot -Tpng pipeline.dot -o pipeline.png
        """
        lines = ["digraph Pipeline {", "    rankdir=LR;", "    node [shape=box, style=rounded];", ""]

        # Все ноды
        for node in self.registry.list_nodes():
            node_id = node.__class__.__name__
            lines.append(f'    {node_id} [label="{node_id}", fillcolor=lightyellow, style=filled];')
        lines.append("")

        # Стрелки Node -> Node с событиями
        for node in self.registry.list_nodes():
            src_id = node.__class__.__name__
            for out_event in node.event_out:
                dst_node = self.registry.get(out_event)
                if dst_node:
                    dst_id = dst_node.__class__.__name__
                    lines.append(f'    {src_id} -> {dst_id} [label="{out_event.name}"];')
        lines.append("}")
        return "\n".join(lines)

    def get_pipeline_stats(self) -> Dict:
        """
        Статистика по нодам и связям.
        """
        all_nodes = self.registry.list_nodes()
        total_nodes = len(all_nodes)
        total_edges = sum(len(node.event_out) for node in all_nodes)

        # Entry points (нет входящих EventType)
        all_outputs = set()
        for node in all_nodes:
            all_outputs.update(node.event_out)

        entry_points = [node.__class__.__name__ for node in all_nodes if node.event_in not in all_outputs]
        terminal_nodes = [node.__class__.__name__ for node in all_nodes if not node.event_out]

        return {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "entry_points": entry_points,
            "terminal_nodes": terminal_nodes,
        }

    def print_summary(self):
        stats = self.get_pipeline_stats()
        print("\n" + "="*60)
        print("PIPELINE NODE-CENTRIC SUMMARY")
        print("="*60 + "\n")
        print(f"📊 Total nodes: {stats['total_nodes']}")
        print(f"📊 Total edges: {stats['total_edges']}")
        print(f"🚀 Entry points (no incoming edges): {stats['entry_points']}")
        print(f"🏁 Terminal nodes (no outgoing edges): {stats['terminal_nodes']}")
        print("="*60 + "\n")
        print("Mermaid graph:\n")
        print(self.to_mermaid())
        print("\nGraphviz DOT:\n")
        print(self.to_graphviz())
        print("\n" + "="*60)
