# API Simulateur TCF Canada

API d'évaluation automatique de l'épreuve d'Expression Écrite du **TCF Canada**, propulsée par **Mistral AI** (LLM) et **Qdrant** (RAG vectoriel).

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Frontend   │────▶│  FastAPI     │────▶│  Mistral AI │
│  (React)    │     │  (Python)    │     │  (LLM)      │
└─────────────┘     └──────┬───────┘     └─────────────┘
                           │ RAG
                    ┌──────▼───────┐
                    │  Qdrant      │
                    │  (Vector DB) │
                    └──────────────┘
```

| Couche | Technologie | Rôle |
|--------|-------------|------|
| API | FastAPI (Python 3.14) | Endpoints REST, sécurité, orchestration |
| LLM | Mistral Large (mistral-large-latest) | Évaluation des productions écrites |
| RAG | Qdrant Cloud + embeddings Mistral | Contexte méthodologique et exemples |
| Auth | API Key (X-API-Key) + JWT (OAuth2) | Sécurisation des endpoints |

## Structure du projet

```
api-simulateur-ec-tcf/
├── api_app/                        # Application FastAPI
│   ├── main.py                     # Point d'entrée, montage des routes
│   ├── core/
│   │   └── security.py             # Auth : clé API + JWT
│   ├── routes/
│   │   ├── evaluation.py           # POST /api/v1/tcf/evaluation-complete
│   │   └── auth.py                 # POST /api/v1/auth/token
│   └── services/
│       ├── llm_service.py          # Orchestrateur LLM + grille CECRL/NCLC
│       └── rag_service.py          # RAG : embeddings Mistral + Qdrant
├── data_pipeline/                  # Pipeline de génération et ingestion
│   ├── datasets/                   # Copies brutes et évaluées (JSONL)
│   ├── generation/                 # Scripts de génération synthétique
│   └── methodology_docs/           # PDF méthodologie TCF
├── tests/
│   └── test_tcf_service.py         # 14 tests (unitaires + intégration)
├── requirements.txt                # Dépendances Python
├── pyproject.toml                  # Configuration pytest
└── .env                            # Variables d'environnement (non versionné)
```

## Prérequis

- Python 3.10+
- Compte [Mistral AI](https://console.mistral.ai/) (clé API)
- Compte [Qdrant Cloud](https://cloud.qdrant.io/) (URL + clé API)
- Clés configurées dans le fichier `.env`

## Installation

```bash
# 1. Cloner le dépôt
git clone <url-du-depot>
cd api-simulateur-ec-tcf

# 2. Créer l'environnement virtuel
python -m venv venv
# Windows : venv\Scripts\activate
# Linux/macOS : source venv/bin/activate

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer les variables d'environnement
# Créer un fichier .env (voir .env.example)
```

### Variables d'environnement (`.env`)

| Variable | Description |
|----------|-------------|
| `MISTRAL_API_KEY` | Clé API Mistral AI |
| `QDRANT_URL` | URL de l'instance Qdrant Cloud |
| `QDRANT_API_KEY` | Clé API Qdrant Cloud |
| `TCF_API_KEY` | Clé API pour sécuriser l'endpoint d'évaluation |
| `GROQ_API_KEY` | (Optionnelle) Pour la génération de datasets |

## Lancement

```bash
# Développement
uvicorn api_app.main:app --reload --port 8000

# Production
uvicorn api_app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

L'API est alors accessible sur `http://localhost:8000`.

- Documentation interactive : `http://localhost:8000/docs`
- Documentation OpenAPI : `http://localhost:8000/redoc`
- Health check : `http://localhost:8000/`

## Tests

```bash
pytest tests/ -v
```

14 tests (13 unitaires + 1 intégration mockée).

---

# Documentation complète de l'API

## Endpoints

### 1. Health Check

```
GET /
```

**Réponse :**
```json
{"status": "online"}
```

---

### 2. Authentification JWT

```
POST /api/v1/auth/token
```

Obtient un token JWT pour les requêtes nécessitant une auth OAuth2 (endpoint /token uniquement ; l'endpoint d'évaluation utilise la clé API).

