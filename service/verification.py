"""
ÉTAPE DE VÉRIFICATION (US08)
============================
Après un import (fichier ou OCR), chaque ligne est contrôlée. Une ligne contient :
  - les champs MODIFIABLES (ce que l'utilisateur voit et corrige) :
      phone, status, amount, order_date, label, ignore
  - les champs CALCULÉS par ce fichier :
      phone_normalized, status_normalized, amount_value, date_value, issues, valid

Un problème ("issue") est soit une ERREUR (la ligne ne sera pas enregistrée tant qu'elle n'est pas corrigée),
soit un AVERTISSEMENT (à regarder, mais la ligne peut être enregistrée).
"""
from datetime import date

import normalisation as nz
import telephone

CHAMPS_MODIFIABLES = ["phone", "status", "amount", "order_date", "label"]


def _probleme(niveau, champ, message):
    return {"level": niveau, "field": champ, "message": message}


def valider_ligne(ligne, aujourdhui=None):
    """Contrôle une ligne et remplit ses champs calculés. Retourne la même ligne."""
    aujourdhui = aujourdhui or date.today()
    problemes = []

    # --- Téléphone
    tel = telephone.normaliser(ligne.get("phone"))
    if tel is None:
        problemes.append(_probleme("error", "phone", "Numéro invalide ou absent (format tunisien attendu, 8 chiffres)."))

    # --- Statut
    brut = ligne.get("status")
    texte = "" if brut is None else str(brut)
    if texte.strip() == "":
        statut = "PENDING"
        problemes.append(_probleme("warning", "status", "Statut absent : la commande sera considérée comme en attente."))
    else:
        statut = nz.normaliser_statut(texte)
        if statut is None:
            problemes.append(_probleme("error", "status", f"Statut non reconnu : « {texte.strip()} »."))

    # --- Montant
    montant = None
    try:
        montant = nz.lire_montant(ligne.get("amount"))
        if montant is None:
            problemes.append(_probleme("warning", "amount", "Montant absent."))
        elif montant < 0:
            problemes.append(_probleme("error", "amount", "Le montant ne peut pas être négatif."))
    except ValueError:
        problemes.append(_probleme("error", "amount", f"Montant illisible : « {ligne.get('amount')} »."))

    # --- Date
    jour = None
    try:
        jour = nz.lire_date(ligne.get("order_date"))
        if jour is None:
            jour = aujourdhui.isoformat()
            problemes.append(_probleme("warning", "order_date", "Date absente : la date du jour sera utilisée."))
        elif jour > aujourdhui.isoformat():
            problemes.append(_probleme("warning", "order_date", "Date dans le futur."))
    except ValueError:
        problemes.append(_probleme("error", "order_date", f"Date illisible : « {ligne.get('order_date')} »."))

    ligne["phone_normalized"] = tel
    ligne["status_normalized"] = statut
    ligne["amount_value"] = montant
    ligne["date_value"] = jour
    ligne["issues"] = problemes
    ligne["valid"] = not any(p["level"] == "error" for p in problemes)
    return ligne


def valider_lot(lignes, aujourdhui=None):
    """Contrôle toutes les lignes d'un lot, puis repère les doublons (même numéro, date, montant et libellé)."""
    vus = set()
    for ligne in lignes:
        valider_ligne(ligne, aujourdhui)
        if ligne.get("ignore") or not ligne["valid"]:
            continue
        cle = (ligne["phone_normalized"], ligne["date_value"], ligne["amount_value"],
               nz.nettoyer(ligne.get("label") or ""))
        if cle in vus:
            ligne["issues"].append(_probleme("warning", "phone", "Doublon : même numéro, date, montant et libellé qu'une ligne précédente."))
        vus.add(cle)
    return lignes


def resume(lignes):
    """Chiffres clés pour l'écran de vérification."""
    actives = [l for l in lignes if not l.get("ignore")]
    return {
        "lines": len(lignes),
        "ignored": len(lignes) - len(actives),
        "valid": sum(1 for l in actives if l["valid"]),
        "with_errors": sum(1 for l in actives if not l["valid"]),
        "with_warnings": sum(1 for l in actives if l["valid"] and any(p["level"] == "warning" for p in l["issues"])),
    }
