"""
Serveur de démonstration TrustOrder AI.
Les scores, le cold start et la priorité viennent de service/moteur.py (Sprints 1 et 2).
L'authentification de cette démo n'est pas Symfony Security — elle est indiquée comme telle.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
import time
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = os.path.join(ROOT, "service")
WEB = os.path.join(ROOT, "web")
DB_PATH = os.environ.get("TRUSTORDER_DEMO_DB", os.path.join(ROOT, "data", "demo.db"))
for p in (SERVICE, os.environ.get("PYTHONPATH", "")):
    if p and p not in sys.path:
        sys.path.insert(0, p)

import config  # noqa: E402
import import_fichier  # noqa: E402
import moteur  # noqa: E402
import ocr  # noqa: E402
import telephone  # noqa: E402
import verification  # noqa: E402
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile  # noqa: E402
from fastapi.responses import JSONResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

DASH_CACHE: dict = {}

SETTINGS_SPEC = {
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
DEFAULTS = {k: getattr(config, k) for k in SETTINGS_SPEC}
SESSIONS: dict[str, dict] = {}

app = FastAPI(title="TrustOrder AI — démo Sprint 3", docs_url=None, redoc_url=None)


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return hmac.compare_digest(dk.hex(), dk_hex)


def mask_phone(normalized: str) -> str:
    local = normalized[3:]
    return f"+216 {local[:2]} *** {local[-3:]}"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def apply_settings(con: sqlite3.Connection) -> None:
    for key, value in DEFAULTS.items():
        setattr(config, key, value)
    for row in con.execute("SELECT key, value FROM score_settings"):
        if row["key"] in SETTINGS_SPEC:
            kind = SETTINGS_SPEC[row["key"]][0]
            setattr(config, row["key"], int(row["value"]) if kind == "int" else float(row["value"]))


def current_settings() -> dict:
    out = {}
    for key, (kind, _a, _b) in SETTINGS_SPEC.items():
        value = getattr(config, key)
        out[key] = int(value) if kind == "int" else float(value)
    return out


def validate_settings(payload: dict) -> dict:
    clean = {}
    for key, raw in payload.items():
        if key not in SETTINGS_SPEC:
            raise HTTPException(422, f"Paramètre non autorisé : {key}")
        kind, lo, hi = SETTINGS_SPEC[key]
        try:
            value = int(raw) if kind == "int" else float(raw)
        except (TypeError, ValueError):
            raise HTTPException(422, f"Valeur invalide pour {key}")
        if value < lo or value > hi:
            raise HTTPException(422, f"{key} hors limites ({lo}–{hi})")
        clean[key] = value
    merged = current_settings()
    merged.update(clean)
    if merged["SEUIL_FAIBLE_RISQUE"] < merged["SEUIL_RISQUE_MOYEN"]:
        raise HTTPException(422, "Le seuil LOW doit être supérieur ou égal au seuil MEDIUM.")
    if merged["SEUIL_PRIORITE_HAUTE"] < merged["SEUIL_PRIORITE_MOYENNE"]:
        raise HTTPException(422, "Le seuil de priorité haute doit être supérieur ou égal au seuil moyen.")
    poids = merged["POIDS_RISQUE"] + merged["POIDS_MONTANT"] + merged["POIDS_INCERTITUDE"]
    if abs(poids - 1) > 0.001:
        raise HTTPException(422, "La somme des poids de priorité doit rester égale à 1.")
    return clean


def user_from_request(request: Request) -> dict:
    sid = request.cookies.get("to_session")
    session = SESSIONS.get(sid or "")
    if not session:
        raise HTTPException(401, "Connexion requise.")
    con = db()
    try:
        apply_settings(con)
        row = con.execute("SELECT * FROM users WHERE id=?", (session["uid"],)).fetchone()
    finally:
        con.close()
    if row is None or not row["active"]:
        raise HTTPException(401, "Compte inactif ou introuvable.")
    return dict(row)


def require_admin(user: dict) -> dict:
    if user["role"] != "ADMIN":
        raise HTTPException(403, "Réservé à l'administrateur.")
    return user


def require_shop(user: dict) -> dict:
    """Les commandes appartiennent aux boutiques : l'administrateur les supervise (lecture seule)."""
    if user["role"] != "SHOP" or not user["boutique_id"]:
        raise HTTPException(403, "Action réservée aux boutiques : l'administrateur supervise les commandes en lecture seule.")
    return user


def shop_scope(user: dict, requested: Optional[int] = None) -> Optional[int]:
    """None = toutes les boutiques (admin). Un entier = boutique imposée."""
    if user["role"] == "SHOP":
        if not user["boutique_id"]:
            raise HTTPException(403, "Compte boutique sans établissement.")
        return int(user["boutique_id"])
    return requested


def audit(con, email: str, action: str, details: str) -> None:
    con.execute(
        "INSERT INTO audit_log (actor_email, action, details, created_at) VALUES (?,?,?,?)",
        (email, action, details[:500], now_iso()),
    )


