"""
ÉTAPES 3 ET 4 — COLD START ET PRIORITÉ
======================================
Ce fichier assemble les morceaux :
  analyser_client()   : score (règles) + prédiction (ML), avec gestion du Cold Start
  prioriser_commande(): classe une commande selon l'attention qu'elle demande
"""
import config
import ml
import scoring

MODELE = ml.charger_ou_entrainer()   # chargé une seule fois, au démarrage


def analyser_client(h):
    resultat = scoring.calculer_score(h)
    total, _, _ = scoring.compter(h)

    # COLD START : trop peu de commandes -> le ML ne serait pas fiable -> on utilise seulement les règles
    if total < config.MIN_HISTORIQUE:
        cold_start = True
        proba = None
        notes = [f"Cold start : historique insuffisant ({total}/{config.MIN_HISTORIQUE} commandes). "
                 "Décision basée sur les règles."]
    else:
        cold_start = False
        proba = round(ml.predire_retention(MODELE, h), 4)
        notes = []

    resultat["cold_start"] = cold_start
    resultat["retention_probability"] = proba
    resultat["prediction_source"] = "RULES+ML" if proba is not None else "RULES"
    resultat["model_version"] = ml.VERSION if proba is not None else None
    resultat["notes"] = notes
    return resultat


def prioriser_commande(h, commande):
    """
    Priorité (0-100) = 60 % risque + 25 % montant + 15 % incertitude.
    Plus le résultat est haut, plus la commande doit être vérifiée EN PREMIER.
    """
    analyse = analyser_client(h)
    total, _, _ = scoring.compter(h)

    # a) Risque : on préfère l'avis du ML s'il existe, sinon on utilise le score à règles
    if analyse["retention_probability"] is not None:
        risque = (1 - analyse["retention_probability"]) * 100
        texte_risque = f"Risque de refus estimé par l'IA ({risque:.0f} %)"
    else:
        risque = 100 - analyse["score"]
        texte_risque = f"Risque issu du score de fiabilité ({analyse['score']}/100)"

    # b) Montant : proportionnel jusqu'au plafond (300 TND = note maximale)
    montant = min(commande["amount"] / config.MONTANT_PLAFOND, 1) * 100

    # c) Incertitude : un client sans historique est une inconnue
    incertitude = max(0, 1 - total / config.MIN_HISTORIQUE) * 100

    details = [
        {"code": "RISK", "label": texte_risque, "points": round(config.POIDS_RISQUE * risque, 1)},
        {"code": "AMOUNT", "label": f"Montant à encaisser : {commande['amount']:.0f} TND",
         "points": round(config.POIDS_MONTANT * montant, 1)},
        {"code": "UNCERTAINTY",
         "label": "Peu ou pas d'historique" if incertitude > 0 else "Historique suffisant",
         "points": round(config.POIDS_INCERTITUDE * incertitude, 1)},
    ]
    score = max(0, min(100, round(sum(d["points"] for d in details))))

    if score >= config.SEUIL_PRIORITE_HAUTE:
        priorite = "HIGH"
    elif score >= config.SEUIL_PRIORITE_MOYENNE:
        priorite = "MEDIUM"
    else:
        priorite = "LOW"

    # Phrase d'explication : on cite les facteurs qui comptent (>= 5 points), du plus fort au plus faible
    importants = [d["label"] for d in sorted(details, key=lambda d: -d["points"]) if d["points"] >= 5]
    explication = f"Priorité {priorite} ({score}/100)"
    explication += " : " + " ; ".join(importants) + "." if importants else "."

    return {"order_id": commande.get("order_id"), "priority_score": score, "priority": priorite,
            "explanation": explication, "factors": details,
            "cold_start": analyse["cold_start"], "prediction_source": analyse["prediction_source"]}
