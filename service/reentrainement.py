"""
RÉENTRAÎNEMENT SUR LES VRAIES COMMANDES
=======================================
Au Sprint 1, le modèle apprenait sur des clients fictifs. Maintenant que des commandes réelles sont importées,
on peut l'entraîner sur la réalité.

Principe : pour chaque client, on rejoue son histoire dans l'ordre du temps. À chaque commande (à partir de la 6e),
on se demande : "Avec ce qu'on savait AVANT cette commande, a-t-elle été récupérée ?"
  -> les caractéristiques = l'historique avant la commande
  -> la réponse attendue   = 1 si la commande a été récupérée, 0 sinon

Usage :   python reentrainement.py            (il faut au moins 300 exemples réels)
          python reentrainement.py --min 100
Le serveur doit être redémarré ensuite pour utiliser le nouveau modèle.
"""
import argparse
from contextlib import closing
from datetime import date, timedelta

import joblib
import numpy as np

import config
import ml
import stockage


def construire_jeu():
    """Retourne (X, y) construits à partir des commandes réelles déjà résolues."""
    with closing(stockage.connexion()) as con:
        lignes = con.execute("SELECT telephone_hash, boutique_id, statut, date_commande FROM commandes "
                             "WHERE statut IN ('DELIVERED','REFUSED','NOT_COLLECTED') "
                             "ORDER BY telephone_hash, date_commande, id").fetchall()
    par_client = {}
    for r in lignes:
        par_client.setdefault(r["telephone_hash"], []).append(r)

    X, y = [], []
    for commandes in par_client.values():
        livrees = refusees = non_recuperees = 0
        dates_echecs, boutiques = [], set()
        for i, c in enumerate(commandes):
            if i >= config.MIN_HISTORIQUE:                       # assez d'historique avant cette commande
                limite = (date.fromisoformat(c["date_commande"]) - timedelta(days=config.JOURS_ECHECS_RECENTS)).isoformat()
                historique = {"delivered_orders": livrees, "refused_orders": refusees,
                              "not_collected_orders": non_recuperees,
                              "recent_failed_90d": sum(1 for d in dates_echecs if d >= limite),
                              "distinct_shops": len(boutiques), "reports_count": 0}
                X.append(ml.caracteristiques(historique))
                y.append(1 if c["statut"] == "DELIVERED" else 0)
            # on ajoute cette commande à l'histoire du client
            boutiques.add(c["boutique_id"])
            if c["statut"] == "DELIVERED":
                livrees += 1
            else:
                dates_echecs.append(c["date_commande"])
                if c["statut"] == "REFUSED":
                    refusees += 1
                else:
                    non_recuperees += 1
    return np.array(X), np.array(y)


def reentrainer(min_echantillons=None, sortie=None):
    """Entraîne et sauvegarde le modèle si les données réelles sont suffisantes. Retourne un compte rendu."""
    min_echantillons = min_echantillons or config.MIN_ECHANTILLONS_REENTRAINEMENT
    X, y = construire_jeu()
    if len(y) < min_echantillons:
        return {"retrained": False, "samples": int(len(y)),
                "reason": f"Pas assez d'exemples réels ({len(y)}/{min_echantillons}) : le modèle actuel est conservé."}
    if len(set(y.tolist())) < 2:
        return {"retrained": False, "samples": int(len(y)),
                "reason": "Les exemples ne contiennent qu'un seul type de résultat : impossible d'apprendre."}
    modele, precision = ml.entrainer_depuis(X, y)
    chemin = sortie or ml.chemin_modele()
    joblib.dump(modele, chemin)
    return {"retrained": True, "samples": int(len(y)), "accuracy": round(float(precision), 4), "model_file": chemin}


if __name__ == "__main__":
    parseur = argparse.ArgumentParser()
    parseur.add_argument("--min", type=int, default=None, help="nombre minimum d'exemples réels")
    print(reentrainer(parseur.parse_args().min))
