"""Fixed queue configuration for EventBus with topic exchange"""

from typing import Dict, List


class QueueConfig:
    """
    Fixed queue configuration with topic exchange.

    Event envelope format:
    {
        "event": "host_discovered",
        "target": "admin.example.com",
        "source": "dnsx",
        "confidence": 0.7,
        "program_id": 42
    }

    Architecture:
    - Topic exchange: "scan.events"
    - Routing key: "{queue_name}.{event}"
    - Priority: derived from confidence (0-10)
    - Queue binding: "{queue_name}.#"
    """

    EXCHANGE_NAME = "scan.events"
    EXCHANGE_TYPE = "topic"

    DISCOVERY_QUEUE = "discovery"
    ENUMERATION_QUEUE = "enumeration"
    VALIDATION_QUEUE = "validation"
    ANALYSIS_QUEUE = "analysis"

    EVENT_TO_QUEUE: Dict[str, str] = {
        "subfinder_scan_requested": DISCOVERY_QUEUE,
        "subdomain_discovered": DISCOVERY_QUEUE,
        "asnmap_scan_requested": DISCOVERY_QUEUE,
        "asn_discovered": DISCOVERY_QUEUE,
        "cidr_discovered": DISCOVERY_QUEUE,

        "mapcidr_scan_requested": ENUMERATION_QUEUE,
        "ips_expanded": ENUMERATION_QUEUE,
        "cidr_sliced": ENUMERATION_QUEUE,
        "ips_aggregated": ENUMERATION_QUEUE,
        "hakip2host_scan_requested": ENUMERATION_QUEUE,

        "dnsx_basic_scan_requested": VALIDATION_QUEUE,
        "dnsx_deep_scan_requested": VALIDATION_QUEUE,
        "dnsx_ptr_scan_requested": VALIDATION_QUEUE,
        "dnsx_filtered_hosts": VALIDATION_QUEUE,
        "dnsx_basic_results_batch": VALIDATION_QUEUE,
        "dnsx_deep_results_batch": VALIDATION_QUEUE,
        "dnsx_ptr_results_batch": VALIDATION_QUEUE,

        "httpx_scan_requested": ANALYSIS_QUEUE,
        "host_discovered": ANALYSIS_QUEUE,
        "scan_results_batch": ANALYSIS_QUEUE,
        "tlsx_scan_requested": ANALYSIS_QUEUE,
        "tlsx_results_batch": ANALYSIS_QUEUE,
        "cert_san_discovered": ANALYSIS_QUEUE,
        "gau_scan_requested": ANALYSIS_QUEUE,
        "gau_discovered": ANALYSIS_QUEUE,
        "katana_scan_requested": ANALYSIS_QUEUE,
        "katana_results_batch": ANALYSIS_QUEUE,
        "js_files_discovered": ANALYSIS_QUEUE,
        "linkfinder_scan_requested": ANALYSIS_QUEUE,
        "mantra_scan_requested": ANALYSIS_QUEUE,
        "mantra_results_batch": ANALYSIS_QUEUE,
        "ffuf_scan_requested": ANALYSIS_QUEUE,
        "ffuf_results_batch": ANALYSIS_QUEUE,
        "subjack_scan_requested": ANALYSIS_QUEUE,
        "subjack_results_batch": ANALYSIS_QUEUE,
        "naabu_scan_requested": ANALYSIS_QUEUE,
        "naabu_results_batch": ANALYSIS_QUEUE,
        "smap_scan_requested": ENUMERATION_QUEUE,
        "smap_results": ENUMERATION_QUEUE,
        "ports_discovered": ENUMERATION_QUEUE
    }

    @classmethod
    def get_routing_key(cls, event_name: str) -> str:
        """
        Get routing key for event.

        Args:
            event_name: Event name from event["event"]

        Returns:
            Routing key format: "{queue_name}.{event_name}"
            Example: "discovery.subdomain_discovered"
        """
        queue = cls.EVENT_TO_QUEUE.get(event_name, cls.ANALYSIS_QUEUE)
        return f"{queue}.{event_name}"

    @classmethod
    def get_queue_name(cls, event_name: str) -> str:
        """Get queue name for event"""
        return cls.EVENT_TO_QUEUE.get(event_name, cls.ANALYSIS_QUEUE)

    @classmethod
    def get_all_queues(cls) -> List[str]:
        """Get list of all queue names"""
        return [
            cls.DISCOVERY_QUEUE,
            cls.ENUMERATION_QUEUE,
            cls.VALIDATION_QUEUE,
            cls.ANALYSIS_QUEUE
        ]

    @classmethod
    def get_queue_binding(cls, queue_name: str) -> str:
        """
        Get topic binding pattern for queue.

        Example: "discovery.#" matches all events with routing key starting with "discovery."
        """
        return f"{queue_name}.#"

    @classmethod
    def confidence_to_priority(cls, confidence: float) -> int:
        """
        Convert confidence (0.0-1.0) to RabbitMQ priority (0-10).

        Higher confidence = higher priority
        Default confidence: 0.5 → priority 5
        """
        return min(10, max(0, int(confidence * 10)))