**Body** (form-urlencoded) :
| Champ | Valeur |
|-------|--------|
| `username` | `admin_tcf` |
| `password` | `tcf_password_2026` |

**Réponse :**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

---

### 3. Évaluation complète (endpoint principal)

```
POST /api/v1/tcf/evaluation-complete
```

Header requis : `X-API-Key: <votre_cle_api_tcf>`

Évalue les 3 tâches de l'épreuve d'Expression Écrite du TCF Canada.

#### Schéma de la requête

```json
{
  "tache_1": {
    "consigne_sujet": "string",
    "texte_candidat": "string",
    "documents_contexte": ["string"]
  },
  "tache_2": {
    "consigne_sujet": "string",
    "texte_candidat": "string",
    "documents_contexte": ["string"]
  },
  "tache_3": {
    "consigne_sujet": "string",
    "texte_candidat": "string",
    "documents_contexte": ["string"]
  }
}
```

Chaque tâche est optionnelle (`null` pour une tâche non soumise). Les barèmes par tâche :

| Tâche | Type | Barème | Longueur attendue |
|-------|------|--------|-------------------|
| 1 | Récit / Description (lettre amicale) | /4 | 60-120 mots |
| 2 | Article / Lettre formelle | /7 | 120-150 mots |
| 3 | Synthèse et argumentation | /9 | 120-180 mots |

`documents_contexte` est uniquement pertinent pour la Tâche 3 (synthèse).

#### Schéma de la réponse

```json
{
  "status": "success",
  "meta": {
    "exam": "TCF Canada",
    "epreuve": "Expression écrite",
    "date_evaluation": "2026-07-01T12:00:00Z",
    "version_analyse": "1.0.0",
    "mode": "evaluation_complete"
  },
  "bilan_global": {
    "score": {
      "sur_20": 12.5,
      "pourcentage": 62,
      "mention": "Assez Bien"
    },
    "niveau": {
      "cecrl": "B2",
      "nclc": "8"
    },
    "resume": "Bilan global consolidé basé sur les épreuves soumises.",
    "points_forts": [],
    "priorites_progression": []
  },
  "evaluations": [
    {
      "tache": 1,
      "consigne": "string",
      "copie": {
        "texte_original": "string",
        "nombre_mots": 85
      },
      "score": {
        "obtenu": 3.0,
        "maximum": 4
      },
      "niveau_estime": {
        "cecrl": "B2",
        "nclc": "7"
      },
      "controle_methodologie": {
        "respect_nombre_mots": true,
        "structure_attendue": true,
        "registre_adapte": true,
        "paragraphes": true,
        "connecteurs": true,
        "salutation": true,
        "signature": true,
        "titre": true,
        "conclusion": true
      },
      "analyse": {
        "comprehension_sujet": { "note": 0.0, "commentaire": "" },
        "respect_methodologie": { "note": 0.0, "commentaire": "" },
        "coherence_cohesion": { "note": 0.0, "commentaire": "" },
        "lexique": { "note": 0.0, "commentaire": "" },
        "grammaire": { "note": 0.0, "commentaire": "" },
        "orthographe": { "note": 0.0, "commentaire": "" }
      },
      "statistiques": {
        "richesse_lexicale": { "score": 0, "niveau": "", "commentaire": "" },
        "complexite_syntaxique": { "score": 0, "niveau": "", "commentaire": "" },
        "fluidite": { "score": 0, "niveau": "", "commentaire": "" }
      },
      "erreurs": [
        {
          "id": 1,
          "gravite": "Moyenne",
          "type": "Grammaire",
          "segment_original": "",
          "correction": "",
          "explication": "",
          "regle": "",
          "exemple": ""
        }
      ],
      "versions": {
        "version_corrigee": "",
        "version_modele_c1": ""
      },
      "coaching": {
        "points_forts": [],
        "points_a_ameliorer": [],
        "conseils": [],
        "objectif_prochaine_copie": ""
      }
    }
  ]
}
```

#### Exemple avec curl

