"""
RECHERCHE ET VÉRIFICATION EN MASSE (US09 et US10)
=================================================
  rechercher_client()  : un numéro -> son historique agrégé + son analyse (score, risque, prédiction)
  verifier_en_masse()  : une liste de numéros -> une analyse par numéro + un résumé

Ces deux fonctions branchent les données importées (stockage.py) sur le moteur du Sprint 1 (moteur.py).
"""
import csv
import io

import config
import moteur
import stockage
import telephone


def rechercher_client(numero_brut, boutique_id=None):
    tel = telephone.normaliser(numero_brut)
    if tel is None:
        raise ValueError("Numéro invalide (format tunisien attendu, 8 chiffres).")
    h = telephone.hacher(tel)
    historique = stockage.historique_par_telephone([h]).get(h)
    connu = historique is not None
    historique = historique or dict(stockage.HISTORIQUE_VIDE)

    reponse = {"phone": tel, "known_customer": connu, "history": historique,
               "analysis": moteur.analyser_client(historique)}
    if boutique_id is not None:
        reponse["shop_orders"] = stockage.commandes_de_boutique(boutique_id, h)
    return reponse


def verifier_en_masse(numeros):
    """Analyse une liste de numéros (jusqu'à 1000). Les résultats gardent l'ordre de la liste."""
    if len(numeros) > config.MAX_NUMEROS_MASSE:
        raise ValueError(f"Trop de numéros : {config.MAX_NUMEROS_MASSE} maximum par vérification.")

    normalises = [telephone.normaliser(n) for n in numeros]
    hashes = {n: telephone.hacher(n) for n in set(normalises) if n}
    historiques = stockage.historique_par_telephone(list(hashes.values()))    # UNE requête pour tous les numéros

    analyses = {}                                                             # une seule analyse par numéro distinct
    resultats = []
    for saisi, tel in zip(numeros, normalises):
        ligne = {"input": saisi, "phone": tel}
        if tel is None:
            ligne.update(result_type="INVALID_NUMBER", orders=0, score=None, risk_level=None, cold_start=None,
                         retention_probability=None,
                         recommendation="Numéro invalide : à corriger avant toute vérification.")
        else:
            historique = historiques.get(hashes[tel])
            if historique is None:
                ligne.update(result_type="UNKNOWN_CUSTOMER", orders=0, score=None, risk_level="UNKNOWN",
                             cold_start=True, retention_probability=None,
                             recommendation="Aucun historique : traiter comme un nouveau client (confirmer la commande).")
            else:
                if tel not in analyses:
                    analyses[tel] = moteur.analyser_client(historique)
                a = analyses[tel]
                total = historique["delivered_orders"] + historique["refused_orders"] + historique["not_collected_orders"]
                ligne.update(result_type="ANALYZED", orders=total, score=a["score"], risk_level=a["risk_level"],
                             cold_start=a["cold_start"], retention_probability=a["retention_probability"],
                             recommendation=a["recommendation"])
        resultats.append(ligne)

    comptes = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    for r in resultats:
        if r["result_type"] == "ANALYZED":
            comptes[r["risk_level"]] += 1
    resume = {"total": len(resultats),
              "invalid_numbers": sum(1 for r in resultats if r["result_type"] == "INVALID_NUMBER"),
              "unknown_customers": sum(1 for r in resultats if r["result_type"] == "UNKNOWN_CUSTOMER"),
              **comptes}
    return {"summary": resume, "results": resultats}


def vers_csv(resultats):
    """Exporte les résultats de la vérification en masse au format CSV (ouvrable dans Excel)."""
    sortie = io.StringIO()
    colonnes = ["input", "phone", "result_type", "orders", "score", "risk_level", "recommendation"]
    ecrivain = csv.DictWriter(sortie, fieldnames=colonnes, delimiter=";", extrasaction="ignore")
    ecrivain.writeheader()
    ecrivain.writerows(resultats)
    return "\ufeff" + sortie.getvalue()          # \ufeff : permet à Excel de lire correctement les accents
