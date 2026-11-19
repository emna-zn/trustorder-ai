"""
STOCKAGE ET AGRÉGATION (US09)
=============================
Base SQLite de démonstration (un simple fichier, aucune installation).
Dans le projet final, Symfony utilisera MySQL avec les MÊMES tables (voir sql_mysql.sql) et la même requête.

Trois tables :
  lots          : un import en cours de vérification (fichier ou OCR)
  commandes     : les commandes enregistrées après vérification
  signalements  : les signalements confirmés (gérés au Sprint 3, déjà pris en compte dans le score)

L'AGRÉGATION regroupe toutes les commandes d'un même numéro (toutes boutiques confondues) en un historique
prêt pour le moteur de scoring.
"""
import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from datetime import date, datetime, timedelta

import config
import normalisation as nz
import telephone

SCHEMA = """
CREATE TABLE IF NOT EXISTS lots (
    id TEXT PRIMARY KEY, boutique_id INTEGER NOT NULL, source TEXT NOT NULL, nom_fichier TEXT,
    cree_le TEXT NOT NULL, statut TEXT NOT NULL, infos TEXT NOT NULL, lignes TEXT NOT NULL, bilan TEXT);
CREATE TABLE IF NOT EXISTS commandes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, boutique_id INTEGER NOT NULL, telephone TEXT NOT NULL,
    telephone_hash TEXT NOT NULL, libelle TEXT, montant REAL, statut TEXT NOT NULL,
    date_commande TEXT NOT NULL, empreinte TEXT NOT NULL UNIQUE, lot_id TEXT);
CREATE INDEX IF NOT EXISTS idx_commandes_tel ON commandes(telephone_hash);
CREATE TABLE IF NOT EXISTS signalements (
    id INTEGER PRIMARY KEY AUTOINCREMENT, boutique_id INTEGER, telephone_hash TEXT NOT NULL,
    motif TEXT, statut TEXT NOT NULL DEFAULT 'EN_ATTENTE');
CREATE INDEX IF NOT EXISTS idx_signalements_tel ON signalements(telephone_hash);
"""

HISTORIQUE_VIDE = {"delivered_orders": 0, "refused_orders": 0, "not_collected_orders": 0,
                   "recent_failed_90d": 0, "distinct_shops": 0, "reports_count": 0}


class LotIntrouvable(Exception):
    pass


class LotDejaValide(Exception):
    pass


def connexion():
    con = sqlite3.connect(config.chemin_base())
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


# ------------------------------------------------------------------ LOTS (import en cours de vérification)
def creer_lot(boutique_id, source, nom_fichier, lignes, infos):
    lot_id = uuid.uuid4().hex[:12]
    with closing(connexion()) as con, con:
        con.execute("INSERT INTO lots (id, boutique_id, source, nom_fichier, cree_le, statut, infos, lignes) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (lot_id, boutique_id, source, nom_fichier, datetime.now().isoformat(timespec="seconds"),
                     "A_VERIFIER", json.dumps(infos), json.dumps(lignes)))
    return lot_id


def lire_lot(lot_id):
    with closing(connexion()) as con:
        r = con.execute("SELECT * FROM lots WHERE id=?", (lot_id,)).fetchone()
    if r is None:
        raise LotIntrouvable(lot_id)
    return {"id": r["id"], "shop_id": r["boutique_id"], "source": r["source"], "filename": r["nom_fichier"],
            "created_at": r["cree_le"], "status": r["statut"], "info": json.loads(r["infos"]),
            "lines": json.loads(r["lignes"]), "report": json.loads(r["bilan"]) if r["bilan"] else None}


def sauver_lignes(lot_id, lignes):
    with closing(connexion()) as con, con:
        con.execute("UPDATE lots SET lignes=? WHERE id=?", (json.dumps(lignes), lot_id))


def empreinte(boutique_id, tel_hash, jour, montant, libelle):
    """Identifiant unique d'une commande : permet de ne jamais enregistrer deux fois la même."""
    texte = f"{boutique_id}|{tel_hash}|{jour}|{montant}|{nz.nettoyer(libelle or '')}"
    return hashlib.sha256(texte.encode()).hexdigest()


