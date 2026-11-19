"""
Test d'INTÉGRATION
------------------
Vérifie que plusieurs modules collaborent correctement :
scoring + ml + moteur (analyse client + priorisation de commande).
Aucun serveur HTTP n'est démarré.
"""
import moteur

HISTORIQUE_FIABLE = {
    "delivered_orders": 15,
    "refused_orders": 0,
    "not_collected_orders": 0,
    "recent_failed_90d": 0,
    "distinct_shops": 2,
    "reports_count": 0,
}

HISTORIQUE_RISQUE = {
    "delivered_orders": 1,
    "refused_orders": 6,
    "not_collected_orders": 0,
    "recent_failed_90d": 4,
    "distinct_shops": 3,
    "reports_count": 2,
}


def test_analyse_et_priorisation_coherentes():
    """
    Un client fiable + petite commande → priorité LOW.
    Un client à risque + grosse commande → priorité HIGH.
    Les deux analyses doivent aussi contenir score et cold_start.
    """
    # Client fiable
    analyse_fiable = moteur.analyser_client(HISTORIQUE_FIABLE)
    assert "score" in analyse_fiable
    assert 0 <= analyse_fiable["score"] <= 100
    assert "cold_start" in analyse_fiable

    priorite_fiable = moteur.prioriser_commande(
        HISTORIQUE_FIABLE, {"order_id": "CMD-FIABLE", "amount": 40}
    )
    assert priorite_fiable["priority"] == "LOW"
    assert priorite_fiable["order_id"] == "CMD-FIABLE"

    # Client à risque
    priorite_risque = moteur.prioriser_commande(
        HISTORIQUE_RISQUE, {"order_id": "CMD-RISQUE", "amount": 400}
    )
    assert priorite_risque["priority"] == "HIGH"
    assert priorite_risque["priority_score"] > priorite_fiable["priority_score"]
