"""Helpers for bounded read-only SQL view queries.

The dashboard/API analysis endpoints read historical database views.  This
module keeps those reads inside a small allow-listed SQLAlchemy Core boundary so
service methods do not assemble SQL strings directly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping

from sqlalchemy import bindparam, column, func, literal_column, select, table
from sqlalchemy.sql import Select

_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class ReadOnlyView:
    """A database view that can be queried by API read services."""

    name: str
    allowed_filters: frozenset[str]

    def __post_init__(self) -> None:
        _validate_identifier(self.name, field_name="view name")
        if not self.allowed_filters:
            raise ValueError("allowed_filters must not be empty")
        for filter_name in self.allowed_filters:
            _validate_identifier(filter_name, field_name="filter name")

    @property
    def from_clause(self):  # type: ignore[no-untyped-def]
        return table(self.name)


def view_count_query(view: ReadOnlyView, filters: Mapping[str, object]) -> Select:
    """Build a SELECT count(*) query for an allow-listed read-only view."""

    predicates = _filter_predicates(view, filters.keys())
    return select(func.count()).select_from(view.from_clause).where(*predicates)


def view_data_query(view: ReadOnlyView, filters: Mapping[str, object]) -> Select:
    """Build a paginated SELECT * query for an allow-listed read-only view."""

    predicates = _filter_predicates(view, filters.keys())
    return (
        select(literal_column("*"))
        .select_from(view.from_clause)
        .where(*predicates)
        .limit(bindparam("limit"))
        .offset(bindparam("offset"))
    )


def _filter_predicates(view: ReadOnlyView, filter_names: Iterable[str]):
    predicates = []
    for name in filter_names:
        _validate_filter(view, name)
        predicates.append(column(name) == bindparam(name))
    return predicates


def _validate_filter(view: ReadOnlyView, name: str) -> None:
    _validate_identifier(name, field_name="filter name")
    if name not in view.allowed_filters:
        allowed = ", ".join(sorted(view.allowed_filters))
        raise ValueError(f"filter {name!r} is not allowed for view {view.name!r}; allowed: {allowed}")


def _validate_identifier(value: str, *, field_name: str) -> None:
    if not _SAFE_IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid {field_name}: {value!r}")
