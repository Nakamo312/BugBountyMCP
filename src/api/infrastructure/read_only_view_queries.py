"""SQLAlchemy Core query builders for allow-listed read-only views."""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from sqlalchemy import bindparam, column, func, literal_column, select, table
from sqlalchemy.sql import Select

from api.application.read_only_views import ReadOnlyView


def view_count_query(view: ReadOnlyView, filters: Mapping[str, object]) -> Select:
    """Build a SELECT count(*) query for an allow-listed read-only view."""

    predicates = _filter_predicates(view, filters.keys())
    return select(func.count()).select_from(table(view.name)).where(*predicates)


def view_data_query(view: ReadOnlyView, filters: Mapping[str, object]) -> Select:
    """Build a paginated SELECT * query for an allow-listed read-only view."""

    predicates = _filter_predicates(view, filters.keys())
    return (
        select(literal_column("*"))
        .select_from(table(view.name))
        .where(*predicates)
        .limit(bindparam("limit"))
        .offset(bindparam("offset"))
    )


def _filter_predicates(view: ReadOnlyView, filter_names: Iterable[str]):
    predicates = []
    for name in filter_names:
        view.validate_filter(name)
        predicates.append(column(name) == bindparam(name))
    return predicates
