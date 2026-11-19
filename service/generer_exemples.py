"""
Fabrique les fichiers d'exemple du dossier exemples/ :  python generer_exemples.py
  commandes_exemple.csv        : fichier "sale" (titres français, virgules décimales, doublon, erreurs...)
  commandes_exemple.xlsx       : le même type de données au format Excel (titres anglais)
  bordereau_exemple.pdf        : PDF contenant du texte (pas besoin d'OCR)
  bordereau_scan_exemple.png   : image à lire avec l'OCR (Tesseract)
  numeros_a_verifier.csv       : liste de numéros pour la vérification en masse
"""
import csv
import os
from datetime import date, timedelta

DOSSIER = "exemples"
aujourdhui = date.today()


def il_y_a(jours):
    return aujourdhui - timedelta(days=jours)


def lignes_commandes():
    """(téléphone, statut, montant, date, produit) — plusieurs clients avec des profils différents."""
    lignes = []
    # Client fiable : 6 commandes livrées
    for i, jours in enumerate([150, 120, 95, 70, 40, 12]):
        lignes.append(("98 111 222", "Livré", f"{40 + i * 5},500 DT", il_y_a(jours).strftime("%d/%m/%Y"), f"Robe {i + 1}"))
    # Client à risque : 1 livrée puis des refus récents
    lignes.append(("55 333 444", "Livré", "35,000", il_y_a(140).strftime("%d/%m/%Y"), "Sac"))
    for jours, statut in [(80, "Refusé"), (55, "Retour"), (30, "Injoignable"), (14, "Refusé"), (6, "Non récupéré")]:
        lignes.append(("55 333 444", statut, "120,000 DT", il_y_a(jours).strftime("%d/%m/%Y"), "Chaussures"))
    # Nouveau client : 3 commandes livrées (pas assez pour le ML)
    for jours in (60, 30, 5):
        lignes.append(("+216 22 123 456", "delivered", "29.9", il_y_a(jours).isoformat(), "Parfum"))
    # Lignes volontairement problématiques (pour montrer l'écran de vérification)
    lignes.append(("1234", "Livré", "50 DT", il_y_a(3).strftime("%d/%m/%Y"), "Numéro trop court"))
    lignes.append(("97 000 111", "annulé", "75 DT", il_y_a(4).strftime("%d/%m/%Y"), "Statut inconnu"))
    lignes.append(("97 000 222", "", "", "", "Ligne presque vide"))
    lignes.append(("98 111 222", "Livré", "65,500 DT", il_y_a(12).strftime("%d/%m/%Y"), "Robe 6"))   # doublon de la 6e ligne
    return lignes


def csv_commandes():
    with open(os.path.join(DOSSIER, "commandes_exemple.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["N° Tel", "Etat livraison", "Montant COD", "Date commande", "Produit"])
        w.writerows(lignes_commandes())


def excel_commandes():
    from openpyxl import Workbook
    classeur = Workbook()
    feuille = classeur.active
    feuille.append(["Phone", "Status", "Amount", "Created at", "Item"])
    for jours, statut, montant in [(50, "DELIVERED", 60.0), (35, "DELIVERED", 80.0), (20, "REFUSED", 150.0), (9, "Pending", 90.0)]:
        feuille.append([97123456, statut, montant, il_y_a(jours), f"Article {jours}"])      # vrai nombre + vraie date Excel
    classeur.save(os.path.join(DOSSIER, "commandes_exemple.xlsx"))


LIGNES_BORDEREAU = [
    "BORDEREAU DE LIVRAISON",
    "Ref Client Tel Montant Statut",
    "CMD-10234  Aya  22 123 456  45,500 DT  Livré",
    "CMD-10235  Karim  98 765 432  120,000 DT  Refusé",
    "CMD-10236  Sami  55 333 444  89,900 DT  Injoignable",
    "CMD-10237  Leila  97 456 789  64,000 DT  Livré",
    "Total : 319,400 DT",
]


def pdf_bordereau():
    import pymupdf
    pdf = pymupdf.open()
    page = pdf.new_page()
    for i, texte in enumerate(LIGNES_BORDEREAU):
        page.insert_text((50, 80 + 28 * i), texte, fontsize=12, fontname="helv")
    pdf.save(os.path.join(DOSSIER, "bordereau_exemple.pdf"))


def image_bordereau():
    from PIL import Image, ImageDraw, ImageFont
    police = None
    for nom in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            police = ImageFont.truetype(nom, 30)
            break
        except OSError:
            continue
    police = police or ImageFont.load_default()
    image = Image.new("RGB", (1500, 80 + 56 * len(LIGNES_BORDEREAU)), "white")
    dessin = ImageDraw.Draw(image)
    for i, texte in enumerate(LIGNES_BORDEREAU):
        dessin.text((40, 40 + 56 * i), texte, fill="black", font=police)
    image.save(os.path.join(DOSSIER, "bordereau_scan_exemple.png"))


def csv_numeros():
    with open(os.path.join(DOSSIER, "numeros_a_verifier.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Téléphone"])
        for n in ["98 111 222", "55 333 444", "+216 22 123 456", "20 999 888", "12345", "98111222"]:
            w.writerow([n])


if __name__ == "__main__":
    os.makedirs(DOSSIER, exist_ok=True)
    csv_commandes()
    excel_commandes()
    pdf_bordereau()
    image_bordereau()
    csv_numeros()
    print("Exemples créés dans le dossier", DOSSIER)