def enregistrer_lot(lot_id):
    """Enregistre les lignes valides du lot dans la table commandes. Retourne le bilan."""
    lot = lire_lot(lot_id)
    if lot["status"] != "A_VERIFIER":
        raise LotDejaValide(lot_id)

    ajoutees = mises_a_jour = doublons = ignorees = 0
    rejetees = []
    with closing(connexion()) as con, con:
        for l in lot["lines"]:
            if l.get("ignore"):
                ignorees += 1
                continue
            if not l["valid"]:
                rejetees.append({"line": l["line"], "issues": [p["message"] for p in l["issues"] if p["level"] == "error"]})
                continue
            h = telephone.hacher(l["phone_normalized"])
            emp = empreinte(lot["shop_id"], h, l["date_value"], l["amount_value"], l.get("label"))
            existante = con.execute("SELECT id, statut FROM commandes WHERE empreinte=?", (emp,)).fetchone()
            if existante is None:
                con.execute("INSERT INTO commandes (boutique_id, telephone, telephone_hash, libelle, montant, statut, "
                            "date_commande, empreinte, lot_id) VALUES (?,?,?,?,?,?,?,?,?)",
                            (lot["shop_id"], l["phone_normalized"], h, l.get("label") or "", l["amount_value"],
                             l["status_normalized"], l["date_value"], emp, lot_id))
                ajoutees += 1
            elif existante["statut"] == "PENDING" and l["status_normalized"] != "PENDING":
                # la commande était "en attente" : on met à jour son issue (livrée, refusée...)
                con.execute("UPDATE commandes SET statut=? WHERE id=?", (l["status_normalized"], existante["id"]))
                mises_a_jour += 1
            else:
                doublons += 1
        bilan = {"inserted": ajoutees, "updated": mises_a_jour, "duplicates_ignored": doublons,
                 "ignored_by_user": ignorees, "rejected": rejetees}
        con.execute("UPDATE lots SET statut='VALIDE', bilan=? WHERE id=?", (json.dumps(bilan), lot_id))
    return bilan


# ------------------------------------------------------------------ AGRÉGATION PAR TÉLÉPHONE
def historique_par_telephone(hashes, aujourdhui=None):
    """
    Regroupe l'historique de plusieurs numéros (hachés) en UNE requête par paquet de 500.
    Retourne {hash: historique}. Un numéro sans aucune commande est absent du résultat.
    Les commandes "en attente" ne comptent pas comme issue (ni livrée, ni échec).
    """
    aujourdhui = aujourdhui or date.today()
    limite = (aujourdhui - timedelta(days=config.JOURS_ECHECS_RECENTS)).isoformat()
    hashes = list(dict.fromkeys(hashes))
    resultat = {}
    with closing(connexion()) as con:
        for debut in range(0, len(hashes), 500):
            paquet = hashes[debut:debut + 500]
            noms = ",".join(f":h{i}" for i in range(len(paquet)))
            params = {f"h{i}": h for i, h in enumerate(paquet)}
            params["limite"] = limite
            lignes = con.execute(f"""
                SELECT c.telephone_hash AS h,
                  SUM(CASE WHEN c.statut = 'DELIVERED' THEN 1 ELSE 0 END)     AS delivered_orders,
                  SUM(CASE WHEN c.statut = 'REFUSED' THEN 1 ELSE 0 END)       AS refused_orders,
                  SUM(CASE WHEN c.statut = 'NOT_COLLECTED' THEN 1 ELSE 0 END) AS not_collected_orders,
                  SUM(CASE WHEN c.statut IN ('REFUSED','NOT_COLLECTED') AND c.date_commande >= :limite
                           THEN 1 ELSE 0 END)                                 AS recent_failed_90d,
                  COUNT(DISTINCT c.boutique_id)                               AS distinct_shops,
                  COALESCE(MAX(r.nb), 0)                                      AS reports_count
                FROM commandes c
                LEFT JOIN (SELECT telephone_hash, COUNT(*) AS nb FROM signalements
                           WHERE statut = 'CONFIRME' AND telephone_hash IN ({noms})
                           GROUP BY telephone_hash) r ON r.telephone_hash = c.telephone_hash
                WHERE c.telephone_hash IN ({noms})
                GROUP BY c.telephone_hash""", params).fetchall()
            for r in lignes:
                resultat[r["h"]] = {k: int(r[k]) for k in HISTORIQUE_VIDE}
    return resultat


def commandes_de_boutique(boutique_id, tel_hash, limite=20):
    """Les dernières commandes de CETTE boutique pour ce numéro (les autres boutiques restent confidentielles)."""
    with closing(connexion()) as con:
        lignes = con.execute("SELECT date_commande, libelle, montant, statut FROM commandes "
                             "WHERE boutique_id=? AND telephone_hash=? ORDER BY date_commande DESC, id DESC LIMIT ?",
                             (boutique_id, tel_hash, limite)).fetchall()
    return [{"order_date": r["date_commande"], "label": r["libelle"], "amount": r["montant"], "status": r["statut"]}
            for r in lignes]
