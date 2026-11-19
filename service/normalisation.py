"""
NORMALISATION DES VALEURS
=========================
Les fichiers des boutiques sont "sales" : "Livré", "livree", "DELIVERED" veulent dire la même chose,
les montants s'écrivent "45,500 DT" ou "45.5", les dates "12/09/2026" ou "2026-09-12"...
Ce fichier transforme toutes ces variantes en valeurs propres et uniques.
"""
import re
import unicodedata
from datetime import date, datetime, timedelta


def sans_accents(texte):
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


def nettoyer(texte):
    """'Non récupéré !' -> 'non recupere' (minuscules, sans accents, sans ponctuation)."""
    texte = sans_accents(str(texte)).lower()
    texte = re.sub(r"[^a-z0-9]+", " ", texte)
    return texte.strip()


# ------------------------------------------------------------------ STATUTS
# L'ORDRE COMPTE : "non livré" doit être reconnu avant "livré".
MOTS_STATUTS = [
    ("NOT_COLLECTED", ["non recupere", "non retire", "non reclame", "non livre", "pas recupere",
                       "injoignable", "absent", "pas de reponse", "no answer", "not collected",
                       "no show", "not delivered", "undelivered", "echec livraison", "failed"]),
    ("REFUSED", ["refuse", "refused", "rejete", "rejected", "declined", "retour", "retourne",
                 "returned", "rto", "annule par le client", "client annule"]),
    ("PENDING", ["en attente", "attente", "pending", "en cours", "en livraison", "expedie", "shipped",
                 "nouveau", "new", "confirme", "confirmed", "en preparation", "processing"]),
    ("DELIVERED", ["livre", "livree", "delivered", "recupere", "retire", "encaisse", "recu",
                   "success", "paye", "paid", "complete", "completed", "termine"]),
]


def normaliser_statut(valeur):
    """Retourne DELIVERED, REFUSED, NOT_COLLECTED, PENDING... ou None si le texte n'est pas reconnu."""
    texte = nettoyer(valeur)
    for statut, mots in MOTS_STATUTS:
        for mot in mots:
            # (?:e|s|es)? accepte le féminin et le pluriel : refusé, refusée, refusés...
            if re.search(r"\b" + re.escape(mot) + r"(?:e|s|es)?\b", texte):
                return statut
    return None


# ------------------------------------------------------------------ MONTANTS
def lire_montant(valeur):
    """'45,500 DT' -> 45.5 ; vide -> None ; illisible -> ValueError."""
    if valeur is None or str(valeur).strip() == "":
        return None
    if isinstance(valeur, (int, float)):
        return float(valeur)
    t = re.sub(r"(tnd|dinars?|d\.t\.?|dt)", "", str(valeur).lower())
    t = t.replace("\u00a0", "").replace(" ", "")
    if "," in t and "." in t:                       # ex. 1.250,500 : le dernier séparateur est la virgule décimale
        dernier = max(t.rfind(","), t.rfind("."))
        t = t[:dernier].replace(",", "").replace(".", "") + "." + t[dernier + 1:]
    else:
        t = t.replace(",", ".")
        if t.count(".") > 1:                        # ex. 1.250.000
            dernier = t.rfind(".")
            t = t[:dernier].replace(".", "") + "." + t[dernier + 1:]
    return float(t)                                 # lève ValueError si ce n'est pas un nombre


# ------------------------------------------------------------------ DATES
FORMATS_DATE = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%Y/%m/%d",
                "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]


def lire_date(valeur):
    """Retourne une date au format 'AAAA-MM-JJ', None si vide, ValueError si illisible."""
    if valeur is None or str(valeur).strip() == "":
        return None
    if isinstance(valeur, datetime):
        return valeur.date().isoformat()
    if isinstance(valeur, date):
        return valeur.isoformat()
    if isinstance(valeur, (int, float)) and 30000 < valeur < 60000:      # numéro de série Excel
        return (date(1899, 12, 30) + timedelta(days=int(valeur))).isoformat()
    texte = str(valeur).strip()
    for fmt in FORMATS_DATE:
        try:
            return datetime.strptime(texte, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Date illisible : {texte}")
