"""
Réglages autorisés et analyse par lot.
Les formules de scoring.py, moteur.py et ml.py ne sont pas ici :
on ne fait que lire ou remplacer les constantes déjà prévues dans config.py.
"""
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import config
import moteur

router = APIRouter()

SPEC = {
    "MIN_HISTORIQUE": ("int", 1, 50),
    "SUCCES_IMAGINAIRES": ("int", 0, 20),
    "ECHECS_IMAGINAIRES": ("int", 0, 20),
    "PENALITE_ECHEC_RECENT": ("int", 0, 50),
    "PENALITE_ECHEC_RECENT_MAX": ("int", 0, 100),
    "PENALITE_SIGNALEMENT": ("int", 0, 50),
    "PENALITE_SIGNALEMENT_MAX": ("int", 0, 100),
    "PENALITE_MULTI_BOUTIQUES": ("int", 0, 50),
    "BONUS_FIDELITE": ("int", 0, 30),
    "FIDELITE_MIN_LIVREES": ("int", 1, 100),
    "FIDELITE_TAUX_ECHEC_MAX": ("float", 0, 1),
    "SEUIL_FAIBLE_RISQUE": ("int", 0, 100),
    "SEUIL_RISQUE_MOYEN": ("int", 0, 100),
    "POIDS_RISQUE": ("float", 0, 1),
    "POIDS_MONTANT": ("float", 0, 1),
    "POIDS_INCERTITUDE": ("float", 0, 1),
    "MONTANT_PLAFOND": ("int", 1, 100000),
    "SEUIL_PRIORITE_HAUTE": ("int", 0, 100),
    "SEUIL_PRIORITE_MOYENNE": ("int", 0, 100),
}

# Photo des constantes du fichier, prise au chargement, avant toute modification.
DEFAULTS = {key: getattr(config, key) for key in SPEC}


class HistoriqueIn(BaseModel):
    delivered_orders: int = Field(0, ge=0)
    refused_orders: int = Field(0, ge=0)
    not_collected_orders: int = Field(0, ge=0)
    recent_failed_90d: int = Field(0, ge=0)
    distinct_shops: int = Field(0, ge=0)
    reports_count: int = Field(0, ge=0)


class AnalyseItem(BaseModel):
    customer_ref: str | None = None
    history: HistoriqueIn


class AnalyseLot(BaseModel):
    items: list[AnalyseItem] = Field(..., min_length=1, max_length=800)


def valeurs() -> dict:
    out = {}
    for key, (kind, _lo, _hi) in SPEC.items():
        value = getattr(config, key)
        out[key] = int(value) if kind == "int" else float(value)
    return out


def _autoriser(request: Request) -> None:
    expected = os.environ.get("TRUSTORDER_INTERNAL_TOKEN", "")
    if expected and request.headers.get("x-internal-token") != expected:
        raise HTTPException(401, "Jeton interne requis.")


def appliquer(payload: dict) -> dict:
    clean = {}
    for key, raw in payload.items():
        if key not in SPEC:
            raise HTTPException(422, f"Paramètre non autorisé : {key}")
        kind, lo, hi = SPEC[key]
        if isinstance(raw, bool):
            raise HTTPException(422, f"Valeur invalide pour {key}")
        try:
            if kind == "int":
                if isinstance(raw, float) and not raw.is_integer():
                    raise HTTPException(422, f"Valeur invalide pour {key}")
                value = int(raw)
            else:
                value = float(raw)
        except HTTPException:
            raise
        except (TypeError, ValueError):
            raise HTTPException(422, f"Valeur invalide pour {key}")
        if value < lo or value > hi:
            raise HTTPException(422, f"{key} hors limites ({lo}–{hi})")
        clean[key] = value
    merged = valeurs()
    merged.update(clean)
    if merged["SEUIL_FAIBLE_RISQUE"] < merged["SEUIL_RISQUE_MOYEN"]:
        raise HTTPException(422, "Le seuil LOW doit être supérieur ou égal au seuil MEDIUM.")
    if merged["SEUIL_PRIORITE_HAUTE"] < merged["SEUIL_PRIORITE_MOYENNE"]:
        raise HTTPException(422, "Le seuil de priorité haute doit être supérieur ou égal au seuil moyen.")
    poids = merged["POIDS_RISQUE"] + merged["POIDS_MONTANT"] + merged["POIDS_INCERTITUDE"]
    if abs(poids - 1) > 0.001:
        raise HTTPException(422, "La somme des poids de priorité doit rester égale à 1.")
    for key, value in clean.items():
        setattr(config, key, value)
    return clean


@router.get("/v1/settings")
def lire_reglages():
    current = valeurs()
    return {
        "values": current,
        "defaults": DEFAULTS,
        "overridden": current != {k: (int(v) if SPEC[k][0] == "int" else float(v)) for k, v in DEFAULTS.items()},
        "formulas_modified": False,
        "note": "Seules les constantes de config.py sont modifiables. scoring.py, moteur.py et ml.py restent inchangés.",
    }


@router.put("/v1/settings")
def ecrire_reglages(payload: dict, request: Request):
    _autoriser(request)
    appliquer(payload)
    return lire_reglages()


@router.post("/v1/settings/reset")
def reinitialiser(request: Request):
    _autoriser(request)
    for key, value in DEFAULTS.items():
        setattr(config, key, value)
    return lire_reglages()


@router.post("/v1/analyze/batch")
def analyser_lot(lot: AnalyseLot):
    results = []
    for item in lot.items:
        resultat = moteur.analyser_client(item.history.model_dump())
        resultat["customer_ref"] = item.customer_ref
        results.append(resultat)
    return {"results": results}
