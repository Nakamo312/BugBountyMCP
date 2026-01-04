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
    JS_FILES_DISCOVERED = "js_files_discovered"
    MANTRA_RESULTS_BATCH = "mantra_results_batch"
    FFUF_RESULTS_BATCH = "ffuf_results_batch"
    DNSX_BASIC_RESULTS_BATCH = "dnsx_basic_results_batch"
    DNSX_DEEP_RESULTS_BATCH = "dnsx_deep_results_batch"
