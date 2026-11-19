"""
API DU SPRINT 2
===============
Parcours complet d'un import :

  1. POST  /v2/import/fichier  ou  /v2/import/document   -> crée un LOT et renvoie les lignes à vérifier
  2. GET   /v2/lots/{lot_id}                             -> relire le lot
  3. PATCH /v2/lots/{lot_id}/lignes/{n}                  -> corriger (ou ignorer) une ligne
  4. POST  /v2/lots/{lot_id}/valider                     -> enregistrer les lignes valides en base
  5. GET   /v2/clients?telephone=...                     -> historique + analyse d'un numéro
  6. POST  /v2/verification/masse (+ /fichier)           -> analyser une liste de numéros
"""
from typing import Optional, Union

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

import clients
import config
import import_fichier
import ocr
import stockage
import telephone
import verification

router = APIRouter(prefix="/v2")


# ------------------------------------------------------------------ outils
def _lot_vers_reponse(lot):
    return {"lot_id": lot["id"], "shop_id": lot["shop_id"], "source": lot["source"], "filename": lot["filename"],
            "status": lot["status"], "info": lot["info"], "summary": verification.resume(lot["lines"]),
            "report": lot["report"], "lines": lot["lines"]}


async def _lire_upload(fichier):
    contenu = await fichier.read()
    if len(contenu) > config.TAILLE_MAX_FICHIER:
        raise HTTPException(413, f"Fichier trop volumineux ({config.TAILLE_MAX_FICHIER // (1024 * 1024)} Mo maximum).")
    if not contenu:
        raise HTTPException(422, "Le fichier est vide.")
    return contenu


def _lot_ou_404(lot_id):
    try:
        return stockage.lire_lot(lot_id)
    except stockage.LotIntrouvable:
        raise HTTPException(404, "Lot introuvable.")


# ------------------------------------------------------------------ 1) IMPORTS
@router.post("/import/fichier")
async def importer_un_fichier(boutique_id: int = Form(...), fichier: UploadFile = File(...)):
    """US06 — Importe un fichier Excel (.xlsx) ou CSV et prépare la vérification."""
    contenu = await _lire_upload(fichier)
    try:
        lignes, infos = import_fichier.importer_fichier(contenu, fichier.filename or "")
    except import_fichier.ErreurImport as e:
        raise HTTPException(422, str(e))
    verification.valider_lot(lignes)
    lot_id = stockage.creer_lot(boutique_id, "FILE", fichier.filename, lignes, infos)
    return _lot_vers_reponse(stockage.lire_lot(lot_id))


@router.post("/import/document")
async def importer_un_document(boutique_id: int = Form(...), fichier: UploadFile = File(...)):
    """US07 — Importe un PDF ou une image (OCR) et prépare la vérification."""
    contenu = await _lire_upload(fichier)
    try:
        lignes, infos = ocr.importer_document(contenu, fichier.filename or "")
    except ocr.OcrIndisponible as e:
        raise HTTPException(503, str(e))
    except ocr.ErreurDocument as e:
        raise HTTPException(422, str(e))
    if not lignes:
        raise HTTPException(422, "Aucun numéro de téléphone trouvé dans le document.")
    verification.valider_lot(lignes)
    for ligne in lignes:        # une extraction incertaine doit être regardée de près
        if ligne["confidence"] < config.CONFIANCE_OCR_MIN:
            ligne["issues"].append({"level": "warning", "field": "line",
                                    "message": f"Extraction incertaine (confiance {ligne['confidence']:.0%}) : vérifiez cette ligne."})
    lot_id = stockage.creer_lot(boutique_id, "OCR", fichier.filename, lignes, infos)
    return _lot_vers_reponse(stockage.lire_lot(lot_id))


# ------------------------------------------------------------------ 2) VÉRIFICATION (US08)
class CorrectionLigne(BaseModel):
    phone: Optional[str] = None
    status: Optional[str] = None
    amount: Union[float, str, None] = None
    order_date: Optional[str] = None
    label: Optional[str] = None
    ignore: Optional[bool] = None


@router.get("/lots/{lot_id}")
def lire_un_lot(lot_id: str):
    return _lot_vers_reponse(_lot_ou_404(lot_id))


@router.patch("/lots/{lot_id}/lignes/{numero}")
def corriger_une_ligne(lot_id: str, numero: int, correction: CorrectionLigne):
    """US08 — Corrige une ligne (seuls les champs envoyés changent) puis recontrôle tout le lot."""
    lot = _lot_ou_404(lot_id)
    if lot["status"] != "A_VERIFIER":
        raise HTTPException(409, "Ce lot est déjà validé : il ne peut plus être modifié.")
    cible = next((l for l in lot["lines"] if l["line"] == numero), None)
    if cible is None:
        raise HTTPException(404, "Ligne introuvable.")
    for champ, valeur in correction.model_dump(exclude_unset=True).items():
        cible[champ] = "" if valeur is None and champ != "ignore" else valeur
    verification.valider_lot(lot["lines"])
    stockage.sauver_lignes(lot_id, lot["lines"])
    return _lot_vers_reponse(stockage.lire_lot(lot_id))


