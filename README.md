# TrustOrder AI

Système d'aide à la décision pour la gestion du risque client en e-commerce (paiement à la livraison).

Le service évalue la fiabilité d'un client à partir de son historique de commandes (règles métier + Machine Learning) et priorise les commandes à vérifier.

## Architecture

```
trustorder-ai/
├── service/          → API Python FastAPI (cœur métier + IA)
│   ├── scoring.py    → score de fiabilité (règles)
│   ├── ml.py         → modèle de Machine Learning
│   ├── moteur.py     → orchestration (analyse + priorisation)
│   ├── main.py       → endpoints HTTP
│   └── tests/        → 3 tests (unitaire, intégration, fonctionnel)
├── web/              → Interface web simple
├── demo/             → Serveur de démonstration tout-en-un
├── backend/          → Backend Symfony (optionnel, architecture propre)
└── data/             → Base de démo
```

## Prérequis

- Python **3.10+**
- (optionnel) PHP 8.2+ + Composer pour le backend Symfony

## Installation rapide

```bash
# 1. Cloner le dépôt
git clone https://github.com/VOTRE_COMPTE/trustorder-ai.git
cd trustorder-ai

# 2. Créer un environnement virtuel
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

# 3. Installer les dépendances
pip install -r service/requirements.txt
```

## Lancer le projet

### Option A — API seule (recommandée pour le développement)

```bash
cd service
uvicorn main:app --reload --port 8001
```

Ouvrir : [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs) (Swagger)

### Option B — Démo complète (API + interface web)

```bash
cd demo
python server.py
```

Ouvrir : [http://127.0.0.1:8080](http://127.0.0.1:8080)

## Les 3 tests demandés

| Type            | Fichier                         | Ce qui est testé                          |
|-----------------|---------------------------------|-------------------------------------------|
| **Unitaire**    | `tests/test_unitaire.py`        | Fonction pure `calculer_score`            |
| **Intégration** | `tests/test_integration.py`     | Modules `scoring` + `ml` + `moteur`       |
| **Fonctionnel** | `tests/test_fonctionnel.py`     | Endpoint HTTP `/v1/analyze` (bout-en-bout)|

Lancer les tests :

```bash
cd service
pytest tests/ -v
```

## GitHub Actions (CI/CD)

À chaque push ou pull request sur `main` / `master`, GitHub Actions :

1. Installe Python et les dépendances
2. Lance les **3 tests**
3. Affiche le résultat (vert = OK)

Le workflow se trouve dans `.github/workflows/ci.yml`.

## Endpoints principaux

| Méthode | URL                  | Description                              |
|---------|----------------------|------------------------------------------|
| GET     | `/health`            | Santé du service                         |
| POST    | `/v1/analyze`        | Analyse d'un client (score + risque)     |
| POST    | `/v1/prioritize`     | Priorisation d'une commande              |
| POST    | `/v1/prioritize/batch` | Priorisation d'un lot de commandes     |

## Exemple d'appel

```bash
curl -X POST http://127.0.0.1:8001/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "customer_ref": "C001",
    "history": {
      "delivered_orders": 12,
      "refused_orders": 1,
      "not_collected_orders": 0,
      "recent_failed_90d": 0,
      "distinct_shops": 2,
      "reports_count": 0
    }
  }'
```

## Auteur

Projet académique — TrustOrder AI
