from __future__ import annotations

from pathlib import Path

import pytest

from radar.catalog import Catalog
from radar.collectors import Context

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def cat() -> Catalog:
    return Catalog.load()


class FakeResponse:
    def __init__(self, content: bytes, status: int = 200, payload=None):
        self.content, self.status_code, self._payload = content, status, payload
        self.headers: dict = {}

    @property
    def text(self) -> str:
        return self.content.decode()

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeFetcher:
    """Serves canned responses by URL substring; records the URLs asked for."""

    def __init__(self, routes: dict[str, FakeResponse]):
        self.routes, self.calls = routes, []

    def get(self, url: str, retries: int = 3, headers: dict | None = None):
        self.calls.append(url)
        for key, resp in self.routes.items():
            if key in url:
                return resp
        raise AssertionError(f"unexpected URL {url}")

    def get_conditional(self, url: str, state: dict):
        return self.get(url)


@pytest.fixture
def ctx_factory():
    def make(routes: dict[str, FakeResponse], state: dict | None = None, backfill: bool = True) -> Context:
        return Context(fetcher=FakeFetcher(routes), state=state if state is not None else {}, seen=set(),
                       backfill=backfill)
    return make
