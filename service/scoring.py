"""
ÉTAPE 1 — LE SCORE (règles simples)
===================================
On donne une note de 0 à 100 à un client :
  - on part du taux de livraison,
  - on retire des points pour les mauvais signes,
  - on ajoute un bonus pour les clients fidèles.
Chaque point est expliqué dans la liste "factors" : le score n'est jamais une boîte noire.

Un "historique" est un simple dictionnaire Python, par exemple :
  {"delivered_orders": 8, "refused_orders": 2, "not_collected_orders": 0,
   "recent_failed_90d": 1, "distinct_shops": 2, "reports_count": 0}
"""
import config


def compter(h):
    """Calcule 3 chiffres utiles à partir de l'historique."""
    echecs = h["refused_orders"] + h["not_collected_orders"]      # commandes qui ont échoué
    total = h["delivered_orders"] + echecs                        # commandes qui ont une issue
    taux_echec = echecs / total if total > 0 else 0               # évite la division par zéro
    return total, echecs, taux_echec


def niveau_de_risque(score):
    """Transforme un score en niveau : LOW, MEDIUM ou HIGH."""
    if score >= config.SEUIL_FAIBLE_RISQUE:
        return "LOW"
    if score >= config.SEUIL_RISQUE_MOYEN:
        return "MEDIUM"
    return "HIGH"


RECOMMANDATIONS = {
    "LOW": "Client fiable : expédition normale.",
    "MEDIUM": "Confirmer la commande par appel ou SMS avant l'expédition.",
    "HIGH": "Risque élevé : exiger une confirmation ferme ou un acompte avant expédition.",
}


def calculer_score(h):
    total, echecs, taux_echec = compter(h)
    details = []   # la liste des raisons du score

    # 1) Point de départ : le taux de livraison (avec les valeurs "imaginaires" de config.py)
    base = 100 * (h["delivered_orders"] + config.SUCCES_IMAGINAIRES) / (
        total + config.SUCCES_IMAGINAIRES + config.ECHECS_IMAGINAIRES)
    if total > 0:
        texte = f"Taux de livraison : {h['delivered_orders']}/{total} commandes récupérées"
    else:
        texte = "Aucun historique : score neutre de départ"
    details.append({"code": "BASE_DELIVERY_RATE", "label": texte, "points": round(base, 1)})

    # 2) Malus : échecs récents (90 derniers jours)
    if h["recent_failed_90d"] > 0:
        malus = min(h["recent_failed_90d"] * config.PENALITE_ECHEC_RECENT,
                    config.PENALITE_ECHEC_RECENT_MAX)
        details.append({"code": "RECENT_FAILURES",
                        "label": f"{h['recent_failed_90d']} échec(s) sur les 90 derniers jours",
                        "points": -malus})

    # 3) Malus : signalements confirmés
    if h["reports_count"] > 0:
        malus = min(h["reports_count"] * config.PENALITE_SIGNALEMENT,
                    config.PENALITE_SIGNALEMENT_MAX)
        details.append({"code": "REPORTS",
                        "label": f"{h['reports_count']} signalement(s) retenu(s)",
                        "points": -malus})

    # 4) Malus : échecs dans plusieurs boutiques différentes
    if h["distinct_shops"] >= 3 and echecs >= 2 and taux_echec > 0.30:
        details.append({"code": "MULTI_SHOP_FAILURES",
                        "label": f"Échecs répétés dans plusieurs boutiques ({h['distinct_shops']})",
                        "points": -config.PENALITE_MULTI_BOUTIQUES})

    # 5) Bonus : client ancien et fiable
    if h["delivered_orders"] >= config.FIDELITE_MIN_LIVREES and taux_echec <= config.FIDELITE_TAUX_ECHEC_MAX:
        details.append({"code": "LOYALTY", "label": "Historique long et fiable",
                        "points": config.BONUS_FIDELITE})

    # Total : on additionne les points, puis on garde le résultat entre 0 et 100
    score = round(sum(d["points"] for d in details))
    score = max(0, min(100, score))

    niveau = niveau_de_risque(score)
    return {"score": score, "risk_level": niveau,
            "recommendation": RECOMMANDATIONS[niveau], "factors": details}