def log_analysis(con, user, phone_hash, phone_mask, kind, analysis, priority=None, summary=""):
    con.execute(
        """INSERT INTO analysis_log (boutique_id, actor_email, phone_mask, phone_hash, kind, score, risk_level,
           priority, cold_start, retention_probability, prediction_source, summary, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (user.get("boutique_id"), user["email"], phone_mask, phone_hash, kind,
         analysis.get("score"), analysis.get("risk_level"), priority, 1 if analysis.get("cold_start") else 0,
         analysis.get("retention_probability"), analysis.get("prediction_source") or "RULES",
         summary[:500], now_iso()),
    )


def histories(con: sqlite3.Connection, hashes: list[str], as_of: date | None = None) -> dict:
    as_of = as_of or date.today()
    limit = (as_of - timedelta(days=config.JOURS_ECHECS_RECENTS)).isoformat()
    found: dict[str, dict] = {}
    uniq = list(dict.fromkeys(h for h in hashes if h))
    for start in range(0, len(uniq), 400):
        batch = uniq[start:start + 400]
        if not batch:
            continue
        marks = ",".join("?" for _ in batch)
        rows = con.execute(
            f"""SELECT phone_hash AS h,
                  SUM(CASE WHEN status='DELIVERED' THEN 1 ELSE 0 END) AS delivered_orders,
                  SUM(CASE WHEN status='REFUSED' THEN 1 ELSE 0 END) AS refused_orders,
                  SUM(CASE WHEN status='NOT_COLLECTED' THEN 1 ELSE 0 END) AS not_collected_orders,
                  SUM(CASE WHEN status IN ('REFUSED','NOT_COLLECTED') AND order_date>=? THEN 1 ELSE 0 END) AS recent_failed_90d,
                  COUNT(DISTINCT boutique_id) AS distinct_shops
                FROM customer_order
                WHERE phone_hash IN ({marks}) AND order_date<=?
                GROUP BY phone_hash""",
            [limit, *batch, as_of.isoformat()],
        ).fetchall()
        rep = con.execute(
            f"""SELECT phone_hash AS h, COUNT(*) AS n FROM complaint
                WHERE status='CONFIRME' AND phone_hash IN ({marks}) AND substr(created_at,1,10)<=?
                GROUP BY phone_hash""",
            [*batch, as_of.isoformat()],
        ).fetchall()
        reports = {r["h"]: int(r["n"]) for r in rep}
        for r in rows:
            found[r["h"]] = {
                "delivered_orders": int(r["delivered_orders"]),
                "refused_orders": int(r["refused_orders"]),
                "not_collected_orders": int(r["not_collected_orders"]),
                "recent_failed_90d": int(r["recent_failed_90d"]),
                "distinct_shops": int(r["distinct_shops"]),
                "reports_count": reports.get(r["h"], 0),
            }
    return found


def bust_cache() -> None:
    DASH_CACHE.clear()


def empty_history() -> dict:
    return {"delivered_orders": 0, "refused_orders": 0, "not_collected_orders": 0,
            "recent_failed_90d": 0, "distinct_shops": 0, "reports_count": 0}


def engine_note(analysis: dict) -> dict:
    if analysis.get("cold_start"):
        prediction = "Cold start : le modèle ML n'a pas été appelé (historique insuffisant). Décision du moteur de règles."
    elif analysis.get("retention_probability") is None:
        prediction = "Probabilité ML absente."
    else:
        prediction = f"Probabilité de rétention calculée par {analysis.get('model_version')} (régression logistique du Sprint 1)."
    return {
        "calculated_by": "service/moteur.py",
        "prediction_note": prediction,
        "demo_data": True,
        "not_a_hardcoded_score": True,
    }


def public_user(row: dict, con: sqlite3.Connection | None = None) -> dict:
    shop = None
    if row.get("boutique_id") and con is not None:
        b = con.execute("SELECT id, name, city, governorate, active FROM boutique WHERE id=?", (row["boutique_id"],)).fetchone()
        shop = dict(b) if b else None
    return {
        "id": row["id"], "email": row["email"], "full_name": row["full_name"], "role": row["role"],
        "active": bool(row["active"]), "boutique": shop,
        "auth": "demo-session (ce n'est pas Symfony Security)",
    }


def fingerprint(boutique_id, phone_hash, day, amount, label) -> str:
    raw = f"{boutique_id}|{phone_hash}|{day}|{amount}|{(label or '').strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


class LoginIn(BaseModel):
    email: str
    password: str


class OrderIn(BaseModel):
    phone: str
    label: str = Field(min_length=2, max_length=255)
    amount: float = Field(gt=0, le=100000)
    boutique_id: Optional[int] = None


class ConfirmIn(BaseModel):
    status: str


class BulkIn(BaseModel):
    phones: list[str] = Field(min_length=1, max_length=1000)


class SimulateIn(BaseModel):
    history: dict
    amount: float = Field(default=80, gt=0)


class ComplaintIn(BaseModel):
    phone: str
    motif: str = Field(min_length=5, max_length=255)


class DecisionIn(BaseModel):
    status: str
    note: str = ""


class BoutiqueIn(BaseModel):
    name: str
    governorate: str
    city: str
    address: str
    active: bool = True


class RegisterShopIn(BaseModel):
    shop_name: str = Field(min_length=2, max_length=120)
    governorate: str = Field(min_length=2, max_length=60)
    city: str = Field(min_length=2, max_length=80)
    address: str = Field(min_length=3, max_length=200)
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=190)
    password: str = Field(min_length=8, max_length=128)


class UserIn(BaseModel):
    email: str
    full_name: str
    password: str = Field(min_length=8)
    role: str
    boutique_id: Optional[int] = None


@app.middleware("http")
async def settings_middleware(request: Request, call_next):
    if os.path.exists(DB_PATH):
        con = db()
        try:
            apply_settings(con)
        finally:
            con.close()
    return await call_next(request)


@app.post("/api/login")
def login(body: LoginIn):
    con = db()
    try:
        row = con.execute("SELECT * FROM users WHERE email=?", (body.email.strip().lower(),)).fetchone()
        if row is None or not verify_password(body.password, row["password"]) or not row["active"]:
            raise HTTPException(401, "E-mail ou mot de passe incorrect.")
        if row["role"] == "SHOP" and row["boutique_id"]:
            shop = con.execute("SELECT active FROM boutique WHERE id=?", (row["boutique_id"],)).fetchone()
            if shop and not shop["active"]:
                raise HTTPException(403, "Cette boutique est désactivée.")
        sid = secrets.token_urlsafe(32)
        SESSIONS[sid] = {"uid": row["id"]}
        audit(con, row["email"], "LOGIN", "Connexion à la démo web.")
        con.commit()
        payload = public_user(dict(row), con)
    finally:
        con.close()
    response = JSONResponse(payload)
    response.set_cookie("to_session", sid, httponly=True, samesite="lax", path="/")
    return response


@app.post("/api/register-shop")
def register_shop(body: RegisterShopIn):
    """Inscription publique : crée la boutique ET son compte gérant, puis ouvre la session."""
    email = body.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(422, "Adresse e-mail invalide.")
    if body.password.strip().lower() == email:
        raise HTTPException(422, "Le mot de passe ne doit pas être identique à l'e-mail.")
    name = " ".join(body.shop_name.split())
    con = db()
    try:
        if con.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise HTTPException(409, "Cet e-mail est déjà utilisé.")
        if con.execute("SELECT 1 FROM boutique WHERE lower(name)=lower(?)", (name,)).fetchone():
            raise HTTPException(409, "Une boutique porte déjà ce nom. Ajoutez la ville ou un complément.")
        try:
            cur = con.execute(
                "INSERT INTO boutique (name, governorate, city, address, active, created_at) VALUES (?,?,?,?,1,?)",
                (name, body.governorate.strip(), body.city.strip(), body.address.strip(), now_iso()),
            )
            boutique_id = cur.lastrowid
            salt = secrets.token_bytes(16)
            dk = hashlib.pbkdf2_hmac("sha256", body.password.encode(), salt, 120_000)
            ucur = con.execute(
                "INSERT INTO users (email, password, full_name, role, boutique_id, active) VALUES (?,?,?,?,?,1)",
                (email, salt.hex() + "$" + dk.hex(), " ".join(body.full_name.split()), "SHOP", boutique_id),
            )
        except sqlite3.IntegrityError:
            con.rollback()
            raise HTTPException(409, "Cet e-mail est déjà utilisé.")
        audit(con, email, "SHOP_REGISTER", f"Boutique « {name} » créée par inscription.")
        con.commit()
        row = con.execute("SELECT * FROM users WHERE id=?", (ucur.lastrowid,)).fetchone()
        payload = public_user(dict(row), con)
        sid = secrets.token_urlsafe(32)
        SESSIONS[sid] = {"uid": row["id"]}
    finally:
        con.close()
    response = JSONResponse(payload)
    response.set_cookie("to_session", sid, httponly=True, samesite="lax", path="/")
    return response


@app.post("/api/logout")
def logout(request: Request):
    sid = request.cookies.get("to_session")
    if sid:
        SESSIONS.pop(sid, None)
    response = JSONResponse({"ok": True})
    response.delete_cookie("to_session", path="/")
    return response


@app.get("/api/me")
def me(request: Request):
    user = user_from_request(request)
    con = db()
    try:
        return public_user(user, con)
    finally:
        con.close()


def _avg(values):
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def dashboard_for(con, boutique_id: Optional[int]):
    cache_key = (boutique_id, date.today().isoformat(), tuple(sorted((k, str(v)) for k, v in current_settings().items())))
    hit = DASH_CACHE.get(cache_key)
    if hit and time.time() - hit[0] < 25:
        return hit[1]
    where = ""
    params: list = []
    if boutique_id:
        where = "WHERE boutique_id=?"
        params = [boutique_id]
    today = date.today()
    yday = today - timedelta(days=1)
    week = today - timedelta(days=7)
    orders_today = con.execute(
        f"SELECT COUNT(*) AS n FROM customer_order {where} {'AND' if where else 'WHERE'} order_date=?",
        [*params, today.isoformat()],
    ).fetchone()["n"]
    orders_yday = con.execute(
        f"SELECT COUNT(*) AS n FROM customer_order {where} {'AND' if where else 'WHERE'} order_date=?",
        [*params, yday.isoformat()],
    ).fetchone()["n"]
    phone_rows = con.execute(
        f"SELECT DISTINCT phone_hash FROM customer_order {where}", params
    ).fetchall()
    hashes = [r["phone_hash"] for r in phone_rows]
    now_h = histories(con, hashes, today)
    old_h = histories(con, hashes, week)
    scores, old_scores, risks = [], [], {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    cold = 0
    retentions = []
    model = None
    for h in hashes:
        hist = now_h.get(h) or empty_history()
        analysis = moteur.analyser_client(hist)
        scores.append(analysis["score"])
        risks[analysis["risk_level"]] += 1
        if analysis["cold_start"]:
            cold += 1
        elif analysis["retention_probability"] is not None:
            retentions.append(analysis["retention_probability"])
            model = analysis.get("model_version")
        previous = moteur.analyser_client(old_h.get(h) or empty_history())
        old_scores.append(previous["score"])
    pending = con.execute(
        f"""SELECT o.id, o.amount, o.phone_hash, o.label, o.order_date, o.status, c.full_name, c.phone_mask, b.name AS shop
            FROM customer_order o
            JOIN customer c ON c.id=o.customer_id
            JOIN boutique b ON b.id=o.boutique_id
            {where.replace('boutique_id', 'o.boutique_id')} AND o.status='PENDING'
            ORDER BY o.order_date DESC LIMIT 80""",
        params,
    ).fetchall() if where else con.execute(
        """SELECT o.id, o.amount, o.phone_hash, o.label, o.order_date, o.status, c.full_name, c.phone_mask, b.name AS shop
           FROM customer_order o JOIN customer c ON c.id=o.customer_id JOIN boutique b ON b.id=o.boutique_id
           WHERE o.status='PENDING' ORDER BY o.order_date DESC LIMIT 80"""
    ).fetchall()
    ranked = []
    high_priority = 0
    # count high priority on a larger pending set
    pending_all = con.execute(
        f"SELECT id, amount, phone_hash FROM customer_order {where} {'AND' if where else 'WHERE'} status='PENDING'",
        params,
    ).fetchall()
    hist_pending = histories(con, [r["phone_hash"] for r in pending_all])
    for r in pending_all:
        pr = moteur.prioriser_commande(hist_pending.get(r["phone_hash"]) or empty_history(),
                                       {"order_id": str(r["id"]), "amount": float(r["amount"])})
        if pr["priority"] == "HIGH":
            high_priority += 1
    for r in pending:
        hist = hist_pending.get(r["phone_hash"]) or histories(con, [r["phone_hash"]]).get(r["phone_hash"]) or empty_history()
        pr = moteur.prioriser_commande(hist, {"order_id": str(r["id"]), "amount": float(r["amount"])})
        an = moteur.analyser_client(hist)
        ranked.append({
            "order_id": r["id"], "customer": r["full_name"], "phone_mask": r["phone_mask"],
            "shop": r["shop"], "label": r["label"], "amount": r["amount"],
            "score": an["score"], "risk_level": an["risk_level"],
            "priority_score": pr["priority_score"], "priority": pr["priority"],
            "explanation": pr["explanation"], "cold_start": an["cold_start"],
            "prediction_source": an["prediction_source"],
            "engine": engine_note(an),
        })
    ranked.sort(key=lambda x: -x["priority_score"])
    recent = con.execute(
        f"""SELECT o.id, c.full_name, c.phone_mask, o.label, o.status, o.amount, o.order_date, b.name AS shop
            FROM customer_order o JOIN customer c ON c.id=o.customer_id JOIN boutique b ON b.id=o.boutique_id
            {where.replace('boutique_id', 'o.boutique_id') if where else ''}
            ORDER BY o.id DESC LIMIT 8""",
        params,
    ).fetchall()
    delivered = con.execute(
        f"SELECT COUNT(*) n FROM customer_order {where} {'AND' if where else 'WHERE'} status='DELIVERED'", params
    ).fetchone()["n"]
    refused = con.execute(
        f"SELECT COUNT(*) n FROM customer_order {where} {'AND' if where else 'WHERE'} status='REFUSED'", params
    ).fetchone()["n"]
    missed = con.execute(
        f"SELECT COUNT(*) n FROM customer_order {where} {'AND' if where else 'WHERE'} status='NOT_COLLECTED'", params
    ).fetchone()["n"]
    total_orders = con.execute(f"SELECT COUNT(*) n FROM customer_order {where}", params).fetchone()["n"]
    customers_n = len(hashes)
    score_now = _avg(scores)
    score_old = _avg(old_scores)
    data = {
        "date": today.isoformat(),
        "orders_today": orders_today,
        "orders_yesterday": orders_yday,
        "orders_delta_pct": None if not orders_yday else round((orders_today - orders_yday) / orders_yday * 100, 1),
        "mean_score": score_now,
        "mean_score_delta_7d": None if score_now is None or score_old is None else round(score_now - score_old, 1),
        "high_priority_pending": high_priority,
        "mean_retention": None if not retentions else round(sum(retentions) / len(retentions) * 100, 1),
        "retention_sample": len(retentions),
        "model_version": model,
        "customers": customers_n,
        "cold_start_pct": round(100 * cold / customers_n, 1) if customers_n else 0,
        "cold_start_count": cold,
        "risk": risks,
        "totals": {"orders": total_orders, "delivered": delivered, "refused": refused, "not_collected": missed},
        "priority_preview": ranked[:6],
        "recent_orders": [dict(r) for r in recent],
        "engine": {
            "calculated_by": "moteur.analyser_client + moteur.prioriser_commande",
            "score_is_live": True,
            "retention_excludes_cold_start": True,
        },
    }
    DASH_CACHE[cache_key] = (time.time(), data)
    return data


@app.get("/api/dashboard")
def dashboard(request: Request):
    user = user_from_request(request)
    con = db()
    try:
        scope = shop_scope(user)
        data = dashboard_for(con, scope)
        data["scope"] = "boutique" if scope else "global"
        return data
    finally:
        con.close()


@app.get("/api/orders")
def list_orders(request: Request, page: int = 1, status: str = "", q: str = "", page_size: int = 15, boutique_id: int = 0):
    user = user_from_request(request)
    page = max(1, page)
    page_size = min(50, max(5, page_size))
    con = db()
    try:
        clauses, params = [], []
        scope = shop_scope(user, boutique_id or None)
        if scope:
            clauses.append("o.boutique_id=?")
            params.append(scope)
        if status in ("PENDING", "DELIVERED", "REFUSED", "NOT_COLLECTED"):
            clauses.append("o.status=?")
            params.append(status)
        if q.strip():
            clauses.append("(c.full_name LIKE ? OR o.label LIKE ? OR c.phone_mask LIKE ? OR c.phone_normalized LIKE ?)")
            like = f"%{q.strip()}%"
            params.extend([like, like, like, like])
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        total = con.execute(
            f"SELECT COUNT(*) n FROM customer_order o JOIN customer c ON c.id=o.customer_id {where}", params
        ).fetchone()["n"]
        rows = con.execute(
            f"""SELECT o.id, o.label, o.amount, o.status, o.order_date, o.created_at, o.boutique_id, b.name AS shop,
                      c.full_name, c.phone_mask, c.phone_normalized, c.city
               FROM customer_order o
               JOIN customer c ON c.id=o.customer_id
               JOIN boutique b ON b.id=o.boutique_id
               {where}
               ORDER BY o.id DESC
               LIMIT ? OFFSET ?""",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
        items = []
        for r in rows:
            item = dict(r)
            if user["role"] != "SHOP":
                item.pop("phone_normalized", None)
            items.append(item)
        return {"page": page, "page_size": page_size, "total": total, "items": items}
    finally:
        con.close()


@app.post("/api/orders")
def create_order(request: Request, body: OrderIn):
    user = user_from_request(request)
    require_shop(user)
    phone = telephone.normaliser(body.phone)
    if not phone:
        raise HTTPException(422, "Numéro tunisien invalide (8 chiffres).")
    con = db()
    try:
        boutique_id = int(user["boutique_id"])
        shop = con.execute("SELECT * FROM boutique WHERE id=? AND active=1", (boutique_id,)).fetchone()
        if not shop:
            raise HTTPException(404, "Boutique introuvable ou inactive.")
        digest = telephone.hacher(phone)
        customer = con.execute("SELECT * FROM customer WHERE phone_hash=?", (digest,)).fetchone()
        if customer is None:
            con.execute(
                """INSERT INTO customer (full_name, phone_normalized, phone_hash, phone_mask, governorate, city)
                   VALUES (?,?,?,?,?,?)""",
                ("Client saisi", phone, digest, mask_phone(phone), shop["governorate"], shop["city"]),
            )
            customer = con.execute("SELECT * FROM customer WHERE phone_hash=?", (digest,)).fetchone()
        day = date.today().isoformat()
        amount = round(float(body.amount), 3)
        fp = fingerprint(boutique_id, digest, day, amount, body.label.strip())
        if con.execute("SELECT 1 FROM customer_order WHERE fingerprint=?", (fp,)).fetchone():
            raise HTTPException(409, "Cette commande semble déjà enregistrée (même numéro, date, montant et libellé).")
        cur = con.execute(
            """INSERT INTO customer_order (boutique_id, customer_id, phone_hash, label, amount, status, order_date, fingerprint, created_at)
               VALUES (?,?,?,?,?,'PENDING',?,?,?)""",
            (boutique_id, customer["id"], digest, body.label.strip(), amount, day, fp, now_iso()),
        )
        hist = histories(con, [digest]).get(digest) or empty_history()
        analysis = moteur.analyser_client(hist)
        priority = moteur.prioriser_commande(hist, {"order_id": str(cur.lastrowid), "amount": amount})
        log_analysis(con, user, digest, customer["phone_mask"], "ORDER_CREATE", analysis,
                     priority["priority"], priority["explanation"])
        audit(con, user["email"], "ORDER_CREATE", f"Commande #{cur.lastrowid} créée ({customer['phone_mask']}).")
        con.commit()
        return {"id": cur.lastrowid, "phone_mask": customer["phone_mask"], "history": hist,
                "analysis": analysis, "priority": priority, "engine": engine_note(analysis)}
    finally:
        con.close()


@app.post("/api/orders/{order_id}/confirm")
def confirm_order(order_id: int, request: Request, body: ConfirmIn):
    user = user_from_request(request)
    require_shop(user)
    if body.status not in ("DELIVERED", "REFUSED", "NOT_COLLECTED"):
        raise HTTPException(422, "Statut final attendu : DELIVERED, REFUSED ou NOT_COLLECTED.")
    con = db()
    try:
        row = con.execute("SELECT * FROM customer_order WHERE id=?", (order_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Commande introuvable.")
        if row["boutique_id"] != user["boutique_id"]:
            raise HTTPException(403, "Cette commande appartient à une autre boutique.")
        if row["status"] != "PENDING":
            raise HTTPException(409, "Seule une commande en attente peut être confirmée.")
        con.execute("UPDATE customer_order SET status=? WHERE id=?", (body.status, order_id))
        audit(con, user["email"], "ORDER_CONFIRM", f"Commande #{order_id} → {body.status}.")
        con.commit()
        return {"id": order_id, "status": body.status}
    finally:
        con.close()


@app.get("/api/clients")
def search_client(request: Request, telephone: str = Query(...)):
    user = user_from_request(request)
    phone = telephone_normaliser(telephone)
    return _search(user, phone)


def telephone_normaliser(value: str) -> str:
    phone = telephone.normaliser(value)
    if not phone:
        raise HTTPException(422, "Numéro tunisien invalide (8 chiffres).")
    return phone


def _search(user, phone: str):
    con = db()
    try:
        digest = telephone.hacher(phone)
        customer = con.execute("SELECT * FROM customer WHERE phone_hash=?", (digest,)).fetchone()
        hist = histories(con, [digest]).get(digest)
        known = hist is not None
        hist = hist or empty_history()
        analysis = moteur.analyser_client(hist)
        scope = shop_scope(user)
        if scope:
            shop_orders = con.execute(
                """SELECT id, label, amount, status, order_date FROM customer_order
                   WHERE boutique_id=? AND phone_hash=? ORDER BY order_date DESC LIMIT 20""",
                (scope, digest),
            ).fetchall()
        else:
            shop_orders = con.execute(
                """SELECT o.id, o.label, o.amount, o.status, o.order_date, b.name AS shop
                   FROM customer_order o JOIN boutique b ON b.id=o.boutique_id
                   WHERE o.phone_hash=? ORDER BY o.order_date DESC LIMIT 20""",
                (digest,),
            ).fetchall()
        priority = None
        log_analysis(con, user, digest, mask_phone(phone), "SEARCH", analysis, None,
                     f"Recherche {mask_phone(phone)} → {analysis['score']}/100 {analysis['risk_level']}")
        con.commit()
        return {
            "phone_mask": mask_phone(phone),
            "phone_full": phone if user["role"] == "SHOP" else None,
            "known_customer": known,
            "customer": None if not customer else {
                "full_name": customer["full_name"], "city": customer["city"], "governorate": customer["governorate"],
            },
            "history": hist,
            "analysis": analysis,
            "shop_orders": [dict(r) for r in shop_orders],
            "priority_if_new_order_amount_100": moteur.prioriser_commande(hist, {"amount": 100.0, "order_id": "preview"}),
            "engine": engine_note(analysis),
            "cross_shop_note": "Les compteurs agrègent toutes les boutiques. Le détail des commandes des autres boutiques n'est pas affiché.",
        }
    finally:
        con.close()


@app.post("/api/bulk")
def bulk(request: Request, body: BulkIn):
    user = user_from_request(request)
    return _bulk(user, body.phones)


def _bulk(user, phones: list[str]):
    if len(phones) > config.MAX_NUMEROS_MASSE:
        raise HTTPException(422, f"{config.MAX_NUMEROS_MASSE} numéros maximum.")
    con = db()
    try:
        normalized = [telephone.normaliser(p) for p in phones]
        hashes = {n: telephone.hacher(n) for n in set(normalized) if n}
        found = histories(con, list(hashes.values()))
        results = []
        analyses = {}
        for raw, tel in zip(phones, normalized):
            if tel is None:
                results.append({"input": raw, "phone_mask": None, "result_type": "INVALID_NUMBER",
                                "orders": 0, "score": None, "risk_level": None, "cold_start": None,
                                "retention_probability": None,
                                "recommendation": "Numéro invalide : à corriger avant toute vérification."})
                continue
            hist = found.get(hashes[tel])
            if hist is None:
                results.append({"input": raw, "phone_mask": mask_phone(tel), "result_type": "UNKNOWN_CUSTOMER",
                                "orders": 0, "score": None, "risk_level": "UNKNOWN", "cold_start": True,
                                "retention_probability": None,
                                "recommendation": "Aucun historique : traiter comme un nouveau client (confirmer la commande). La probabilité ML n'est pas estimée."})
                continue
            if tel not in analyses:
                analyses[tel] = moteur.analyser_client(hist)
            a = analyses[tel]
            total = hist["delivered_orders"] + hist["refused_orders"] + hist["not_collected_orders"]
            results.append({"input": raw, "phone_mask": mask_phone(tel), "result_type": "ANALYZED",
                            "orders": total, "score": a["score"], "risk_level": a["risk_level"],
                            "cold_start": a["cold_start"], "retention_probability": a["retention_probability"],
                            "prediction_source": a["prediction_source"], "recommendation": a["recommendation"],
                            "engine": engine_note(a)})
        summary = {
            "total": len(results),
            "invalid_numbers": sum(1 for r in results if r["result_type"] == "INVALID_NUMBER"),
            "unknown_customers": sum(1 for r in results if r["result_type"] == "UNKNOWN_CUSTOMER"),
            "LOW": sum(1 for r in results if r.get("risk_level") == "LOW"),
            "MEDIUM": sum(1 for r in results if r.get("risk_level") == "MEDIUM"),
            "HIGH": sum(1 for r in results if r.get("risk_level") == "HIGH"),
        }
        audit(con, user["email"], "BULK", f"Vérification en masse de {len(results)} numéros.")
        con.commit()
        return {"summary": summary, "results": results,
                "engine": {"calculated_by": "moteur.analyser_client", "live": True}}
    finally:
        con.close()


@app.post("/api/bulk/file")
async def bulk_file(request: Request, fichier: UploadFile = File(...)):
    user = user_from_request(request)
    content = await fichier.read()
    if len(content) > config.TAILLE_MAX_FICHIER:
        raise HTTPException(413, "Fichier trop volumineux.")
    try:
        table = import_fichier.lire_tableau(content, fichier.filename or "liste.csv")
    except import_fichier.ErreurImport as exc:
        raise HTTPException(422, str(exc))
    table = [line for line in table if any(c is not None and str(c).strip() for c in line)]
    if not table:
        raise HTTPException(422, "Fichier vide.")
    header = not any(telephone.normaliser(c) for c in table[0] if c is not None)
    if header:
        cols = import_fichier.detecter_colonnes(table[0], table[1:])
        if "phone" not in cols:
            raise HTTPException(422, "Colonne téléphone introuvable.")
        idx, rows = cols["phone"], table[1:]
    else:
        idx, rows = 0, table
    phones = []
    for line in rows:
        if idx < len(line):
            phones.append(import_fichier._en_texte(line[idx]))
    phones = [p for p in phones if p]
    return _bulk(user, phones[: config.MAX_NUMEROS_MASSE])


@app.post("/api/import/file")
async def import_file(request: Request, fichier: UploadFile = File(...)):
    user = user_from_request(request)
    if user["role"] != "SHOP":
        raise HTTPException(403, "L'import est réservé à une boutique.")
    content = await fichier.read()
    if len(content) > config.TAILLE_MAX_FICHIER:
        raise HTTPException(413, "Fichier trop volumineux (10 Mo maximum).")
    try:
        lines, info = import_fichier.importer_fichier(content, fichier.filename or "")
    except import_fichier.ErreurImport as exc:
        raise HTTPException(422, str(exc))
    verification.valider_lot(lines)
    return _store_lot(user, "FILE", fichier.filename or "import", lines, info)


@app.post("/api/import/document")
async def import_document(request: Request, fichier: UploadFile = File(...)):
    user = user_from_request(request)
    if user["role"] != "SHOP":
        raise HTTPException(403, "L'import est réservé à une boutique.")
    content = await fichier.read()
    if len(content) > config.TAILLE_MAX_FICHIER:
        raise HTTPException(413, "Fichier trop volumineux.")
    try:
        lines, info = ocr.importer_document(content, fichier.filename or "")
    except ocr.OcrIndisponible as exc:
        raise HTTPException(503, str(exc))
    except ocr.ErreurDocument as exc:
        raise HTTPException(422, str(exc))
    if not lines:
        raise HTTPException(422, "Aucun numéro de téléphone trouvé dans le document.")
    verification.valider_lot(lines)
    for line in lines:
        if line.get("confidence", 1) < config.CONFIANCE_OCR_MIN:
            line["issues"].append({
                "level": "warning", "field": "line",
                "message": f"Extraction incertaine (confiance {line['confidence']:.0%}) : vérifiez cette ligne.",
            })
            line["valid"] = not any(p["level"] == "error" for p in line["issues"])
    return _store_lot(user, "OCR", fichier.filename or "document", lines, info)


def _store_lot(user, source, filename, lines, info):
    lot_id = uuid.uuid4().hex[:12]
    con = db()
    try:
        con.execute(
            """INSERT INTO import_lot (id, boutique_id, source, filename, status, info_json, lines_json, created_at)
               VALUES (?,?,?,?, 'A_VERIFIER', ?, ?, ?)""",
            (lot_id, user["boutique_id"], source, filename, json.dumps(info), json.dumps(lines), now_iso()),
        )
        audit(con, user["email"], "IMPORT", f"Lot {lot_id} ({source}, {filename}) à vérifier.")
        con.commit()
    finally:
        con.close()
    return _lot_payload(lot_id)


def _lot_payload(lot_id: str):
    con = db()
    try:
        row = con.execute("SELECT * FROM import_lot WHERE id=?", (lot_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Lot introuvable.")
        lines = json.loads(row["lines_json"])
        return {
            "lot_id": row["id"], "source": row["source"], "filename": row["filename"], "status": row["status"],
            "info": json.loads(row["info_json"]), "summary": verification.resume(lines),
            "report": json.loads(row["report_json"]) if row["report_json"] else None,
            "lines": lines,
        }
    finally:
        con.close()


def _own_lot(user, lot_id):
    con = db()
    try:
        row = con.execute("SELECT * FROM import_lot WHERE id=?", (lot_id,)).fetchone()
    finally:
        con.close()
    if not row:
        raise HTTPException(404, "Lot introuvable.")
    if user["role"] == "SHOP" and row["boutique_id"] != user["boutique_id"]:
        raise HTTPException(403, "Ce lot appartient à une autre boutique.")
    return row


class LinePatch(BaseModel):
    phone: Optional[str] = None
    status: Optional[str] = None
    amount: Optional[str] = None
    order_date: Optional[str] = None
    label: Optional[str] = None
    ignore: Optional[bool] = None


@app.get("/api/lots/{lot_id}")
def get_lot(lot_id: str, request: Request):
    user = user_from_request(request)
    _own_lot(user, lot_id)
    return _lot_payload(lot_id)


@app.patch("/api/lots/{lot_id}/lines/{numero}")
def patch_line(lot_id: str, numero: int, request: Request, body: LinePatch):
    user = user_from_request(request)
    row = _own_lot(user, lot_id)
    if row["status"] != "A_VERIFIER":
        raise HTTPException(409, "Ce lot est déjà validé.")
    lines = json.loads(row["lines_json"])
    target = next((l for l in lines if l.get("line") == numero), None)
    if target is None:
        raise HTTPException(404, "Ligne introuvable.")
    for key, value in body.model_dump(exclude_unset=True).items():
        target[key] = value
    verification.valider_lot(lines)
    con = db()
    try:
        con.execute("UPDATE import_lot SET lines_json=? WHERE id=?", (json.dumps(lines), lot_id))
        con.commit()
    finally:
        con.close()
    return _lot_payload(lot_id)


@app.post("/api/lots/{lot_id}/validate")
def validate_lot(lot_id: str, request: Request):
    user = user_from_request(request)
    row = _own_lot(user, lot_id)
    if row["status"] != "A_VERIFIER":
        raise HTTPException(409, "Ce lot a déjà été validé.")
    lines = json.loads(row["lines_json"])
    verification.valider_lot(lines)
    inserted = duplicates = ignored = 0
    rejected = []
    con = db()
    try:
        shop = con.execute("SELECT * FROM boutique WHERE id=?", (row["boutique_id"],)).fetchone()
        for line in lines:
            if line.get("ignore"):
                ignored += 1
                continue
            if not line.get("valid"):
                rejected.append({"line": line.get("line"), "issues": [i["message"] for i in line.get("issues", []) if i["level"] == "error"]})
                continue
            phone = line["phone_normalized"]
            digest = telephone.hacher(phone)
            customer = con.execute("SELECT * FROM customer WHERE phone_hash=?", (digest,)).fetchone()
            if customer is None:
                con.execute(
                    """INSERT INTO customer (full_name, phone_normalized, phone_hash, phone_mask, governorate, city)
                       VALUES (?,?,?,?,?,?)""",
                    ("Client " + mask_phone(phone), phone, digest, mask_phone(phone), shop["governorate"], shop["city"]),
                )
                customer = con.execute("SELECT * FROM customer WHERE phone_hash=?", (digest,)).fetchone()
            amount = line.get("amount_value")
            amount = 0.0 if amount is None else round(float(amount), 3)
            day = line["date_value"]
            fp = fingerprint(row["boutique_id"], digest, day, amount, line.get("label") or "")
            existing = con.execute("SELECT id, status FROM customer_order WHERE fingerprint=?", (fp,)).fetchone()
            if existing is None:
                if amount <= 0 and line["status_normalized"] != "PENDING":
                    amount = 0.001
                con.execute(
                    """INSERT INTO customer_order (boutique_id, customer_id, phone_hash, label, amount, status, order_date, fingerprint, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (row["boutique_id"], customer["id"], digest, line.get("label") or "Import", max(amount, 0.001),
                     line["status_normalized"], day, fp, now_iso()),
                )
                inserted += 1
            elif existing["status"] == "PENDING" and line["status_normalized"] != "PENDING":
                con.execute("UPDATE customer_order SET status=? WHERE id=?", (line["status_normalized"], existing["id"]))
                inserted += 0
            else:
                duplicates += 1
        report = {"inserted": inserted, "duplicates_ignored": duplicates, "ignored_by_user": ignored, "rejected": rejected}
        con.execute("UPDATE import_lot SET status='VALIDE', report_json=?, lines_json=? WHERE id=?",
                    (json.dumps(report), json.dumps(lines), lot_id))
        audit(con, user["email"], "IMPORT_VALIDATE", f"Lot {lot_id} : {inserted} insérée(s), {duplicates} doublon(s).")
        con.commit()
        return {"lot_id": lot_id, "status": "VALIDE", "report": report}
    finally:
        con.close()


@app.get("/api/priority")
def priority_list(request: Request, limit: int = 40):
    user = user_from_request(request)
    limit = min(100, max(5, limit))
    con = db()
    try:
        scope = shop_scope(user)
        if scope:
            rows = con.execute(
                """SELECT o.id, o.amount, o.label, o.order_date, o.phone_hash, c.full_name, c.phone_mask, b.name AS shop
                   FROM customer_order o JOIN customer c ON c.id=o.customer_id JOIN boutique b ON b.id=o.boutique_id
                   WHERE o.status='PENDING' AND o.boutique_id=? ORDER BY o.id DESC LIMIT 200""",
                (scope,),
            ).fetchall()
        else:
            rows = con.execute(
                """SELECT o.id, o.amount, o.label, o.order_date, o.phone_hash, c.full_name, c.phone_mask, b.name AS shop
                   FROM customer_order o JOIN customer c ON c.id=o.customer_id JOIN boutique b ON b.id=o.boutique_id
                   WHERE o.status='PENDING' ORDER BY o.id DESC LIMIT 200"""
            ).fetchall()
        found = histories(con, [r["phone_hash"] for r in rows])
        items = []
        for r in rows:
            hist = found.get(r["phone_hash"]) or empty_history()
            an = moteur.analyser_client(hist)
            pr = moteur.prioriser_commande(hist, {"order_id": str(r["id"]), "amount": float(r["amount"])})
            items.append({
                "order_id": r["id"], "customer": r["full_name"], "phone_mask": r["phone_mask"], "shop": r["shop"],
                "label": r["label"], "amount": r["amount"], "order_date": r["order_date"],
                "score": an["score"], "risk_level": an["risk_level"], "cold_start": an["cold_start"],
                "retention_probability": an["retention_probability"], "prediction_source": an["prediction_source"],
                "priority": pr["priority"], "priority_score": pr["priority_score"],
                "explanation": pr["explanation"], "factors": pr["factors"], "engine": engine_note(an),
            })
        items.sort(key=lambda x: -x["priority_score"])
        return {"items": items[:limit], "engine": {"calculated_by": "moteur.prioriser_commande", "live": True}}
    finally:
        con.close()


@app.get("/api/analyses")
def analyses(request: Request, page: int = 1):
    user = user_from_request(request)
    page = max(1, page)
    con = db()
    try:
        if user["role"] == "SHOP":
            where, params = "WHERE boutique_id=?", [user["boutique_id"]]
        else:
            where, params = "", []
        total = con.execute(f"SELECT COUNT(*) n FROM analysis_log {where}", params).fetchone()["n"]
        rows = con.execute(
            f"""SELECT id, actor_email, phone_mask, kind, score, risk_level, priority, cold_start,
                      retention_probability, prediction_source, summary, created_at
               FROM analysis_log {where} ORDER BY id DESC LIMIT 20 OFFSET ?""",
            [*params, (page - 1) * 20],
        ).fetchall()
        return {"total": total, "page": page, "items": [dict(r) for r in rows]}
    finally:
        con.close()


@app.post("/api/simulate")
def simulate(request: Request, body: SimulateIn):
    user_from_request(request)
    needed = ["delivered_orders", "refused_orders", "not_collected_orders", "recent_failed_90d", "distinct_shops", "reports_count"]
    hist = {}
    for key in needed:
        try:
            hist[key] = max(0, int(body.history.get(key, 0)))
        except (TypeError, ValueError):
            raise HTTPException(422, f"Champ historique invalide : {key}")
    analysis = moteur.analyser_client(hist)
    priority = moteur.prioriser_commande(hist, {"amount": float(body.amount), "order_id": "simulation"})
    return {"history": hist, "analysis": analysis, "priority": priority, "engine": engine_note(analysis),
            "warning": "Simulation : l'historique est saisi à la main. Le résultat est calculé par le moteur, il ne provient pas d'une commande réelle."}


@app.get("/api/engine")
def engine_info(request: Request):
    user_from_request(request)
    empty = empty_history()
    check = moteur.analyser_client(empty)
    return {
        "self_check_unknown_customer_score": check["score"],
        "self_check_expected": 50,
        "self_check_ok": check["score"] == 50 and check["cold_start"] is True,
        "model_version": moteur.ml.VERSION if hasattr(moteur, "ml") else None,
        "min_history": config.MIN_HISTORIQUE,
        "risk_thresholds": {"LOW": config.SEUIL_FAIBLE_RISQUE, "MEDIUM": config.SEUIL_RISQUE_MOYEN},
        "priority_thresholds": {"HIGH": config.SEUIL_PRIORITE_HAUTE, "MEDIUM": config.SEUIL_PRIORITE_MOYENNE},
        "weights": {"risk": config.POIDS_RISQUE, "amount": config.POIDS_MONTANT, "uncertainty": config.POIDS_INCERTITUDE},
        "amount_cap_tnd": config.MONTANT_PLAFOND,
        "formulas_modified": False,
        "source_files": ["service/scoring.py", "service/moteur.py", "service/ml.py", "service/config.py"],
    }


@app.post("/api/complaints")
def create_complaint(request: Request, body: ComplaintIn):
    user = user_from_request(request)
    if user["role"] != "SHOP":
        raise HTTPException(403, "Une boutique crée le signalement.")
    phone = telephone_normaliser(body.phone)
    con = db()
    try:
        cur = con.execute(
            """INSERT INTO complaint (boutique_id, phone_hash, phone_mask, motif, status, created_at, updated_at)
               VALUES (?,?,?,?, 'EN_ATTENTE', ?, ?)""",
            (user["boutique_id"], telephone.hacher(phone), mask_phone(phone), body.motif.strip(), now_iso(), now_iso()),
        )
        audit(con, user["email"], "COMPLAINT", f"Signalement #{cur.lastrowid} pour {mask_phone(phone)}.")
        con.commit()
        return {"id": cur.lastrowid, "status": "EN_ATTENTE"}
    finally:
        con.close()


@app.get("/api/complaints")
def list_complaints(request: Request, status: str = ""):
    user = user_from_request(request)
    con = db()
    try:
        clauses, params = [], []
        if user["role"] == "SHOP":
            clauses.append("c.boutique_id=?")
            params.append(user["boutique_id"])
        if status:
            clauses.append("c.status=?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = con.execute(
            f"""SELECT c.*, b.name AS shop FROM complaint c JOIN boutique b ON b.id=c.boutique_id
                {where} ORDER BY c.id DESC LIMIT 200""",
            params,
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        con.close()


@app.post("/api/contestations")
def create_contestation(request: Request, body: ComplaintIn):
    user = user_from_request(request)
    if user["role"] != "SHOP":
        raise HTTPException(403, "Une boutique ouvre la contestation.")
    phone = telephone_normaliser(body.phone)
    con = db()
    try:
        cur = con.execute(
            """INSERT INTO contestation (boutique_id, phone_hash, phone_mask, motif, status, created_at, updated_at)
               VALUES (?,?,?,?, 'OUVERTE', ?, ?)""",
            (user["boutique_id"], telephone.hacher(phone), mask_phone(phone), body.motif.strip(), now_iso(), now_iso()),
        )
        audit(con, user["email"], "CONTESTATION", f"Contestation #{cur.lastrowid} pour {mask_phone(phone)}.")
        con.commit()
        return {"id": cur.lastrowid, "status": "OUVERTE"}
    finally:
        con.close()


@app.get("/api/contestations")
def list_contestations(request: Request, status: str = ""):
    user = user_from_request(request)
    con = db()
    try:
        clauses, params = [], []
        if user["role"] == "SHOP":
            clauses.append("c.boutique_id=?")
            params.append(user["boutique_id"])
        if status:
            clauses.append("c.status=?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = con.execute(
            f"""SELECT c.*, b.name AS shop FROM contestation c JOIN boutique b ON b.id=c.boutique_id
                {where} ORDER BY c.id DESC LIMIT 200""",
            params,
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        con.close()


@app.patch("/api/admin/complaints/{item_id}")
def decide_complaint(item_id: int, request: Request, body: DecisionIn):
    user = require_admin(user_from_request(request))
    if body.status not in ("EN_ATTENTE", "CONFIRME", "REJETE"):
        raise HTTPException(422, "Statut de signalement invalide.")
    con = db()
    try:
        cur = con.execute(
            "UPDATE complaint SET status=?, admin_note=?, updated_at=? WHERE id=?",
            (body.status, body.note[:500], now_iso(), item_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Signalement introuvable.")
        audit(con, user["email"], "COMPLAINT_DECIDE", f"Signalement #{item_id} → {body.status}.")
        con.commit()
        return {"id": item_id, "status": body.status}
    finally:
        con.close()


@app.patch("/api/admin/contestations/{item_id}")
def decide_contestation(item_id: int, request: Request, body: DecisionIn):
    user = require_admin(user_from_request(request))
    if body.status not in ("OUVERTE", "EN_COURS", "ACCEPTEE", "REJETEE"):
        raise HTTPException(422, "Statut de contestation invalide.")
    con = db()
    try:
        cur = con.execute(
            "UPDATE contestation SET status=?, decision_note=?, updated_at=? WHERE id=?",
            (body.status, body.note[:500], now_iso(), item_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Contestation introuvable.")
        audit(con, user["email"], "CONTESTATION_DECIDE", f"Contestation #{item_id} → {body.status}.")
        con.commit()
        return {"id": item_id, "status": body.status}
    finally:
        con.close()


@app.get("/api/admin/boutiques")
def admin_boutiques(request: Request):
    require_admin(user_from_request(request))
    con = db()
    try:
        rows = con.execute(
            """SELECT b.*, (SELECT COUNT(*) FROM customer_order o WHERE o.boutique_id=b.id) AS orders,
                      (SELECT COUNT(*) FROM users u WHERE u.boutique_id=b.id) AS users
               FROM boutique b ORDER BY b.id"""
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        con.close()


@app.post("/api/admin/boutiques")
def admin_create_boutique(request: Request, body: BoutiqueIn):
    user = require_admin(user_from_request(request))
    con = db()
    try:
        cur = con.execute(
            "INSERT INTO boutique (name, governorate, city, address, active, created_at) VALUES (?,?,?,?,?,?)",
            (body.name.strip(), body.governorate.strip(), body.city.strip(), body.address.strip(), 1 if body.active else 0, now_iso()),
        )
        audit(con, user["email"], "BOUTIQUE_CREATE", f"Boutique {body.name} créée.")
        con.commit()
        return {"id": cur.lastrowid}
    finally:
        con.close()


@app.patch("/api/admin/boutiques/{boutique_id}")
def admin_patch_boutique(boutique_id: int, request: Request, active: Optional[bool] = None, name: Optional[str] = None):
    user = require_admin(user_from_request(request))
    con = db()
    try:
        row = con.execute("SELECT * FROM boutique WHERE id=?", (boutique_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Boutique introuvable.")
        if active is not None:
            con.execute("UPDATE boutique SET active=? WHERE id=?", (1 if active else 0, boutique_id))
        if name:
            con.execute("UPDATE boutique SET name=? WHERE id=?", (name.strip(), boutique_id))
        audit(con, user["email"], "BOUTIQUE_UPDATE", f"Boutique #{boutique_id} mise à jour.")
        con.commit()
        return {"ok": True}
    finally:
        con.close()


@app.get("/api/admin/users")
def admin_users(request: Request):
    require_admin(user_from_request(request))
    con = db()
    try:
        rows = con.execute(
            """SELECT u.id, u.email, u.full_name, u.role, u.active, u.boutique_id, b.name AS shop
               FROM users u LEFT JOIN boutique b ON b.id=u.boutique_id ORDER BY u.id"""
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        con.close()


@app.post("/api/admin/users")
def admin_create_user(request: Request, body: UserIn):
    user = require_admin(user_from_request(request))
    if body.role not in ("ADMIN", "SHOP"):
        raise HTTPException(422, "Rôle invalide.")
    if body.role == "SHOP" and not body.boutique_id:
        raise HTTPException(422, "Une boutique est requise.")
    con = db()
    try:
        salt = secrets.token_bytes(16)
        dk = hashlib.pbkdf2_hmac("sha256", body.password.encode(), salt, 120_000)
        stored = salt.hex() + "$" + dk.hex()
        try:
            cur = con.execute(
                """INSERT INTO users (email, password, full_name, role, boutique_id, active)
                   VALUES (?,?,?,?,?,1)""",
                (body.email.strip().lower(), stored, body.full_name.strip(), body.role, body.boutique_id),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Cet e-mail existe déjà.")
        audit(con, user["email"], "USER_CREATE", f"Compte {body.email} ({body.role}).")
        con.commit()
        return {"id": cur.lastrowid}
    finally:
        con.close()


@app.patch("/api/admin/users/{user_id}")
def admin_patch_user(user_id: int, request: Request, active: Optional[bool] = None):
    user = require_admin(user_from_request(request))
    if user["id"] == user_id and active is False:
        raise HTTPException(409, "Vous ne pouvez pas désactiver votre propre compte.")
    con = db()
    try:
        cur = con.execute("UPDATE users SET active=? WHERE id=?", (1 if active else 0, user_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "Utilisateur introuvable.")
        audit(con, user["email"], "USER_UPDATE", f"Utilisateur #{user_id} active={active}.")
        con.commit()
        return {"ok": True}
    finally:
        con.close()


@app.get("/api/admin/stats")
def admin_stats(request: Request):
    require_admin(user_from_request(request))
    con = db()
    try:
        global_dash = dashboard_for(con, None)
        per = []
        for b in con.execute("SELECT id, name, governorate, city, active FROM boutique ORDER BY id"):
            d = dashboard_for(con, b["id"])
            per.append({
                "id": b["id"], "name": b["name"], "governorate": b["governorate"], "city": b["city"],
                "active": bool(b["active"]), "orders": d["totals"]["orders"], "customers": d["customers"],
                "mean_score": d["mean_score"], "high_priority_pending": d["high_priority_pending"],
                "cold_start_pct": d["cold_start_pct"], "risk": d["risk"],
            })
        return {"global": global_dash, "boutiques": per}
    finally:
        con.close()


@app.get("/api/admin/settings")
def get_settings(request: Request):
    require_admin(user_from_request(request))
    return {"values": current_settings(), "defaults": DEFAULTS,
            "note": "Ces paramètres sont ceux lus par le moteur en mémoire (config.py). Les formules de scoring.py et moteur.py ne sont pas modifiées. Réinitialiser restaure les constantes du Sprint 1."}


@app.put("/api/admin/settings")
def put_settings(request: Request, payload: dict):
    user = require_admin(user_from_request(request))
    clean = validate_settings(payload)
    con = db()
    try:
        for key, value in clean.items():
            con.execute(
                "INSERT INTO score_settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )
            setattr(config, key, value)
        audit(con, user["email"], "SETTINGS", "Paramètres du moteur mis à jour (démo, en mémoire + base démo).")
        con.commit()
        return {"values": current_settings()}
    finally:
        con.close()


@app.post("/api/admin/settings/reset")
def reset_settings(request: Request):
    user = require_admin(user_from_request(request))
    con = db()
    try:
        con.execute("DELETE FROM score_settings")
        for key, value in DEFAULTS.items():
            setattr(config, key, value)
        audit(con, user["email"], "SETTINGS_RESET", "Retour aux constantes du Sprint 1.")
        con.commit()
        return {"values": current_settings()}
    finally:
        con.close()


@app.get("/api/admin/audit")
def admin_audit(request: Request):
    require_admin(user_from_request(request))
    con = db()
    try:
        rows = con.execute(
            "SELECT id, actor_email, action, details, created_at FROM audit_log ORDER BY id DESC LIMIT 200"
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        con.close()


@app.get("/api/notifications")
def notifications(request: Request):
    user = user_from_request(request)
    con = db()
    try:
        if user["role"] == "ADMIN":
            n = con.execute("SELECT COUNT(*) n FROM complaint WHERE status='EN_ATTENTE'").fetchone()["n"]
            rows = con.execute(
                "SELECT id, motif, phone_mask, created_at FROM complaint WHERE status='EN_ATTENTE' ORDER BY id DESC LIMIT 6"
            ).fetchall()
        else:
            n = con.execute(
                "SELECT COUNT(*) n FROM complaint WHERE status='EN_ATTENTE' AND boutique_id=?",
                (user["boutique_id"],),
            ).fetchone()["n"]
            rows = con.execute(
                """SELECT id, motif, phone_mask, created_at FROM complaint
                   WHERE status='EN_ATTENTE' AND boutique_id=? ORDER BY id DESC LIMIT 6""",
                (user["boutique_id"],),
            ).fetchall()
        return {"count": n, "items": [dict(r) for r in rows]}
    finally:
        con.close()


app.mount("/samples", StaticFiles(directory=os.path.join(SERVICE, "exemples")), name="samples")
app.mount("/", StaticFiles(directory=WEB, html=True), name="web")


def main():
    if not os.path.exists(DB_PATH):
        from demo.seed import build
        print(build(DB_PATH))
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))


if __name__ == "__main__":
    main()
