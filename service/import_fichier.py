"""
IMPORT EXCEL / CSV (US06)
=========================
Lit un fichier de commandes, retrouve TOUT SEUL quelle colonne contient le téléphone, le statut, le montant,
la date et le libellé (même si les titres sont écrits différemment), puis fabrique une liste de lignes
prêtes pour la vérification.
"""
import csv
import io
from datetime import date, datetime

import config
import normalisation as nz
import telephone


class ErreurImport(Exception):
    """Le fichier ne peut pas être lu (message lisible par l'utilisateur)."""


# Titres de colonnes reconnus (après nettoyage : minuscules, sans accents).
SYNONYMES = {
    "phone": ["telephone", "tel", "phone", "mobile", "gsm", "portable", "contact", "numero telephone",
              "n tel", "num tel", "client phone", "customer phone"],
    "status": ["statut", "status", "etat", "etat livraison", "statut livraison", "statut commande",
               "etat commande", "livraison", "resultat", "delivery status"],
    "amount": ["montant", "prix", "total", "cod", "amount", "price", "montant cod", "montant a encaisser"],
    "order_date": ["date", "date commande", "date de commande", "date creation", "created at", "created"],
    "label": ["libelle", "produit", "article", "designation", "description", "reference", "ref",
              "product", "item", "produits"],
}


def lire_tableau(contenu, nom_fichier):
    """Retourne la liste des lignes du fichier (chaque ligne = liste de cellules)."""
    extension = nom_fichier.lower().rsplit(".", 1)[-1] if "." in nom_fichier else ""
    if extension in ("csv", "txt", "tsv"):
        return _lire_csv(contenu)
    if extension in ("xlsx", "xlsm"):
        return _lire_excel(contenu)
    if extension == "xls":
        raise ErreurImport("Le format .xls n'est pas pris en charge : enregistrez le fichier en .xlsx ou en .csv.")
    raise ErreurImport("Format non pris en charge. Utilisez un fichier .csv ou .xlsx.")


def _lire_csv(contenu):
    for encodage in ("utf-8-sig", "cp1252"):
        try:
            texte = contenu.decode(encodage)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ErreurImport("Encodage du fichier CSV illisible.")
    echantillon = texte[:4096]
    try:
        separateur = csv.Sniffer().sniff(echantillon, delimiters=";,\t|").delimiter
    except csv.Error:
        separateur = ";" if echantillon.count(";") > echantillon.count(",") else ","
    return [list(ligne) for ligne in csv.reader(io.StringIO(texte), delimiter=separateur)]


def _lire_excel(contenu):
    from openpyxl import load_workbook
    try:
        classeur = load_workbook(io.BytesIO(contenu), read_only=True, data_only=True)
    except Exception:
        raise ErreurImport("Fichier Excel illisible ou corrompu.")
    return [list(ligne) for ligne in classeur.active.iter_rows(values_only=True)]


def _vide(cellule):
    return cellule is None or str(cellule).strip() == ""


def _en_texte(cellule):
    """Convertit une cellule en texte simple (les dates Excel deviennent AAAA-MM-JJ)."""
    if cellule is None:
        return ""
    if isinstance(cellule, datetime):
        return cellule.date().isoformat()
    if isinstance(cellule, date):
        return cellule.isoformat()
    if isinstance(cellule, float) and cellule.is_integer():
        return str(int(cellule))
    return str(cellule).strip()


def detecter_colonnes(entetes, lignes_donnees):
    """Associe chaque champ (phone, status...) à la colonne qui lui correspond. Retourne {champ: index}."""
    propres = [nz.nettoyer(e) if not _vide(e) else "" for e in entetes]
    candidats = []                                    # (score, champ, index de colonne)
    for champ, synonymes in SYNONYMES.items():
        for i, titre in enumerate(propres):
            if not titre:
                continue
            for syn in synonymes:
                if titre == syn:
                    candidats.append((100, champ, i))
                elif f" {syn} " in f" {titre} ":
                    candidats.append((len(syn), champ, i))
    colonnes, champs_pris, index_pris = {}, set(), set()
    for score, champ, i in sorted(candidats, key=lambda c: -c[0]):
        if champ not in champs_pris and i not in index_pris:
            colonnes[champ] = i
            champs_pris.add(champ)
            index_pris.add(i)

    # Plan B pour le téléphone : la colonne dont la plupart des valeurs ressemblent à un numéro
    if "phone" not in colonnes:
        meilleur, meilleur_taux = None, 0.5
        for i in range(len(entetes)):
            if i in index_pris:
                continue
            valeurs = [l[i] for l in lignes_donnees[:50] if i < len(l) and not _vide(l[i])]
            if valeurs:
                taux = sum(1 for v in valeurs if telephone.normaliser(v)) / len(valeurs)
                if taux > meilleur_taux:
                    meilleur, meilleur_taux = i, taux
        if meilleur is not None:
            colonnes["phone"] = meilleur
    return colonnes


def importer_tableau(tableau):
    """Transforme le tableau brut en lignes à vérifier. Retourne (lignes, infos)."""
    tableau = [l for l in tableau if any(not _vide(c) for c in l)]       # on enlève les lignes vides
    if len(tableau) < 2:
        raise ErreurImport("Le fichier est vide ou ne contient pas de ligne de données.")
    if len(tableau) - 1 > config.MAX_LIGNES_IMPORT:
        raise ErreurImport(f"Trop de lignes : {config.MAX_LIGNES_IMPORT} maximum par fichier.")

    entetes, donnees = tableau[0], tableau[1:]
    colonnes = detecter_colonnes(entetes, donnees)
    if "phone" not in colonnes:
        raise ErreurImport("Colonne du numéro de téléphone introuvable. "
                           "Ajoutez un titre de colonne comme « Téléphone » ou « Mobile ».")

    lignes = []
    for numero, cellules in enumerate(donnees, start=1):
        def valeur(champ):
            i = colonnes.get(champ)
            return _en_texte(cellules[i]) if i is not None and i < len(cellules) else ""
        lignes.append({"line": numero, "phone": valeur("phone"), "status": valeur("status"),
                       "amount": valeur("amount"), "order_date": valeur("order_date"),
                       "label": valeur("label"), "ignore": False})

    infos = {"detected_columns": {champ: _en_texte(entetes[i]) for champ, i in colonnes.items()},
             "ignored_columns": [_en_texte(e) for i, e in enumerate(entetes)
                                 if i not in colonnes.values() and not _vide(e)]}
    return lignes, infos


def importer_fichier(contenu, nom_fichier):
    """Point d'entrée : octets du fichier + nom -> (lignes, infos)."""
    return importer_tableau(lire_tableau(contenu, nom_fichier))
