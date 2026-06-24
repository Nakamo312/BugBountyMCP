"""Strict tool option schemas and per-action execution budget resolution."""
from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


OptionType = Literal["integer", "number", "boolean", "string"]

FORBIDDEN_OPTION_KEYS = {
    "cmd",
    "command",
    "shell",
    "exec",
    "raw_command",
    "nmap_cli",
}


class ActionInputValidationError(ValueError):
    """Raised when action options or requested limits violate the profile."""


class ToolOptionSpec(BaseModel):
    """Strict declarative contract for one profile option."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    type: OptionType
    default: Any = None
    required: bool = False
    minimum: float | None = None
    maximum: float | None = None
    enum: tuple[Any, ...] = ()

    @field_validator("enum", mode="before")
    @classmethod
    def normalize_enum(cls, value: Any) -> tuple[Any, ...]:
        if value is None:
            return ()
        if isinstance(value, (list, tuple)):
            return tuple(value)
        raise ValueError("enum must be a list or tuple")

    @model_validator(mode="after")
    def validate_contract(self) -> "ToolOptionSpec":
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("minimum cannot exceed maximum")
        if self.type not in {"integer", "number"} and (
            self.minimum is not None or self.maximum is not None
        ):
            raise ValueError("minimum/maximum require a numeric option")
        if self.default is not None:
            try:
                self.validate_value("default", self.default)
            except ActionInputValidationError as exc:
                raise ValueError(str(exc)) from exc
        for value in self.enum:
            try:
                self.validate_value("enum", value)
            except ActionInputValidationError as exc:
                raise ValueError(str(exc)) from exc
        return self

    def validate_value(self, name: str, value: Any) -> Any:
        checks = {
            "integer": lambda item: isinstance(item, int)
            and not isinstance(item, bool),
            "number": lambda item: isinstance(item, (int, float))
            and not isinstance(item, bool),
            "boolean": lambda item: isinstance(item, bool),
            "string": lambda item: isinstance(item, str),
        }
        if not checks[self.type](value):
            raise ActionInputValidationError(f"{name} must be {self.type}")
        if self.minimum is not None and value < self.minimum:
            raise ActionInputValidationError(f"{name} is below minimum")
        if self.maximum is not None and value > self.maximum:
            raise ActionInputValidationError(f"{name} exceeds maximum")
        if self.enum and value not in self.enum:
            raise ActionInputValidationError(f"{name} is not an allowed value")
        return value


class ExecutionBudget(BaseModel):
    """Resolved hard ceilings for one action and its tool invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    max_duration_seconds: float | None = Field(default=None, gt=0)
    max_targets: int | None = Field(default=None, gt=0)
    rate_per_second: float | None = Field(default=None, gt=0)
    concurrency: int | None = Field(default=None, gt=0)


class ExecutionBudgetRequest(ExecutionBudget):
    """Optional caller request that may only tighten effective ceilings."""


DEFAULT_SYSTEM_EXECUTION_BUDGET = ExecutionBudget(
    max_duration_seconds=1800,
    max_targets=1000,
    rate_per_second=1000,
    concurrency=5,
)


def system_execution_budget(settings: Any) -> ExecutionBudget:
    """Build system ceilings from application settings."""
    return ExecutionBudget(
        max_duration_seconds=settings.MAX_ACTION_DURATION_SECONDS,
        max_targets=settings.MAX_ACTION_TARGETS,
        rate_per_second=settings.MAX_ACTION_RATE_PER_SECOND,
        concurrency=settings.ORCHESTRATOR_MAX_CONCURRENT,
    )


def normalize_options(
    schema: Mapping[str, ToolOptionSpec],
    options: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply defaults and validate caller options without type coercion."""
    forbidden = set(schema) & FORBIDDEN_OPTION_KEYS
    if forbidden:
        raise ActionInputValidationError(
            f"Forbidden command-like options: {sorted(forbidden)}"
        )

    unknown = set(options) - set(schema)
    if unknown:
        raise ActionInputValidationError(f"Unsupported options: {sorted(unknown)}")

    normalized: dict[str, Any] = {}
    for name, spec in schema.items():
        if name in options:
            normalized[name] = spec.validate_value(name, options[name])
            continue
        if spec.default is not None:
            normalized[name] = spec.default
            continue
        if spec.required:
            raise ActionInputValidationError(f"{name} is required")
    return normalized


def resolve_execution_budget(
    *,
    system: ExecutionBudget,
    profile: ExecutionBudget,
    requested: ExecutionBudgetRequest | None,
) -> ExecutionBudget:
    """Resolve the strict minimum of system, profile, and caller limits."""
    values: dict[str, int | float | None] = {}
    for field_name in ExecutionBudget.model_fields:
        system_value = getattr(system, field_name)
        profile_value = getattr(profile, field_name)
        requested_value = getattr(requested, field_name) if requested else None

        if (
            system_value is not None
            and profile_value is not None
            and profile_value > system_value
        ):
            raise ActionInputValidationError(
                f"profile {field_name} exceeds system ceiling"
            )

        ceilings = [
            value
            for value in (system_value, profile_value)
            if value is not None
        ]
        ceiling = min(ceilings) if ceilings else None
        if requested_value is not None:
            if ceiling is not None and requested_value > ceiling:
                raise ActionInputValidationError(
                    f"{field_name} exceeds effective ceiling {ceiling}"
                )
            values[field_name] = requested_value
        else:
            values[field_name] = ceiling

    return ExecutionBudget(**values)
