"""
RÉGLAGES DU MOTEUR
==================
Tous les chiffres modifiables sont ici. Changez une valeur, relancez, et le comportement change.
(Ce sont des valeurs de départ : à valider avec votre Product Owner.)
"""
import os

# ============================ SPRINT 1 : scoring, ML, priorité ============================

# ---- Cold Start : client avec peu d'historique ----
MIN_HISTORIQUE = 5            # en dessous de 5 commandes, on n'utilise pas le ML

# ---- Score de base ----
# On ajoute 2 succès et 2 échecs "imaginaires" : un client inconnu démarre à 50/100
# et un client avec 1 seule commande n'obtient pas 100/100 trop vite.
SUCCES_IMAGINAIRES = 2
ECHECS_IMAGINAIRES = 2

# ---- Pénalités et bonus (en points sur 100) ----
PENALITE_ECHEC_RECENT = 6         # par échec sur les 90 derniers jours...
PENALITE_ECHEC_RECENT_MAX = 18    # ...mais jamais plus de 18 points
PENALITE_SIGNALEMENT = 5          # par signalement confirmé...
PENALITE_SIGNALEMENT_MAX = 15     # ...mais jamais plus de 15 points
PENALITE_MULTI_BOUTIQUES = 8      # échecs répétés dans au moins 3 boutiques différentes
BONUS_FIDELITE = 5                # bonus pour un client ancien et fiable
FIDELITE_MIN_LIVREES = 10         # au moins 10 commandes livrées
FIDELITE_TAUX_ECHEC_MAX = 0.10    # et 10 % d'échecs au maximum

# ---- Niveaux de risque ----
SEUIL_FAIBLE_RISQUE = 75          # score >= 75  -> LOW    (client fiable)
SEUIL_RISQUE_MOYEN = 50           # score >= 50  -> MEDIUM (à confirmer), sinon HIGH

# ---- Priorité d'une commande (somme des poids = 1) ----
POIDS_RISQUE = 0.60
POIDS_MONTANT = 0.25
POIDS_INCERTITUDE = 0.15
MONTANT_PLAFOND = 300             # en TND : au-dessus, le montant compte au maximum
SEUIL_PRIORITE_HAUTE = 60         # priorité >= 60 -> HIGH (à vérifier en premier)
SEUIL_PRIORITE_MOYENNE = 35       # priorité >= 35 -> MEDIUM, sinon LOW

# ============================ SPRINT 2 : données, import, OCR ============================

JOURS_ECHECS_RECENTS = 90                 # fenêtre des "échecs récents"
TAILLE_MAX_FICHIER = 10 * 1024 * 1024     # 10 Mo par fichier importé
MAX_LIGNES_IMPORT = 5000                  # lignes maximum par fichier
MAX_PAGES_PDF = 20                        # pages maximum lues dans un PDF
MAX_NUMEROS_MASSE = 1000                  # numéros maximum par vérification en masse
MIN_ECHANTILLONS_REENTRAINEMENT = 300     # exemples réels minimum pour réentraîner le modèle
CONFIANCE_OCR_MIN = 0.8                   # en dessous : la ligne extraite doit être vérifiée


def chemin_base():
    """Fichier de la base SQLite de démonstration (variable d'environnement TRUSTORDER_DB pour le changer)."""
    return os.environ.get("TRUSTORDER_DB", "trustorder.db")


def secret_telephone():
    """Secret servant à hacher les numéros. À CHANGER en production (variable TRUSTORDER_SECRET)."""
    return os.environ.get("TRUSTORDER_SECRET", "dev-secret-a-changer-en-production")