@router.post("/lots/{lot_id}/valider")
def valider_un_lot(lot_id: str):
    """US08 — Enregistre en base les lignes valides. Les lignes en erreur ou ignorées ne sont pas enregistrées."""
    try:
        bilan = stockage.enregistrer_lot(lot_id)
    except stockage.LotIntrouvable:
        raise HTTPException(404, "Lot introuvable.")
    except stockage.LotDejaValide:
        raise HTTPException(409, "Ce lot a déjà été validé.")
    return {"lot_id": lot_id, "status": "VALIDE", "report": bilan}


# ------------------------------------------------------------------ 3) RECHERCHE (US09)
@router.get("/clients")
def chercher_un_client(telephone: str = Query(..., description="Numéro à rechercher"),
                       boutique_id: Optional[int] = Query(None, description="Pour voir aussi les commandes de cette boutique")):
    try:
        return clients.rechercher_client(telephone, boutique_id)
    except ValueError as e:
        raise HTTPException(422, str(e))


# ------------------------------------------------------------------ 4) VÉRIFICATION EN MASSE (US10)
class DemandeMasse(BaseModel):
    phones: list[str] = Field(..., min_length=1, max_length=config.MAX_NUMEROS_MASSE)


@router.post("/verification/masse")
def verification_en_masse(demande: DemandeMasse, format: str = Query("json", pattern="^(json|csv)$")):
    sortie = clients.verifier_en_masse(demande.phones)
    if format == "csv":
        return Response(clients.vers_csv(sortie["results"]), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=verification.csv"})
    return sortie


@router.post("/verification/masse/fichier")
async def verification_en_masse_fichier(fichier: UploadFile = File(...), format: str = Query("json", pattern="^(json|csv)$")):
    """Envoie un fichier .csv ou .xlsx contenant une colonne de numéros (avec ou sans ligne de titres)."""
    contenu = await _lire_upload(fichier)
    try:
        tableau = import_fichier.lire_tableau(contenu, fichier.filename or "")
        tableau = [l for l in tableau if any(c is not None and str(c).strip() for c in l)]
        if not tableau:
            raise import_fichier.ErreurImport("Le fichier est vide.")
        a_des_titres = not any(telephone.normaliser(c) for c in tableau[0] if c is not None)
        if a_des_titres:                                         # première ligne = titres de colonnes
            colonnes = import_fichier.detecter_colonnes(tableau[0], tableau[1:])
            if "phone" not in colonnes:
                raise import_fichier.ErreurImport("Colonne du numéro de téléphone introuvable.")
            col, lignes = colonnes["phone"], tableau[1:]
        else:                                                    # pas de titres : numéros dans la première colonne
            col, lignes = 0, tableau
        numeros = [import_fichier._en_texte(l[col]) for l in lignes if col < len(l)]
    except import_fichier.ErreurImport as e:
        raise HTTPException(422, str(e))
    numeros = [n for n in numeros if n]
    if not numeros:
        raise HTTPException(422, "Aucun numéro trouvé dans le fichier.")
    try:
        sortie = clients.verifier_en_masse(numeros)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if format == "csv":
        return Response(clients.vers_csv(sortie["results"]), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=verification.csv"})
    return sortie


def extraire_numeros(contenu: bytes, filename: str) -> list[str]:
    """Lit une colonne de téléphones. Ne calcule aucun score."""
    tableau = import_fichier.lire_tableau(contenu, filename)
    tableau = [ligne for ligne in tableau if any(c is not None and str(c).strip() for c in ligne)]
    if not tableau:
        raise import_fichier.ErreurImport("Le fichier est vide.")
    a_des_titres = not any(telephone.normaliser(c) for c in tableau[0] if c is not None)
    if a_des_titres:
        colonnes = import_fichier.detecter_colonnes(tableau[0], tableau[1:])
        if "phone" not in colonnes:
            raise import_fichier.ErreurImport("Colonne du numéro de téléphone introuvable.")
        col, lignes = colonnes["phone"], tableau[1:]
    else:
        col, lignes = 0, tableau
    return [n for n in (import_fichier._en_texte(l[col]) for l in lignes if col < len(l)) if n]


@router.post("/outils/numeros")
async def lire_numeros(fichier: UploadFile = File(...)):
    """Extraction seule, pour que Symfony score ensuite sur MySQL et non sur le SQLite du service."""
    contenu = await _lire_upload(fichier)
    try:
        numeros = extraire_numeros(contenu, fichier.filename or "liste.csv")
    except import_fichier.ErreurImport as e:
        raise HTTPException(422, str(e))
    if not numeros:
        raise HTTPException(422, "Aucun numéro trouvé dans le fichier.")
    if len(numeros) > config.MAX_NUMEROS_MASSE:
        raise HTTPException(422, f"{config.MAX_NUMEROS_MASSE} numéros maximum.")
    return {"phones": numeros}
