"""
ÉTAPE 2 — LE MODÈLE DE MACHINE LEARNING
=======================================
Idée : un modèle apprend à partir d'exemples (clients + ce qui s'est passé à leur commande suivante)
pour estimer la probabilité qu'un client récupère sa prochaine commande.

Sprint 1 : on n'avait pas de vraies données -> on en FABRIQUE (fictives).
Sprint 2 : on peut entraîner le modèle sur les VRAIES commandes importées (voir reentrainement.py).

Le modèle est entraîné automatiquement au premier lancement (environ 1 seconde)
puis sauvegardé dans le fichier modele.joblib.
"""
import os

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

import scoring

VERSION = "logreg-simple"


def chemin_modele():
    """Fichier du modèle (variable d'environnement TRUSTORDER_MODELE pour le changer)."""
    return os.environ.get("TRUSTORDER_MODELE", os.path.join(os.path.dirname(__file__), "modele.joblib"))


def caracteristiques(h):
    """Les 4 nombres que le modèle regarde pour chaque client."""
    total, echecs, taux_echec = scoring.compter(h)
    return [taux_echec, h["recent_failed_90d"], h["reports_count"], total]


def fabriquer_donnees(n_clients=5000):
    """Crée des clients fictifs. Chaque client a une 'fiabilité cachée' entre 0 et 1."""
    hasard = np.random.default_rng(42)       # 42 = résultats identiques à chaque lancement
    X, y = [], []
    for _ in range(n_clients):
        # 80 % de clients plutôt fiables, 20 % plutôt à risque
        fiabilite = hasard.beta(6, 2) if hasard.random() < 0.8 else hasard.beta(2, 5)

        nb_commandes = int(hasard.integers(5, 41))
        livrees = int(hasard.binomial(nb_commandes, fiabilite))
        echecs = nb_commandes - livrees
        recents = int(hasard.binomial(echecs, 0.4)) if echecs > 0 else 0
        signalements = int(hasard.poisson(0.25 * echecs))

        X.append([echecs / nb_commandes, recents, signalements, nb_commandes])
        y.append(1 if hasard.random() < fiabilite else 0)   # 1 = a récupéré sa commande suivante
    return np.array(X), np.array(y)


def entrainer_depuis(X, y):
    """Entraîne un modèle sur des exemples (X = caractéristiques, y = 1 récupérée / 0 échec).
    Retourne (modèle, précision mesurée sur 20 % de données gardées de côté)."""
    X_app, X_test, y_app, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    modele = LogisticRegression(max_iter=1000)
    modele.fit(X_app, y_app)
    precision = accuracy_score(y_test, modele.predict(X_test))
    return modele, precision


def entrainer():
    """Entraîne le modèle sur les données fictives du Sprint 1."""
    X, y = fabriquer_donnees()
    modele, precision = entrainer_depuis(X, y)
    print(f"[ML] Modèle entraîné. Précision sur les données de test : {precision:.0%}")
    return modele


def charger_ou_entrainer():
    """Charge modele.joblib s'il existe, sinon entraîne le modèle et le sauvegarde."""
    chemin = chemin_modele()
    if os.path.exists(chemin):
        return joblib.load(chemin)
    modele = entrainer()
    joblib.dump(modele, chemin)
    return modele


def predire_retention(modele, h):
    """Retourne une probabilité entre 0 et 1 (0.82 = 82 % de chances de récupérer la commande)."""
    return float(modele.predict_proba([caracteristiques(h)])[0][1])
