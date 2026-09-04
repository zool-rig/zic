from typing import Any, Self
from collections.abc import Sequence


class QueryBuilder:
    def __init__(self, query: str, *args: Any) -> None:
        self.query: str = query
        self.arguments: list[Any] = list(args)

    def push(self, query: str) -> Self:
        self.query = f"{self.query} {query}"
        return self

    def push_bind(self, value: Any) -> Self:
        self.query = f"{self.query} ?"
        self.arguments.append(value)
        return self

    def push_binds(self, values: Sequence[Any]) -> Self:
        placeholders = ", ".join("?" * len(values))
        self.query = f"{self.query} ({placeholders})"
        self.arguments.extend(values)
        return self

    def build(self) -> tuple[str, list[Any]]:
        self.query = self.query.replace(";", "")
        self.query += ";"
        return self.query, self.arguments

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.query!r}, {self.arguments!r})"
