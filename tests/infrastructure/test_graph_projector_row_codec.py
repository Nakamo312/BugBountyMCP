from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path("services/graph-projector").resolve()))

from graph_projector.row_codec import cursor_for


class ContextManagedCursor:
    def __init__(self) -> None:
        self.entered = 0
        self.exited = 0

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.exited += 1


class Connection:
    def __init__(self) -> None:
        self.cursor_obj = ContextManagedCursor()

    def cursor(self) -> ContextManagedCursor:
        return self.cursor_obj


def test_cursor_for_does_not_enter_context_managed_cursor_without_exit() -> None:
    connection = Connection()

    cursor = cursor_for(connection)

    assert cursor is connection.cursor_obj
    assert connection.cursor_obj.entered == 0
    assert connection.cursor_obj.exited == 0
