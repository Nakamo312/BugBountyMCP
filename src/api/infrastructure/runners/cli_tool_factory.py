from __future__ import annotations

import logging
from typing import Any

from api.config import Settings
from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.runners.cli_specs.registry import CLI_TOOL_SPECS
from api.infrastructure.runners.cli_tool import GenericCliToolRunner


class CliToolRunnerFactory:
    def __init__(
        self,
        settings: Settings,
        *,
        executor_cls: type[CommandExecutor] = CommandExecutor,
    ) -> None:
        self.settings = settings
        self.executor_cls = executor_cls

    def create(self, tool_name: str, **options: Any) -> GenericCliToolRunner:
        try:
            spec = CLI_TOOL_SPECS[tool_name]
        except KeyError as exc:
            known = ", ".join(sorted(CLI_TOOL_SPECS))
            raise ValueError(f"Unknown CLI tool spec '{tool_name}'. Known values: {known}") from exc

        static_options = dict(
            spec.static_options_from_settings(self.settings)
            if spec.static_options_from_settings is not None
            else {}
        )
        static_options.update(options)
        return GenericCliToolRunner(
            spec,
            executable=self.settings.get_tool_path(spec.executable),
            timeout=spec.timeout,
            logger=logging.getLogger(f"api.infrastructure.runners.{tool_name}"),
            executor_cls=self.executor_cls,
            **static_options,
        )
