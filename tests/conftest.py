from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []

    def __iter__(self):
        return iter(self.rows)

    def single(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def consume(self) -> "FakeResult":
        return self


class FakeSession:
    def __init__(self, driver: "FakeDriver") -> None:
        self.driver = driver

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def run(self, query: str, **parameters: Any) -> FakeResult:
        self.driver.calls.append((query, parameters))
        return FakeResult(self.driver.handler(query, parameters))

    def execute_write(self, callback: Callable[..., Any]) -> Any:
        return callback(self)


class FakeDriver:
    def __init__(
        self,
        handler: Callable[[str, dict[str, Any]], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.handler = handler or (lambda _query, _parameters: [])

    def session(self) -> FakeSession:
        return FakeSession(self)


@pytest.fixture()
def fake_driver() -> FakeDriver:
    return FakeDriver()
