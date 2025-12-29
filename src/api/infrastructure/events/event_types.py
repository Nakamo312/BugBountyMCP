"""Event type constants for EventBus messaging"""
from enum import Enum


class EventType(str, Enum):
    """Application event type constants for EventBus messaging"""

    SERVICE_EVENTS = "service_events"
    SUBDOMAIN_DISCOVERED = "subdomain_discovered"
    SCAN_RESULTS_BATCH = "scan_results_batch"
    GAU_DISCOVERED = "gau_discovered"
    KATANA_RESULTS_BATCH = "katana_results_batch"
    HOST_DISCOVERED = "host_discovered"
