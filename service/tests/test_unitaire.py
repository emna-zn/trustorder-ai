"""
Test UNITAIRE
-------------
Teste une fonction pure (scoring.calculer_score) sans base de données,
sans API et sans modèle ML. Seule la logique métier des règles est vérifiée.
"""
from scoring import calculer_score

# Historique vide → score neutre attendu (50)
HISTORIQUE_VIDE = {
    "delivered_orders": 0,
    "refused_orders": 0,
    "not_collected_orders": 0,
    "recent_failed_90d": 0,
    "distinct_shops": 0,
    "reports_count": 0,
}


def test_client_sans_historique_obtient_score_neutre():
    """Un client sans aucune commande doit recevoir un score neutre de 50."""
    resultat = calculer_score(HISTORIQUE_VIDE)
    assert resultat["score"] == 50
    assert resultat["risk_level"] in ("LOW", "MEDIUM", "HIGH")
    assert "factors" in resultat
    assert len(resultat["factors"]) >= 1
