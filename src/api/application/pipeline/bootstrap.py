"""Pipeline bootstrap - assembles node registry"""

import logging

from .base import PipelineContext
from .registry import NodeRegistry
from .scope_policy import ScopePolicy
from .nodes import (
    TLSxCertNode,
    NaabuPortsNode,
    PortsDiscoveredNode,
    SubdomainDiscoveredNode,
    DNSxBasicResultsNode,
    DNSxFilteredHostsNode,
    HTTPXResultsNode,
    HostDiscoveredNode,
    GAUDiscoveredNode,
    CertSANDiscoveredNode,
    KatanaResultsNode,
    MantraResultsNode,
    FFUFResultsNode,
    DNSxDeepResultsNode,
    DNSxPTRResultsNode,
    ASNMapResultsNode,
    JSFilesDiscoveredNode,
    CNAMEDiscoveredNode,
    SubjackResultsNode,
    CIDRDiscoveredNode,
    IPsExpandedNode,
    ASNDiscoveredNode,
)

from api.infrastructure.events.event_bus import EventBus
from api.config import Settings
from dishka import AsyncContainer


logger = logging.getLogger(__name__)


def build_node_registry(
    bus: EventBus,
    container: AsyncContainer,
    settings: Settings,
) -> NodeRegistry:
    """
    Build and populate node registry with all pipeline nodes.

    This is the central place where pipeline graph is assembled.
    Add new nodes here to extend the pipeline.

    Args:
        bus: EventBus for event publishing
        container: DI container for service resolution
        settings: Application settings

    Returns:
        NodeRegistry with all nodes registered
    """
    scope_policy = ScopePolicy(container)
    ctx = PipelineContext(bus, container, settings, scope_policy)

    registry = NodeRegistry()

    # DNS Track
    registry.register(SubdomainDiscoveredNode(ctx))
    registry.register(DNSxBasicResultsNode(ctx))
    registry.register(DNSxFilteredHostsNode(ctx))
    registry.register(HTTPXResultsNode(ctx))
    registry.register(HostDiscoveredNode(ctx))
    registry.register(GAUDiscoveredNode(ctx))
    registry.register(KatanaResultsNode(ctx))
    registry.register(MantraResultsNode(ctx))
    registry.register(FFUFResultsNode(ctx))
    registry.register(DNSxDeepResultsNode(ctx))
    registry.register(DNSxPTRResultsNode(ctx))
    registry.register(JSFilesDiscoveredNode(ctx))
    registry.register(CNAMEDiscoveredNode(ctx))
    registry.register(SubjackResultsNode(ctx))

    # ASN Track
    registry.register(ASNMapResultsNode(ctx))
    registry.register(ASNDiscoveredNode(ctx))
    registry.register(CIDRDiscoveredNode(ctx))
    registry.register(IPsExpandedNode(ctx))
    registry.register(NaabuPortsNode(ctx))
    registry.register(PortsDiscoveredNode(ctx))
    registry.register(TLSxCertNode(ctx))
    registry.register(CertSANDiscoveredNode(ctx))

    logger.info(
        f"Pipeline bootstrap complete: {len(registry.list_nodes())} nodes registered"
    )

    event_graph = registry.get_event_graph()
    for event_in, events_out in event_graph.items():
        logger.debug(f"Pipeline: {event_in} -> {events_out}")

    # Print visualization summary if debug logging
    if logger.isEnabledFor(logging.DEBUG):
        from .visualizer import print_pipeline_summary
        print_pipeline_summary(registry)

    return registry
