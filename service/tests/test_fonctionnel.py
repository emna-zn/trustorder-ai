"""
Test FONCTIONNEL (bout-en-bout via l'API)
----------------------------------------
Simule un vrai appel HTTP sur l'API FastAPI grâce à TestClient.
On vérifie le comportement observable de l'endpoint /v1/analyze.
"""
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

HISTORIQUE_FIABLE = {
    "delivered_orders": 15,
    "refused_orders": 0,
    "not_collected_orders": 0,
    "recent_failed_90d": 0,
    "distinct_shops": 2,
    "reports_count": 0,
}


def test_endpoint_analyze_retourne_score_et_niveau_de_risque():
    """
    POST /v1/analyze avec un historique fiable doit renvoyer
    un score, un risk_level et le customer_ref fourni.
    """
    reponse = client.post(
        "/v1/analyze",
        json={
            "customer_ref": "CLIENT-DEMO-001",
            "history": HISTORIQUE_FIABLE,
        },
    )

    assert reponse.status_code == 200
    data = reponse.json()

    assert data["customer_ref"] == "CLIENT-DEMO-001"
    assert "score" in data
    assert 0 <= data["score"] <= 100
    assert data["risk_level"] in ("LOW", "MEDIUM", "HIGH")
    assert "factors" in data
    assert isinstance(data["factors"], list)
