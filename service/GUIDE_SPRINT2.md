# TrustOrder AI — Sprint 2 : données, import et OCR (pour débutants)

## L'idée en une phrase
Le Sprint 1 savait **juger** un client. Le Sprint 2 lui apprend à **recevoir des données réelles** :
lire les fichiers des boutiques, corriger les erreurs, enregistrer les commandes, puis retrouver l'historique d'un numéro.

## Le parcours d'une commande importée

```
 Fichier Excel/CSV ──┐
                     ├─► 1. IMPORT ─► 2. VÉRIFICATION ─► 3. CORRECTION ─► 4. ENREGISTREMENT ─► 5. AGRÉGATION ─► SCORE (Sprint 1)
 PDF / photo (OCR) ──┘   (lire)        (contrôler)        (réparer)         (base de données)    (par numéro)
```

| Étape | User story | Fichier | Ce que ça fait |
|---|---|---|---|
| Import Excel/CSV | US06 | `import_fichier.py` | Retrouve seul les colonnes (téléphone, statut, montant, date), même si les titres changent |
| Import PDF/image | US07 | `ocr.py` | Lit le texte d'un PDF ou d'une photo (OCR) et repère numéro, statut, montant, date |
| Vérification | US08 | `verification.py` | Contrôle chaque ligne : **erreur** (bloquante) ou **avertissement** |
| Correction | US08 | `routes_sprint2.py` | Corriger ou ignorer une ligne, puis valider le lot |
| Agrégation | US09 | `stockage.py` | Regroupe toutes les commandes d'un numéro (toutes boutiques) en un historique |
| Recherche | US09 | `clients.py` | Un numéro → historique + score + prédiction |
| Vérification en masse | US10 | `clients.py` | Une liste de numéros → une analyse par numéro + un résumé + export CSV |
| Réentraînement | — | `reentrainement.py` | Réentraîne le modèle ML sur les vraies commandes enregistrées |

Fichiers utilitaires : `telephone.py` (normaliser et hacher un numéro), `normalisation.py` (statuts, montants, dates),
`sql_mysql.sql` (les mêmes tables pour MySQL/Symfony).
Les fichiers du Sprint 1 (`config.py`, `scoring.py`, `ml.py`, `moteur.py`) sont inchangés, sauf `ml.py` qui peut maintenant s'entraîner sur de vraies données.

## Lancer le projet (Windows, dans le dossier du projet)

```
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
python demo_sprint2.py
uvicorn main:app --reload --port 8001
```
Ouvrez http://127.0.0.1:8001/docs. Tests : `pytest -q` (44 tests).

`python demo_sprint2.py` déroule tout le parcours sans serveur sur les fichiers du dossier `exemples/` : lisez sa sortie en premier.

## Tester l'import dans Swagger (/docs)
1. Ouvrez `POST /v2/import/fichier` → **Try it out** → `boutique_id` = 1 → choisissez `exemples/commandes_exemple.csv` → **Execute**.
2. Dans la réponse : `summary` (combien de lignes valides / en erreur), `lines` (chaque ligne avec ses `issues`) et `lot_id` (à garder).
3. Corrigez : `PATCH /v2/lots/{lot_id}/lignes/{n}` avec `{"phone": "20 444 555"}` (ligne 16) puis `{"ignore": true}` (ligne 17).
4. Enregistrez : `POST /v2/lots/{lot_id}/valider`.
5. Cherchez : `GET /v2/clients?telephone=55 333 444` → un client à risque HIGH.
6. Vérifiez une liste : `POST /v2/verification/masse/fichier` avec `exemples/numeros_a_verifier.csv`
   (ajoutez `?format=csv` pour télécharger le résultat, lisible dans Excel).

## Installer l'OCR (seulement pour les photos et les PDF scannés)
- Les **PDF contenant du texte** et les fichiers **Excel/CSV** fonctionnent sans rien installer.
- Pour les **images** (png, jpg) et les **PDF scannés**, installez Tesseract (gratuit) : programme d'installation Windows de
  « UB Mannheim » (cherchez *Tesseract at UB Mannheim*), en cochant la langue **French** à l'installation.
- Si le programme n'est pas trouvé, indiquez son chemin avant de lancer le serveur :
  `set TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe`
- Sans Tesseract, l'API répond clairement « Tesseract n'est pas installé » (code 503) au lieu de planter.

## Comprendre les « problèmes » d'une ligne
| Niveau | Exemple | Conséquence |
|---|---|---|
| `error` | Numéro invalide, statut non reconnu (« annulé »), montant ou date illisible | La ligne n'est **pas** enregistrée tant qu'elle n'est pas corrigée (ou ignorée) |
| `warning` | Statut/montant/date absent, doublon, extraction OCR incertaine | La ligne est enregistrée, mais regardez-la |

Reimporter le même fichier ne crée **aucun doublon** : chaque commande a une empreinte unique. Une commande « en attente »
est automatiquement mise à jour quand un nouvel import donne son issue (livrée, refusée...).

## Réentraîner le modèle sur les vraies commandes
```
python reentrainement.py            (il faut au moins 300 exemples réels, sinon le modèle actuel est conservé)
python reentrainement.py --min 100  (pour tester avec moins)
```
Redémarrez ensuite le serveur. Un « exemple » = une commande à partir de la 6e d'un client : le modèle apprend à prédire
si elle sera récupérée d'après ce qu'on savait **avant**.

## Exercices
1. Ouvrez `exemples/commandes_exemple.csv` dans un éditeur de texte, changez le titre « N° Tel » en « Mobile client », relancez la démo : les colonnes sont-elles encore retrouvées ?
2. Ajoutez le mot « paye » comme statut dans `normalisation.py` pour `REFUSED` : que devient le test `test_statuts_et_negations` ?
3. Dans `config.py`, passez `JOURS_ECHECS_RECENTS` à 30 : le score du client « 55 333 444 » change-t-il ?
4. Importez `exemples/bordereau_scan_exemple.png` (avec Tesseract) et comparez avec `bordereau_exemple.pdf`.

## Limites à connaître
- **Base SQLite de démonstration** (`trustorder.db`) : en production, Symfony enregistre dans MySQL avec les mêmes tables (`sql_mysql.sql`).
- **Pas d'authentification** : `boutique_id` est envoyé dans la requête. Le JWT arrive au Sprint 3 ; n'exposez pas ce service sur Internet.
- **Secret de hachage** : changez `TRUSTORDER_SECRET` en production et ne le modifiez plus ensuite, sinon les historiques deviennent introuvables.
- **Numéros tunisiens uniquement** (8 chiffres, indicatif 216).
- **Doublons** : la même commande importée avec un libellé différent (par exemple depuis un CSV puis un bordereau) sera comptée deux fois.
- **OCR** : la confiance affichée est une estimation simple (numéro + statut + montant + date trouvés), pas une garantie. Vérifiez toujours les lignes extraites.
- **Statuts** : la correspondance (« retour » = refusée, « injoignable » = non récupérée...) est une proposition à valider avec le Product Owner.
- Le fichier `.xls` (ancien Excel) n'est pas lu : enregistrez-le en `.xlsx` ou `.csv`.
