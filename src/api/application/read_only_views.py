"""Application-level contracts for bounded read-only database views."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class ReadOnlyView:
    """Allow-listed database view descriptor consumed by read services."""

    name: str
    allowed_filters: frozenset[str]

    def __post_init__(self) -> None:
        _validate_identifier(self.name, field_name="view name")
        if not self.allowed_filters:
            raise ValueError("allowed_filters must not be empty")
        for filter_name in self.allowed_filters:
            _validate_identifier(filter_name, field_name="filter name")

    def validate_filter(self, name: str) -> None:
        _validate_identifier(name, field_name="filter name")
        if name not in self.allowed_filters:
            allowed = ", ".join(sorted(self.allowed_filters))
            raise ValueError(
                f"filter {name!r} is not allowed for view {self.name!r}; allowed: {allowed}"
            )

    def validate_filters(self, filters: Mapping[str, object]) -> None:
        for name in filters:
            self.validate_filter(name)


@dataclass(frozen=True)
class ReadOnlyViewPage:
    rows: list[dict[str, Any]]
    total: int | None = None


class ReadOnlyViewReader(Protocol):
    async def list_view_rows(
        self,
        view: ReadOnlyView,
        filters: Mapping[str, object],
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        ...

    async def page_view_rows(
        self,
        view: ReadOnlyView,
        filters: Mapping[str, object],
        *,
        limit: int,
        offset: int,
    ) -> ReadOnlyViewPage:
        ...


def _validate_identifier(value: str, *, field_name: str) -> None:
    if not _SAFE_IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid {field_name}: {value!r}")
