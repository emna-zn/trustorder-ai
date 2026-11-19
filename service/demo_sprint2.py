"""
DÉMO DU SPRINT 2 SANS SERVEUR :  python demo_sprint2.py
Déroule tout le parcours sur les fichiers du dossier exemples/ :
  import -> vérification -> correction -> enregistrement -> recherche -> vérification en masse
"""
import os

os.environ["TRUSTORDER_DB"] = "demo_sprint2.db"          # base de démonstration, recréée à chaque lancement
if os.path.exists("demo_sprint2.db"):
    os.remove("demo_sprint2.db")

import clients
import import_fichier
import ocr
import stockage
import verification


def titre(texte):
    print("\n" + "=" * 70 + "\n" + texte + "\n" + "=" * 70)


# ---------------------------------------------------------------- 1. IMPORT D'UN FICHIER CSV
titre("1. Import du fichier exemples/commandes_exemple.csv (US06)")
contenu = open("exemples/commandes_exemple.csv", "rb").read()
lignes, infos = import_fichier.importer_fichier(contenu, "commandes_exemple.csv")
print("Colonnes retrouvées automatiquement :", infos["detected_columns"])
verification.valider_lot(lignes)
print("Résumé :", verification.resume(lignes))

# ---------------------------------------------------------------- 2. VÉRIFICATION
titre("2. Écran de vérification : lignes à regarder (US08)")
for l in lignes:
    if l["issues"]:
        for p in l["issues"]:
            print(f"  ligne {l['line']:>2} [{'ERREUR' if p['level'] == 'error' else 'avert.'}] {p['message']}")

# ---------------------------------------------------------------- 3. CORRECTION
titre("3. Correction : on répare le numéro trop court et on ignore la ligne au statut inconnu")
for l in lignes:
    if l["phone"] == "1234":
        l["phone"] = "20 444 555"                          # l'utilisateur corrige le numéro
    if l["status"] == "annulé":
        l["ignore"] = True                                 # l'utilisateur ignore cette ligne
verification.valider_lot(lignes)
print("Résumé après correction :", verification.resume(lignes))

lot_id = stockage.creer_lot(1, "FILE", "commandes_exemple.csv", lignes, infos)
bilan = stockage.enregistrer_lot(lot_id)
print("Enregistrement en base :", {k: v for k, v in bilan.items() if k != "rejected"}, "| rejetées :", len(bilan["rejected"]))

# ---------------------------------------------------------------- 4. IMPORT D'UN BORDEREAU (PDF)
titre("4. Import d'un bordereau PDF (US07) — lecture du texte, sans OCR")
lignes_pdf, infos_pdf = ocr.importer_document(open("exemples/bordereau_exemple.pdf", "rb").read(), "bordereau_exemple.pdf")
verification.valider_lot(lignes_pdf)
print("Méthode :", infos_pdf["method"])
for l in lignes_pdf:
    print(f"  {l['phone']:<14} {l['status_normalized']:<14} {l['amount']:>8} TND   confiance {l['confidence']:.0%}")
stockage.enregistrer_lot(stockage.creer_lot(2, "OCR", "bordereau_exemple.pdf", lignes_pdf, infos_pdf))

# ---------------------------------------------------------------- 5. RECHERCHE
titre("5. Recherche d'un numéro (US09) : historique agrégé de toutes les boutiques")
for numero in ("98 111 222", "55 333 444", "20 999 888"):
    r = clients.rechercher_client(numero)
    h, a = r["history"], r["analysis"]
    if not r["known_customer"]:
        print(f"  {numero} : client inconnu (aucune commande enregistrée)")
        continue
    print(f"  {numero} : {h['delivered_orders']} livrées, {h['refused_orders'] + h['not_collected_orders']} échecs "
          f"({h['recent_failed_90d']} récents), {h['distinct_shops']} boutique(s)"
          f" -> score {a['score']}/100, risque {a['risk_level']}, cold start : {a['cold_start']}")

# ---------------------------------------------------------------- 6. VÉRIFICATION EN MASSE
titre("6. Vérification en masse d'une liste de numéros (US10)")
numeros = ["98 111 222", "55 333 444", "+216 22 123 456", "20 999 888", "12345"]
sortie = clients.verifier_en_masse(numeros)
for r in sortie["results"]:
    print(f"  {r['input']:<16} {r['result_type']:<17} score {str(r['score']):<5} risque {str(r['risk_level']):<8} {r['recommendation']}")
print("Résumé :", sortie["summary"])
print("\nBase de démonstration : demo_sprint2.db (supprimez ce fichier pour repartir de zéro)")
