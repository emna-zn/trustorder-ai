"""
LE NUMÉRO DE TÉLÉPHONE
======================
Deux choses à faire avec un numéro :
  1) le NORMALISER : "+216 22 123 456", "22123456" et "0021622123456" deviennent tous "21622123456"
  2) le HACHER : on le transforme en une longue suite de lettres/chiffres impossible à inverser.
     Ce hachage sert de clé pour regrouper l'historique d'un client entre boutiques,
     sans jamais envoyer le vrai numéro au service IA.
"""
import hashlib
import hmac
import re

import config


def normaliser(valeur):
    """Retourne le numéro au format '216XXXXXXXX', ou None s'il n'est pas un numéro tunisien valide."""
    if valeur is None:
        return None
    if isinstance(valeur, float) and valeur.is_integer():     # Excel donne parfois 22123456.0
        valeur = int(valeur)
    texte = re.sub(r"\.0+$", "", str(valeur).strip())
    chiffres = re.sub(r"\D+", "", texte)                      # on garde uniquement les chiffres
    if chiffres.startswith("00216"):
        chiffres = chiffres[2:]
    if len(chiffres) == 8:                                    # numéro local sans indicatif
        chiffres = "216" + chiffres
    if re.fullmatch(r"216[2-9]\d{7}", chiffres):
        return chiffres
    return None


def hacher(normalise):
    """Hachage HMAC-SHA256 d'un numéro déjà normalisé (64 caractères)."""
    return hmac.new(config.secret_telephone().encode(), normalise.encode(), hashlib.sha256).hexdigest()
