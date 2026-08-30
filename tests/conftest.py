from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """Create an isolated API client for each contract test."""
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