```bash
curl -X POST http://localhost:8000/api/v1/tcf/evaluation-complete \
  -H "Content-Type: application/json" \
  -H "X-API-Key: tcf_secret_dev_key_2026" \
  -d '{
    "tache_1": {
      "consigne_sujet": "Vous avez récemment déménagé dans une nouvelle ville. Écrivez une lettre à un ami pour lui décrire votre nouveau quartier et l'inviter à vous rendre visite.",
      "texte_candidat": "Cher ami, Je viens de m'installer à Lyon et je dois dire que la ville est magnifique ! Mon quartier est animé avec des petits cafés partout. Tu devrais venir me voir le week-end prochain, je te ferai visiter les environs. À bientôt, Marc",
      "documents_contexte": []
    },
    "tache_2": {
      "consigne_sujet": "Vous avez décidé d'arrêter d'utiliser les réseaux sociaux. Écrivez un article pour expliquer les raisons de votre décision et ses effets sur votre vie quotidienne.",
      "texte_candidat": "Pourquoi j'ai quitté les réseaux sociaux...",
      "documents_contexte": []
    },
    "tache_3": null
  }'
```

#### Codes d'erreur

| Code | Signification |
|------|---------------|
| 200 | Succès |
| 403 | Clé API manquante ou invalide (header `X-API-Key`) |
| 422 | Données invalides (validation Pydantic) |
| 500 | Erreur interne (LLM / RAG) |

---

## Grille de notation CECRL / NCLC

### Barème global (note sur 20)

| Note | CECRL | NCLC | Mention |
|------|-------|------|---------|
| 18-20 | C2 | 10+ | Excellent |
| 16-17 | C1 | 10+ | Très Bien |
| 14-15 | C1 | 9 | Bien |
| 12-13 | B2 | 8 | Assez Bien |
| 10-11 | B2 | 7 | Passable |
| 7-9 | B1 | 6 | Médiocre |
| 6 | B1 | 5 | Insuffisant |
| 4-5 | A2 | 4 | Très Insuffisant |
| 0-3 | A1 | 3 | À renforcer |

### Projection par tâche

Chaque tâche est notée sur son propre barème (4, 7 ou 9 points), puis projetée proportionnellement sur 20 via `(obtenu / max) × 20` pour déterminer le niveau CECRL/NCLC de la tâche.

---

## Pipeline de données

### Scripts de génération (`data_pipeline/generation/`)

| Script | Description |
|--------|-------------|
| `generate_candidates.py` | Génère des copies synthétiques via Mistral AI |
| `generate_candidates111.py` | Génération avec support Groq/Mistral |
| `generate_dataset.py` | Production de dataset via Groq |
| `evaluate_copies.py` | Évaluation des copies par Mistral |
| `ingest_methodology.py` | Chunking et ingestion du PDF méthodo dans Qdrant |
| `ingest_to_qdrant.py` | Ingestion des copies évaluées dans Qdrant |
| `validate_dataset.py` | Validation de la cohérence du dataset |

### Datasets (`data_pipeline/datasets/`)

| Fichier | Contenu |
|---------|---------|
| `copies_candidates_brutes.jsonl` | 790 copies brutes (A1-C1) |
| `copies_candidates_brutes1.jsonl` | 171 copies brutes (A1-C1) |
| `copies_evaluees.jsonl` | 787 copies avec évaluations expertes |
| `text_file.json` | Exemple de tâche 1 |

### Collections Qdrant

| Collection | Contenu | Usage |
|------------|---------|-------|
| `tcf_methodologie` | Règles de barème et consignes (Top 3) | Contexte pour le LLM |
| `tcf_copies_dataset` | Copies évaluées avec filtrage par `tache_id` (Top 2) | Few-shot pour le LLM |

---

## Déploiement

### Render / Railway / Fly.io

```bash
# Commandes de démarrage typiques
uvicorn api_app.main:app --host 0.0.0.0 --port $PORT
```

Variables d'environnement requises sur la plateforme :
- `MISTRAL_API_KEY`
- `QDRANT_URL`
- `QDRANT_API_KEY`
- `TCF_API_KEY`

### Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "api_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
