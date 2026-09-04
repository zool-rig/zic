import sqlite3

from typing import TypeAlias, Callable, Any


RowFactoryOptions: TypeAlias = (
    type[sqlite3.Row] | Callable[[sqlite3.Cursor, tuple[Any, ...]], object] | None
)


class RowFactory:
    def __init__(self, conn: sqlite3.Connection, factory: RowFactoryOptions) -> None:
        self.conn = conn
        self.target_factory: RowFactoryOptions = factory
        self.current_factory = conn.row_factory

    def __enter__(self):
        self.conn.row_factory = self.target_factory

    def __exit__(self, exc_type, exc, tb):
        self.conn.row_factory = self.current_factory
