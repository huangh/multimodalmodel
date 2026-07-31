"""Smoke tests for the hub ASGI app."""

from pathlib import Path

import pytest

from multimodalmodel.hub.server import create_app
from multimodalmodel.hub.usage import UsageStore

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    starlette_testclient = pytest.importorskip("starlette.testclient")
    db = tmp_path_factory.mktemp("hub") / "usage.db"
    store = UsageStore(db)
    store.record("benchmark/eta_accuracy_demo", user="alice", session_id="s1")
    app = create_app(
        scripts_root=REPO / "scripts",
        hub_notebook=REPO / "notebooks" / "hub.py",
        db_path=db,
    )
    with starlette_testclient.TestClient(app) as client:
        yield client


def test_healthz(client):
    body = client.get("/healthz").json()
    assert body["ok"] is True
    assert body["scripts"] >= 1


def test_scripts_listing_includes_usage_and_urls(client):
    body = client.get("/api/scripts").json()
    ids = {s["script_id"]: s for s in body["scripts"]}
    demo = ids["benchmark/eta_accuracy_demo"]
    assert demo["uses"] == 1
    assert demo["url"] == "/s/benchmark/eta_accuracy_demo"
    assert "offline" in demo["tags"]


def test_scripts_listing_filters(client):
    body = client.get("/api/scripts", params={"q": "gtfs"}).json()
    assert body["count"] >= 1
    assert all("gtfs" in s["script_id"] or "gtfs" in s["tags"] for s in body["scripts"])


def test_usage_endpoints(client):
    top = client.get("/api/usage/top", params={"limit": 1}).json()
    assert top[0]["script_id"] == "benchmark/eta_accuracy_demo"
    assert client.get("/api/usage/recent").json()[0]["user"] == "alice"


def test_hub_and_standalone_pages_render(client):
    assert client.get("/").status_code == 200
    resp = client.get("/s/benchmark/eta_accuracy_demo", follow_redirects=True)
    assert resp.status_code == 200
