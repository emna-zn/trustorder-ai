"""
Jeu de données fictif tunisien pour la démo web.
Les scores ne sont PAS stockés : le moteur Python les recalcule à la lecture.
"""
from __future__ import annotations

import hashlib
import os
import random
import sqlite3
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = os.path.join(ROOT, "service")
if SERVICE not in sys.path:
    sys.path.insert(0, SERVICE)

import telephone  # noqa: E402

SEED = 20261118
DB_PATH = os.path.join(ROOT, "data", "demo.db")

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE boutique (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    governorate TEXT NOT NULL,
    city TEXT NOT NULL,
    address TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL,
    boutique_id INTEGER,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE customer (
    id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    phone_normalized TEXT NOT NULL UNIQUE,
    phone_hash TEXT NOT NULL UNIQUE,
    phone_mask TEXT NOT NULL,
    governorate TEXT NOT NULL,
    city TEXT NOT NULL
);
CREATE TABLE customer_order (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    boutique_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    phone_hash TEXT NOT NULL,
    label TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT NOT NULL,
    order_date TEXT NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_order_phone ON customer_order(phone_hash, status, order_date);
CREATE INDEX idx_order_shop ON customer_order(boutique_id, order_date);
CREATE TABLE complaint (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    boutique_id INTEGER NOT NULL,
    phone_hash TEXT NOT NULL,
    phone_mask TEXT NOT NULL,
    motif TEXT NOT NULL,
    status TEXT NOT NULL,
    admin_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE contestation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    boutique_id INTEGER NOT NULL,
    phone_hash TEXT NOT NULL,
    phone_mask TEXT NOT NULL,
    motif TEXT NOT NULL,
    status TEXT NOT NULL,
    decision_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_email TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE analysis_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    boutique_id INTEGER,
    actor_email TEXT NOT NULL,
    phone_mask TEXT NOT NULL,
    phone_hash TEXT NOT NULL,
    kind TEXT NOT NULL,
    score INTEGER,
    risk_level TEXT,
    priority TEXT,
    cold_start INTEGER NOT NULL,
    retention_probability REAL,
    prediction_source TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE import_lot (
    id TEXT PRIMARY KEY,
    boutique_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    filename TEXT NOT NULL,
    status TEXT NOT NULL,
    info_json TEXT NOT NULL,
    lines_json TEXT NOT NULL,
    report_json TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE score_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

FIRST = [
    "Emna", "Sarra", "Rania", "Chaima", "Inès", "Nour", "Mariem", "Yasmine", "Ons", "Farah",
    "Amina", "Hiba", "Lina", "Eya", "Sirine", "Yassine", "Omar", "Ahmed", "Mohamed", "Amine",
    "Sami", "Khaled", "Aziz", "Wassim", "Hamza", "Mehdi", "Bilel", "Anis", "Fares", "Skander",
    "Ayoub", "Malek", "Houssem", "Wael", "Zied", "Nizar", "Tarek", "Hatem", "Rami", "Ilyes",
]
LAST = [
    "Ben Salah", "Trabelsi", "Ben Ali", "Gharbi", "Bouzid", "Khemiri", "Louati", "Aouadi",
    "Mansouri", "Jaziri", "Ben Salem", "Chaabane", "Mejri", "Dridi", "Hamdi", "Saidi",
    "Ben Youssef", "Guizani", "Rekik", "Kammoun", "Bouazizi", "Haddad", "Cherif", "Masmoudi",
    "Ben Amor", "Ferchichi", "Oueslati", "Baccar", "Elloumi", "Khelifi",
]
BOUTIQUES = [
    ("Maison Emna", "Tunis", "Tunis", "12 rue de Marseille, Tunis"),
    ("Carthage Electro", "Ariana", "Ariana", "Centre Tunis City, Ariana"),
    ("Sfax Market", "Sfax", "Sfax Ville", "Rue de la République, Sfax"),
    ("Sousse Style", "Sousse", "Sousse Médina", "Avenue Habib Bourguiba, Sousse"),
    ("Monastir Shop", "Monastir", "Monastir", "Rue de l'Indépendance, Monastir"),
    ("Mahdia Perles", "Mahdia", "Mahdia", "Corniche, Mahdia"),
    ("Nabeul Atelier", "Nabeul", "Nabeul", "Avenue Habib Thameur, Nabeul"),
    ("Bizerte Nord", "Bizerte", "Bizerte", "Quai Trak Ibn Ziad, Bizerte"),
    ("Kairouan Medina", "Kairouan", "Kairouan", "Rue des Aghlabites, Kairouan"),
    ("Gabès Oasis", "Gabès", "Gabès", "Avenue Farhat Hached, Gabès"),
    ("Djerba Soleil", "Médenine", "Houmt Souk", "Route touristique, Djerba"),
    ("Kasserine Atlas", "Kasserine", "Kasserine", "Avenue de l'Environnement, Kasserine"),
    ("Gafsa Minerale", "Gafsa", "Gafsa", "Rue Mohamed Ali, Gafsa"),
    ("Tozeur Palmeraie", "Tozeur", "Tozeur", "Avenue Abou el Kacem Chebbi, Tozeur"),
    ("Jendouba Verte", "Jendouba", "Jendouba", "Avenue Habib Bourguiba, Jendouba"),
    ("Zaghouan Source", "Zaghouan", "Zaghouan", "Rue de la Source, Zaghouan"),
]
PLACES = {
    "Tunis": ["Tunis", "La Marsa", "Le Bardo", "Carthage", "La Goulette", "El Menzah"],
    "Ariana": ["Ariana", "La Soukra", "Raoued", "Ettadhamen"],
    "Ben Arous": ["Ben Arous", "Ezzahra", "Radès", "Hammam Lif", "Mohamedia"],
    "Manouba": ["Manouba", "Den Den", "Oued Ellil"],
    "Nabeul": ["Nabeul", "Hammamet", "Kélibia", "Dar Chaâbane"],
    "Bizerte": ["Bizerte", "Menzel Bourguiba", "Mateur"],
    "Béja": ["Béja", "Medjez el-Bab"],
    "Jendouba": ["Jendouba", "Tabarka", "Aïn Draham"],
    "Le Kef": ["Le Kef", "Dahmani"],
    "Siliana": ["Siliana", "Makthar"],
    "Sousse": ["Sousse", "Msaken", "Kalâa Kebira", "Hammam Sousse"],
    "Monastir": ["Monastir", "Moknine", "Jemmal"],
    "Mahdia": ["Mahdia", "Ksour Essef", "El Jem"],
    "Sfax": ["Sfax", "Sakiet Ezzit", "Mahres"],
    "Kairouan": ["Kairouan", "Haffouz", "Oueslatia"],
    "Kasserine": ["Kasserine", "Sbeitla", "Fériana"],
    "Sidi Bouzid": ["Sidi Bouzid", "Menzel Bouzaiane"],
    "Gabès": ["Gabès", "El Hamma", "Mareth"],
    "Médenine": ["Médenine", "Houmt Souk", "Zarzis", "Ben Gardane"],
    "Tataouine": ["Tataouine", "Ghomrassen"],
    "Gafsa": ["Gafsa", "Métlaoui", "Redeyef"],
    "Tozeur": ["Tozeur", "Nefta", "Degache"],
    "Kébili": ["Kébili", "Douz"],
    "Zaghouan": ["Zaghouan", "El Fahs"],
}
PRODUCTS = [
    ("Enceinte Bluetooth JBL Flip 6", 189, 279),
    ("Écouteurs sans fil", 49, 129),
    ("Powerbank 20000mAh Xiaomi", 55, 89),
    ("Hub USB-C 7-en-1", 62, 110),
    ("Montre connectée", 220, 690),
    ("Coque téléphone", 12, 35),
    ("Robe lin", 45, 120),
    ("Sac cabas", 70, 160),
    ("Parfum 50 ml", 29, 95),
    ("Huile d'olive 3L", 38, 62),
    ("Dattes Deglet Nour 1 kg", 16, 28),
    ("Chaussures de sport", 90, 210),
    ("Fouta de plage", 22, 48),
    ("Mixeur", 85, 190),
    ("Cafetière", 40, 95),
    ("Pack couches", 36, 68),
    ("Crème solaire", 18, 42),
    ("Tapis artisanal", 140, 320),
    ("Hijab soie", 28, 75),
    ("Chargeur rapide 30W", 19, 45),
]
PREFIXES = ["20", "21", "22", "23", "24", "25", "26", "27", "28", "29",
            "40", "41", "50", "52", "53", "54", "55", "58", "90", "92", "93", "94", "95", "96", "97", "98", "99"]
MOTIFS_SIGNALEMENT = [
    "Refus répété après confirmation téléphonique",
    "Numéro injoignable à plusieurs reprises",
    "Commande non récupérée au point relais",
    "Adresse de livraison introuvable",
    "Client ayant contesté le montant à la livraison",
]
MOTIFS_CONTESTATION = [
    "Le client indique que la commande a bien été livrée",
    "Numéro partagé au sein de la famille, historique mélangé",
    "Refus enregistré alors que le colis est revenu pour une erreur d'adresse boutique",
    "Le client demande la correction d'un statut « non récupéré »",
]


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return salt.hex() + "$" + dk.hex()


def mask_phone(normalized: str) -> str:
    local = normalized[3:]
    return f"+216 {local[:2]} *** {local[-3:]}"


def fingerprint(boutique_id, phone_hash, day, amount, label) -> str:
    raw = f"{boutique_id}|{phone_hash}|{day}|{amount}|{label.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def archetype_of(index: int) -> str:
    r = index % 20
    if r < 8:
        return "RELIABLE"
    if r < 13:
        return "MEDIUM"
    if r < 17:
        return "HIGH"
    return "COLD"


def build(path: str = DB_PATH) -> dict:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    rng = random.Random(SEED)
    today = date.today()
    start = date(2025, 1, 8)
    span = max(30, (today - start).days)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    now = today.isoformat() + "T09:00:00"

    for i, (name, gov, city, address) in enumerate(BOUTIQUES, start=1):
        con.execute(
            "INSERT INTO boutique (id, name, governorate, city, address, active, created_at) VALUES (?,?,?,?,?,1,?)",
            (i, name, gov, city, address, "2025-01-06T10:00:00"),
        )
    con.execute(
        "INSERT INTO users (id, email, password, full_name, role, boutique_id, active) VALUES (?,?,?,?,?,?,1)",
        (1, "admin@trustorder.tn", hash_password("Admin2026!", b"trustorder-admin-01"),
         "Sami Khelifi", "ADMIN", None),
    )
    con.execute(
        "INSERT INTO users (id, email, password, full_name, role, boutique_id, active) VALUES (?,?,?,?,?,?,1)",
        (2, "ines.chaabane@trustorder.tn", hash_password("Admin2026!", b"trustorder-admin-02"),
         "Inès Chaabane", "ADMIN", None),
    )
    shop_users = []
    for i, (name, gov, city, _addr) in enumerate(BOUTIQUES, start=1):
        if i == 1:
            full, email = "Emna Ben Salah", "emna.bensalah@maison-emna.tn"
        else:
            full = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            slug = name.lower().replace(" ", "-").replace("è", "e").replace("é", "e")
            email = f"contact@{slug}.tn"
        uid = i + 2
        con.execute(
            "INSERT INTO users (id, email, password, full_name, role, boutique_id, active) VALUES (?,?,?,?,?,?,1)",
            (uid, email, hash_password("Boutique2026!", f"shop-salt-{i:02d}".encode()), full, "SHOP", i),
        )
        shop_users.append(uid)

    govs = list(PLACES)
    customers = []
    used_phones = set()
    for i in range(1, 701):
        full = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        while True:
            local = rng.choice(PREFIXES) + "".join(str(rng.randint(0, 9)) for _ in range(6))
            phone = "216" + local
            if phone not in used_phones and telephone.normaliser(phone):
                used_phones.add(phone)
                break
        primary = ((i - 1) % len(BOUTIQUES)) + 1
        gov = BOUTIQUES[primary - 1][1] if rng.random() < 0.8 else rng.choice(govs)
        city = rng.choice(PLACES[gov])
        digest = telephone.hacher(phone)
        con.execute(
            "INSERT INTO customer (id, full_name, phone_normalized, phone_hash, phone_mask, governorate, city) VALUES (?,?,?,?,?,?,?)",
            (i, full, phone, digest, mask_phone(phone), gov, city),
        )
        customers.append({"id": i, "phone": phone, "hash": digest, "mask": mask_phone(phone),
                          "shop": primary, "arch": archetype_of(i - 1), "name": full})

    orders = []
    oid_preview = 1
    for c in customers:
        arch = c["arch"]
        if arch == "RELIABLE":
            n = rng.randint(8, 15)
            statuses = ["DELIVERED" if rng.random() < 0.93 else "REFUSED" for _ in range(n)]
        elif arch == "MEDIUM":
            n = rng.randint(6, 10)
            statuses = [rng.choice(["DELIVERED", "DELIVERED", "DELIVERED", "REFUSED", "NOT_COLLECTED"]) for _ in range(n)]
        elif arch == "HIGH":
            n = rng.randint(6, 11)
            statuses = [rng.choice(["REFUSED", "NOT_COLLECTED", "REFUSED", "DELIVERED"]) for _ in range(n)]
        else:
            n = rng.randint(1, 4)
            statuses = [rng.choice(["DELIVERED", "REFUSED", "DELIVERED", "NOT_COLLECTED"]) for _ in range(n)]
        dates = sorted(start + timedelta(days=rng.randint(0, max(1, span - 20))) for _ in range(n))
        if arch == "RELIABLE":
            # échecs placés au début de l'historique (anciens)
            fail_idx = [k for k, s in enumerate(statuses) if s != "DELIVERED"]
            for k in fail_idx:
                dates[k] = start + timedelta(days=rng.randint(0, 80))
            dates = sorted(dates)
        if arch == "HIGH":
            recent_n = min(4, n)
            for k in range(n - recent_n, n):
                statuses[k] = rng.choice(["REFUSED", "NOT_COLLECTED"])
                dates[k] = today - timedelta(days=rng.randint(1, 70))
            dates = sorted(dates)
        second_shop = ((c["shop"] + 2) % len(BOUTIQUES)) + 1 if rng.random() < 0.18 else None
        for k, (st, day) in enumerate(zip(statuses, dates)):
            label, lo, hi = PRODUCTS[(c["id"] + k) % len(PRODUCTS)]
            amount = round(rng.uniform(lo, hi), 3)
            shop = second_shop if second_shop and k % 3 == 0 else c["shop"]
            orders.append((shop, c["id"], c["hash"], label, amount, st, day.isoformat(),
                           day.isoformat() + "T11:30:00"))
        if rng.random() < 0.45:
            label, lo, hi = rng.choice(PRODUCTS)
            amount = round(rng.uniform(lo, hi), 3)
            day = today - timedelta(days=rng.randint(0, 6))
            orders.append((c["shop"], c["id"], c["hash"], label, amount, "PENDING", day.isoformat(),
                           day.isoformat() + "T08:15:00"))

    # 12 commandes datées aujourd'hui pour la boutique de démonstration (Maison Emna)
    emna_customers = [c for c in customers if c["shop"] == 1][:12]
    for k, c in enumerate(emna_customers):
        label, lo, hi = PRODUCTS[k % len(PRODUCTS)]
        st = "PENDING" if k < 7 else rng.choice(["DELIVERED", "PENDING", "REFUSED"])
        amount = round(rng.uniform(lo, hi), 3)
        orders.append((1, c["id"], c["hash"], label, amount, st, today.isoformat(), now))

    seen = set()
    rows = []
    for shop, cid, ph, label, amount, st, day, created in orders:
        amount = round(float(amount), 3)
        fp = fingerprint(shop, ph, day, amount, label)
        while fp in seen:
            amount = round(amount + 0.001, 3)
            fp = fingerprint(shop, ph, day, amount, label)
        seen.add(fp)
        rows.append((shop, cid, ph, label, amount, st, day, fp, created))
    con.executemany(
        "INSERT INTO customer_order (boutique_id, customer_id, phone_hash, label, amount, status, order_date, fingerprint, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        rows,
    )

    risky = [c for c in customers if c["arch"] in ("HIGH", "MEDIUM")]
    for i in range(42):
        c = risky[i % len(risky)]
        status = ["EN_ATTENTE", "CONFIRME", "REJETE", "EN_ATTENTE"][i % 4]
        created = (today - timedelta(days=rng.randint(1, 120))).isoformat() + "T14:00:00"
        con.execute(
            "INSERT INTO complaint (boutique_id, phone_hash, phone_mask, motif, status, admin_note, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (c["shop"], c["hash"], c["mask"], MOTIFS_SIGNALEMENT[i % len(MOTIFS_SIGNALEMENT)], status,
             None if status == "EN_ATTENTE" else "Décision de démonstration, donnée fictive.", created, created),
        )
    for i in range(22):
        c = risky[(i * 3) % len(risky)]
        status = ["OUVERTE", "EN_COURS", "ACCEPTEE", "REJETEE"][i % 4]
        created = (today - timedelta(days=rng.randint(2, 90))).isoformat() + "T16:20:00"
        con.execute(
            "INSERT INTO contestation (boutique_id, phone_hash, phone_mask, motif, status, decision_note, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (c["shop"], c["hash"], c["mask"], MOTIFS_CONTESTATION[i % len(MOTIFS_CONTESTATION)], status,
             None if status in ("OUVERTE", "EN_COURS") else "Décision fictive enregistrée pour la démo.", created, created),
        )
    con.execute(
        "INSERT INTO audit_log (actor_email, action, details, created_at) VALUES (?,?,?,?)",
        ("system", "SEED", "Jeu fictif tunisien chargé (clients, commandes, signalements).", now),
    )
    counts = {
        "customers": con.execute("SELECT COUNT(*) FROM customer").fetchone()[0],
        "orders": con.execute("SELECT COUNT(*) FROM customer_order").fetchone()[0],
        "boutiques": con.execute("SELECT COUNT(*) FROM boutique").fetchone()[0],
        "complaints": con.execute("SELECT COUNT(*) FROM complaint").fetchone()[0],
        "contestations": con.execute("SELECT COUNT(*) FROM contestation").fetchone()[0],
    }
    con.execute("INSERT INTO meta (key, value) VALUES ('seed', ?)", (str(SEED),))
    con.execute("INSERT INTO meta (key, value) VALUES ('generated_on', ?)", (today.isoformat(),))
    con.commit()
    con.close()
    counts["path"] = path
    return counts


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    print(build(target))
