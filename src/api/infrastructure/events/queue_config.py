"""YAML-backed queue configuration for EventBus with topic exchange."""

import os
from typing import Dict, List

from api.application.pipeline.yaml_config import DEFAULT_PIPELINE_CONFIG_PATH, load_pipeline_config


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

    _CONFIGURED_QUEUES: Dict[str, str] | None = None

    @classmethod
    def _config_event_to_queue(cls) -> Dict[str, str]:
        if cls._CONFIGURED_QUEUES is None:
            config_path = os.environ.get("PIPELINE_CONFIG_PATH") or DEFAULT_PIPELINE_CONFIG_PATH
            config = load_pipeline_config(config_path)
            configured = {
                capability.request_event: capability.queue
                for capability in config.capabilities.values()
            }
            for event_name, event_config in config.events.items():
                configured[event_name] = event_config.queue
            cls._CONFIGURED_QUEUES = configured
        return cls._CONFIGURED_QUEUES

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
        queue = cls.get_queue_name(event_name)
        return f"{queue}.{event_name}"

    @classmethod
    def get_queue_name(cls, event_name: str) -> str:
        """Get queue name for event"""
        return cls._config_event_to_queue().get(event_name, cls.ANALYSIS_QUEUE)

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
