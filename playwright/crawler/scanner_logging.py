"""Logging setup for the Playwright crawler."""
from __future__ import annotations

import logging


class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    RESET = "\033[0m"


class ColorFormatter(logging.Formatter):
    def format(self, record):
        timestamp = self.formatTime(record, "%H:%M:%S")
        level = record.levelname
        if level == "INFO":
            level_color = Colors.GREEN
        elif level == "WARNING":
            level_color = Colors.YELLOW
        elif level == "ERROR":
            level_color = Colors.RED
        else:
            level_color = Colors.RESET
        return f"[{timestamp}] [{level_color}{level}{Colors.RESET}] {record.getMessage()}"


logger = logging.getLogger("playwright_scanner")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(ColorFormatter())
    logger.addHandler(handler)
