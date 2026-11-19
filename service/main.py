"""
L'API (Sprints 1 et 2)
======================
Une API est une "porte" par laquelle Symfony envoie des données au service IA et reçoit une réponse.
Lancer :  uvicorn main:app --reload --port 8001      puis ouvrir  http://127.0.0.1:8001/docs
"""
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

import moteur
from routes_reglages import router as router_reglages
from routes_sprint2 import router as router_sprint2

app = FastAPI(title="TrustOrder AI - Sprints 1 et 2")
app.include_router(router_sprint2)          # toutes les routes /v2/... du Sprint 2
app.include_router(router_reglages)         # /v1/settings et /v1/analyze/batch (Sprint 3, formules inchangées)


# --- SPRINT 1 : les formes de données acceptées (FastAPI refuse automatiquement tout ce qui ne leur ressemble pas) ---
class Historique(BaseModel):
    delivered_orders: int = Field(0, ge=0)        # commandes récupérées   (ge=0 : pas de nombre négatif)
    refused_orders: int = Field(0, ge=0)          # commandes refusées
    not_collected_orders: int = Field(0, ge=0)    # commandes non récupérées
    recent_failed_90d: int = Field(0, ge=0)       # échecs des 90 derniers jours
    distinct_shops: int = Field(0, ge=0)          # nombre de boutiques différentes
    reports_count: int = Field(0, ge=0)           # signalements confirmés


class Commande(BaseModel):
    order_id: Optional[str] = None
    amount: float = Field(..., gt=0)              # montant en TND, obligatoire, supérieur à 0


class DemandeAnalyse(BaseModel):
    customer_ref: Optional[str] = None            # simple étiquette, renvoyée telle quelle
    history: Historique


class DemandePriorite(BaseModel):
    customer_ref: Optional[str] = None
    history: Historique
    order: Commande


class DemandeLot(BaseModel):
    items: list[DemandePriorite] = Field(..., min_length=1, max_length=500)


# --- SPRINT 1 : les "endpoints" (les adresses de l'API) ---
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/analyze")
def analyze(demande: DemandeAnalyse):
    resultat = moteur.analyser_client(demande.history.model_dump())
    resultat["customer_ref"] = demande.customer_ref
    return resultat


@app.post("/v1/prioritize")
def prioritize(demande: DemandePriorite):
    resultat = moteur.prioriser_commande(demande.history.model_dump(), demande.order.model_dump())
    resultat["customer_ref"] = demande.customer_ref
    return resultat


@app.post("/v1/prioritize/batch")
def prioritize_batch(lot: DemandeLot):
    resultats = []
    for item in lot.items:
        r = moteur.prioriser_commande(item.history.model_dump(), item.order.model_dump())
        r["customer_ref"] = item.customer_ref
        resultats.append(r)
    resultats.sort(key=lambda r: r["priority_score"], reverse=True)   # la plus prioritaire en premier
    return {"results": resultats}
