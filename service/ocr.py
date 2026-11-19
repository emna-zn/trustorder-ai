"""
IMPORT PDF / IMAGE AVEC OCR (US07)
==================================
Un bordereau de livraison peut arriver sous trois formes :
  1) un PDF "texte"  -> on lit le texte directement (pas besoin d'OCR, c'est fiable)
  2) un PDF "scanné" -> on transforme chaque page en image puis on fait de l'OCR
  3) une photo / une image (png, jpg...) -> OCR

L'OCR (reconnaissance de texte sur une image) utilise le logiciel gratuit Tesseract, à installer séparément.
Sans Tesseract, les PDF "texte" fonctionnent quand même.

Ensuite, on cherche dans le texte les lignes qui contiennent un numéro de téléphone, et on y repère
le statut, le montant et la date. Chaque ligne reçoit une CONFIANCE (0 à 1) : en dessous de 0.8,
l'utilisateur doit la vérifier avec soin.
"""
import io
import os
import re

import config
import normalisation as nz
import telephone


class OcrIndisponible(Exception):
    """Tesseract (ou pytesseract) n'est pas installé."""


class ErreurDocument(Exception):
    """Le document ne peut pas être lu."""


EXTENSIONS_IMAGES = ("png", "jpg", "jpeg", "bmp", "tif", "tiff", "webp")


# ------------------------------------------------------------------ 1) LIRE LE TEXTE
def _ocr_image(image):
    try:
        import pytesseract
    except ImportError:
        raise OcrIndisponible("Le module pytesseract n'est pas installé (pip install pytesseract).")
    commande = os.environ.get("TESSERACT_CMD")            # chemin de tesseract.exe sous Windows, si besoin
    if commande:
        pytesseract.pytesseract.tesseract_cmd = commande
    try:
        try:
            return pytesseract.image_to_string(image, lang="fra+eng")
        except pytesseract.TesseractError:                # langue française non installée : on se contente de l'anglais
            return pytesseract.image_to_string(image, lang="eng")
    except pytesseract.TesseractNotFoundError:
        raise OcrIndisponible("Tesseract n'est pas installé sur ce poste. "
                              "Installez-le, ou importez un PDF contenant du texte, ou un fichier Excel/CSV.")


def _preparer_image(image):
    """Améliore l'image avant l'OCR : niveaux de gris, contraste, agrandissement si elle est petite."""
    from PIL import ImageOps
    image = ImageOps.autocontrast(image.convert("L"))
    if image.width < 1200:
        facteur = 2 if image.width >= 600 else 3
        image = image.resize((image.width * facteur, image.height * facteur))
    return image


def extraire_texte(contenu, nom_fichier):
    """Retourne (texte, methode). methode = 'texte_pdf', 'ocr_pdf' ou 'ocr_image'."""
    from PIL import Image
    extension = nom_fichier.lower().rsplit(".", 1)[-1] if "." in nom_fichier else ""

    if extension == "pdf" or contenu[:5] == b"%PDF-":
        try:
            import pymupdf
        except ImportError:
            import fitz as pymupdf
        try:
            pdf = pymupdf.open(stream=contenu, filetype="pdf")
        except Exception:
            raise ErreurDocument("PDF illisible ou corrompu.")
        morceaux, methode = [], "texte_pdf"
        for page in list(pdf)[:config.MAX_PAGES_PDF]:
            texte = page.get_text()
            if len(texte.strip()) >= 20:
                morceaux.append(texte)
            else:                                           # page scannée : pas de texte, on fait de l'OCR
                image = Image.open(io.BytesIO(page.get_pixmap(dpi=200).tobytes("png")))
                morceaux.append(_ocr_image(_preparer_image(image)))
                methode = "ocr_pdf"
        return "\n".join(morceaux), methode

    if extension in EXTENSIONS_IMAGES:
        try:
            image = Image.open(io.BytesIO(contenu))
            image.load()
        except Exception:
            raise ErreurDocument("Image illisible.")
        return _ocr_image(_preparer_image(image)), "ocr_image"

    raise ErreurDocument("Format non pris en charge. Utilisez un PDF ou une image (png, jpg...).")


