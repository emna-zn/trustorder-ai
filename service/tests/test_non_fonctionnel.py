"""
Test NON FONCTIONNEL
--------------------
Les tests précédents vérifient CE QUE fait le service (le résultat).
Ceux-ci vérifient COMMENT il se comporte :

  1. PERFORMANCE  : le service répond assez vite (exigence du rapport : Symfony
                    abandonne si FastAPI ne répond pas en 3 secondes).
  2. ROBUSTESSE   : des données invalides sont refusées proprement (code 422),
                    sans plantage du serveur (jamais de code 500).
  3. FIABILITÉ    : le même historique donne toujours le même résultat
                    (résultat déterministe, donc explicable et contestable).
"""
import time

from fastapi.testclient import TestClient

import moteur
from main import app

client = TestClient(app)

DELAI_MAX_SECONDES = 3.0        # exigence : délai maximal d'appel de FastAPI par Symfony
NB_REQUETES_CHARGE = 50         # nombre d'appels successifs du test de charge
TAILLE_LOT_MAX = 500            # limite de /v1/prioritize/batch (voir DemandeLot)

HISTORIQUE_FIABLE = {
    "delivered_orders": 15, "refused_orders": 0, "not_collected_orders": 0,
    "recent_failed_90d": 0, "distinct_shops": 2, "reports_count": 0,
}
HISTORIQUE_RISQUE = {
    "delivered_orders": 1, "refused_orders": 6, "not_collected_orders": 0,
    "recent_failed_90d": 4, "distinct_shops": 3, "reports_count": 2,
}


# ---------------------------------------------------------------- 1. PERFORMANCE
def test_performance_une_analyse_repond_en_moins_de_3_secondes():
    """Une analyse unitaire doit respecter le délai de 3 s imposé à Symfony."""
    debut = time.perf_counter()
    reponse = client.post("/v1/analyze", json={"customer_ref": "PERF-1", "history": HISTORIQUE_FIABLE})
    duree = time.perf_counter() - debut

    assert reponse.status_code == 200
    assert duree < DELAI_MAX_SECONDES, f"Analyse trop lente : {duree:.2f} s"


def test_performance_charge_50_requetes_successives():
    """Sous charge (50 appels à la suite), aucun appel ne dépasse 3 s et la moyenne reste faible."""
    durees = []
    for i in range(NB_REQUETES_CHARGE):
        debut = time.perf_counter()
        reponse = client.post("/v1/analyze", json={"customer_ref": f"CHARGE-{i}", "history": HISTORIQUE_RISQUE})
        durees.append(time.perf_counter() - debut)
        assert reponse.status_code == 200

    assert max(durees) < DELAI_MAX_SECONDES, f"Pire temps : {max(durees):.2f} s"
    assert sum(durees) / len(durees) < 0.5, f"Temps moyen : {sum(durees) / len(durees):.3f} s"


def test_performance_lot_maximal_de_500_commandes():
    """Le lot le plus gros accepté (500 commandes) doit être traité en moins de 3 s."""
    item = {"history": HISTORIQUE_RISQUE, "order": {"order_id": "LOT", "amount": 120}}
    debut = time.perf_counter()
    reponse = client.post("/v1/prioritize/batch", json={"items": [item] * TAILLE_LOT_MAX})
    duree = time.perf_counter() - debut

    assert reponse.status_code == 200
    assert len(reponse.json()["results"]) == TAILLE_LOT_MAX
    assert duree < DELAI_MAX_SECONDES, f"Lot de {TAILLE_LOT_MAX} trop lent : {duree:.2f} s"


# ----------------------------------------------------------------- 2. ROBUSTESSE
def test_robustesse_valeurs_negatives_refusees():
    """Un nombre de commandes négatif est rejeté (422), pas accepté ni transformé en erreur 500."""
    historique = dict(HISTORIQUE_FIABLE, delivered_orders=-5)
    reponse = client.post("/v1/analyze", json={"history": historique})
    assert reponse.status_code == 422


def test_robustesse_donnees_manquantes_ou_mal_typees_refusees():
    """Historique absent, texte à la place d'un nombre : rejet propre (422)."""
    assert client.post("/v1/analyze", json={}).status_code == 422
    mauvais_type = dict(HISTORIQUE_FIABLE, refused_orders="beaucoup")
    assert client.post("/v1/analyze", json={"history": mauvais_type}).status_code == 422


def test_robustesse_montant_de_commande_invalide_refuse():
    """Une commande de montant nul ou négatif est rejetée (le montant doit être > 0)."""
    for montant in (0, -10):
        reponse = client.post(
            "/v1/prioritize",
            json={"history": HISTORIQUE_FIABLE, "order": {"order_id": "X", "amount": montant}},
        )
        assert reponse.status_code == 422


def test_robustesse_lots_vide_ou_trop_gros_refuses():
    """Un lot vide ou de plus de 500 commandes est refusé (protège le serveur d'une surcharge)."""
    item = {"history": HISTORIQUE_FIABLE, "order": {"order_id": "X", "amount": 50}}
    assert client.post("/v1/prioritize/batch", json={"items": []}).status_code == 422
    assert client.post("/v1/prioritize/batch", json={"items": [item] * (TAILLE_LOT_MAX + 1)}).status_code == 422


def test_robustesse_le_service_reste_disponible_apres_des_erreurs():
    """Après plusieurs requêtes invalides, le service répond toujours normalement."""
    for _ in range(10):
        client.post("/v1/analyze", json={"history": {"delivered_orders": -1}})
    assert client.get("/health").json() == {"status": "ok"}
    assert client.post("/v1/analyze", json={"history": HISTORIQUE_FIABLE}).status_code == 200


# ------------------------------------------------------------------ 3. FIABILITÉ
def test_fiabilite_resultat_deterministe():
    """Le même historique donne exactement le même score et le même niveau de risque, 20 fois de suite."""
    premier = moteur.analyser_client(HISTORIQUE_RISQUE)
    for _ in range(20):
        suivant = moteur.analyser_client(HISTORIQUE_RISQUE)
        assert suivant["score"] == premier["score"]
        assert suivant["risk_level"] == premier["risk_level"]


def test_fiabilite_le_score_ne_depend_pas_de_la_reference_client():
    """customer_ref n'est qu'une étiquette : changer l'étiquette ne doit pas changer le score."""
    a = client.post("/v1/analyze", json={"customer_ref": "A", "history": HISTORIQUE_RISQUE}).json()
    b = client.post("/v1/analyze", json={"customer_ref": "B", "history": HISTORIQUE_RISQUE}).json()
    assert a["score"] == b["score"]
    assert a["risk_level"] == b["risk_level"]
