import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client
    test_client.post("/api/reset")


def test_index_and_health(client):
    index = client.get("/")
    assert index.status_code == 200
    assert "Anchor" in index.text

    health = client.get("/api/health").json()
    assert health["status"] == "ok"
    assert health["customers"] > 0
    assert health["model_auc"] > 0.7


def test_overview_contract(client):
    overview = client.get("/api/overview").json()
    assert overview["dataset"]["source"] == "demo"
    assert overview["kpis"]["customers"] == 1680
    assert overview["kpis"]["mrr"] > 0
    assert 0 < overview["kpis"]["churn_rate"] < 1
    assert len(overview["drivers"]) > 0
    assert len(overview["top_customers"]) == 8
    assert len(overview["trend"]) > len(overview["cohorts"]["rows"])


def test_customer_filters(client):
    page = client.get("/api/customers", params={"segment": "high", "limit": 10}).json()
    assert page["total"] > 0
    assert all(item["segment"] == "high" for item in page["items"])
    assert len(page["items"]) <= 10

    search = client.get("/api/customers", params={"q": "Fin"}).json()
    assert all("fin" in (item["company"] + item["industry"]).lower() for item in search["items"])


def test_customer_detail_and_simulation(client):
    customer = client.get("/api/customers", params={"limit": 1}).json()["items"][0]
    detail = client.get(f"/api/customers/{customer['id']}").json()

    assert detail["customer"]["id"] == customer["id"]
    assert 0 <= detail["risk"] <= 1
    assert detail["risks"]
    assert detail["playbooks"]

    playbook = detail["playbooks"][0]
    result = client.post(
        "/api/simulate",
        json={"customer_id": customer["id"], "playbook_ids": [playbook["id"]]},
    ).json()

    assert result["risk_after"] <= result["risk_before"]
    assert result["saved_mrr"] >= 0
    assert result["changes"]


def test_missing_customer(client):
    assert client.get("/api/customers/999999").status_code == 404
    assert client.post("/api/simulate", json={"customer_id": 999999, "playbook_ids": []}).status_code == 404


def test_upload_and_reset(client):
    content = (
        "company,mrr,plan,seats,active_ratio,feature_adoption,tenure_months\n"
        "Acme Retail,1200,Scale,50,0.4,0.3,8\n"
        "Beta Labs,300,Growth,10,0.8,0.7,24\n"
    )
    response = client.post(
        "/api/upload",
        files={"file": ("clients.csv", content.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["imported"] == 2

    overview = client.get("/api/overview").json()
    assert overview["dataset"]["source"] == "upload"
    assert overview["dataset"]["filename"] == "clients.csv"
    assert overview["kpis"]["customers"] == 2

    reset = client.post("/api/reset")
    assert reset.status_code == 200

    overview = client.get("/api/overview").json()
    assert overview["dataset"]["source"] == "demo"
    assert overview["kpis"]["customers"] == 1680


def test_upload_requires_columns(client):
    response = client.post(
        "/api/upload",
        files={"file": ("bad.csv", b"foo,bar\n1,2\n", "text/csv")},
    )
    assert response.status_code == 400