# ------------------------------------------------------------------ 2) TROUVER LES COMMANDES DANS LE TEXTE
# Numéro tunisien : 8 chiffres (2 à 9 au début), avec ou sans espaces/points/tirets, avec ou sans +216.
RE_TEL = re.compile(r"(?<!\d)(?:(?:\+|00)?216[\s.\-]?)?"
                    r"([2-9]\d(?:[\s.\-]?\d{3}){2}|[2-9]\d(?:[\s.\-]?\d{2}){3})(?!\d)")
RE_DATE = re.compile(r"(?<!\d)(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{4}-\d{2}-\d{2})(?!\d)")
RE_MONTANT_DEVISE = re.compile(r"(\d{1,6}(?:[.,]\d{1,3})?)\s*(?:tnd|dt|dinars?)\b", re.IGNORECASE)
RE_MONTANT_DECIMAL = re.compile(r"(?<![\d.,])(\d{1,5}[.,]\d{3})(?![\d])")
RE_REFERENCE = re.compile(r"\b([A-Z]{2,6}[-_]?\d{3,10})\b")


def _chercher_telephone(ligne):
    sans_dates = RE_DATE.sub(lambda m: " " * len(m.group(0)), ligne)      # une date ne doit pas passer pour un numéro
    return RE_TEL.search(sans_dates)


def _analyser_enregistrement(principale, suite):
    """Extrait téléphone, statut, montant, date, référence d'une ligne (et des lignes suivantes si besoin)."""
    # 1) la date est retirée d'abord pour qu'elle ne soit pas confondue avec un numéro ou un montant
    date_trouvee = None
    m = RE_DATE.search(principale)
    if m:
        date_trouvee = m.group(1)
    sans_date = RE_DATE.sub(lambda mm: " " * len(mm.group(0)), principale)

    # 2) le téléphone
    mt = RE_TEL.search(sans_date)
    brut_tel = mt.group(0).strip()
    sans_tel = sans_date[:mt.start()] + " " * (mt.end() - mt.start()) + sans_date[mt.end():]

    # 3) montant, statut, référence : d'abord sur la ligne principale, puis sur les lignes suivantes
    def montant_dans(texte):
        m1 = RE_MONTANT_DEVISE.search(texte) or RE_MONTANT_DECIMAL.search(texte)
        return m1.group(1) if m1 else None

    montant = montant_dans(sans_tel)
    statut = nz.normaliser_statut(sans_tel)
    reference = (RE_REFERENCE.search(sans_tel) or [None, None])[1]
    for extra in suite:
        extra_sans_date = RE_DATE.sub(" ", extra)
        if montant is None:
            montant = montant_dans(extra_sans_date)
        if statut is None:
            statut = nz.normaliser_statut(extra_sans_date)
        if date_trouvee is None and RE_DATE.search(extra):
            date_trouvee = RE_DATE.search(extra).group(1)
        if reference is None:
            reference = (RE_REFERENCE.search(extra) or [None, None])[1]

    confiance = 0.5 + (0.2 if statut else 0) + (0.2 if montant else 0) + (0.1 if date_trouvee else 0)
    return {"phone": brut_tel, "status": statut or "", "amount": montant or "",
            "order_date": date_trouvee or "", "label": reference or "", "ignore": False,
            "confidence": round(confiance, 2), "source_text": principale[:200]}


def extraire_lignes(texte):
    """Retourne une ligne par numéro de téléphone trouvé dans le texte."""
    lignes = [l.strip() for l in texte.splitlines() if l.strip()]
    positions = [i for i, l in enumerate(lignes) if _chercher_telephone(l)]
    resultats = []
    for rang, i in enumerate(positions):
        limite = positions[rang + 1] if rang + 1 < len(positions) else len(lignes)
        # lignes qui suivent (3 au maximum), sans les lignes de total
        suite = [l for l in lignes[i + 1:min(limite, i + 4)] if "total" not in nz.nettoyer(l).split()]
        resultats.append(_analyser_enregistrement(lignes[i], suite))
    for numero, ligne in enumerate(resultats, start=1):
        ligne["line"] = numero
    return resultats


def importer_document(contenu, nom_fichier):
    """Point d'entrée : octets du PDF/image + nom -> (lignes, infos)."""
    texte, methode = extraire_texte(contenu, nom_fichier)
    lignes = extraire_lignes(texte)
    infos = {"method": methode, "text_length": len(texte.strip()),
             "uncertain_lines": sum(1 for l in lignes if l["confidence"] < config.CONFIANCE_OCR_MIN)}
    return lignes, infos
