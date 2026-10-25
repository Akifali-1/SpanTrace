import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def project(client):
    response = client.post("/v1/projects", json={"name": "Test project"})
    assert response.status_code == 201
    return response.json()
