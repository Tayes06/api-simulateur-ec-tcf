# API Simulateur TCF Canada

API de préparation au **TCF Canada** (France Éducation International), couvrant :

- **Expression Écrite** — évaluation automatique des 3 tâches (note /20, niveau CECRL/NCLC, analyse par critère, corrections, coaching)
- **Expression Orale** — génération de fiches de correction pédagogique pour la Tâche 2 (interaction) et la Tâche 3 (dialectique / analytique)

Propulsée par **Google Gemini** (LLM), **Qdrant** (RAG vectoriel) et **Mistral AI** (embeddings).

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  Frontend   │────▶│  FastAPI     │────▶│  Gemini API  │
│  (React)    │     │  (Python)    │     │  (LLM)       │
└─────────────┘     └──────┬───────┘     └──────────────┘
                           │ RAG
                    ┌──────▼───────┐     ┌──────────────┐
                    │  Qdrant      │◀────│  Mistral AI  │
                    │  (Vector DB) │     │  (embeddings)│
                    └──────────────┘     └──────────────┘
```

| Couche | Technologie | Rôle |
|--------|-------------|------|
| API | FastAPI (Python 3.14 en dev, 3.12 en Docker) | Endpoints REST, sécurité, orchestration |
| LLM | Gemini `gemini-3.8-flash` (SDK `google-genai`) | Évaluation des copies + fiches orales (JSON contraint, T=0.0) |
| RAG | Qdrant Cloud + embeddings `mistral-embed` | Contexte méthodologique et exemples (1024 dims) |
| Auth | API Key (X-API-Key) | Sécurisation des endpoints métier |

## Structure du projet

```
api-simulateur-ec-tcf/
├── api_app/                        # Application FastAPI
│   ├── main.py                     # Point d'entrée, montage des routeurs
│   ├── core/
│   │   └── security.py             # Auth : clé API (X-API-Key)
│   ├── prompts/
│   │   └── oral_prompts.py         # Prompts système Expression Orale
│   ├── routes/
│   │   ├── evaluation.py           # POST /api/v1/tcf/evaluation-complete
│   │   ├── oral_correction.py      # POST /api/v1/oral/generate-corrections | regenerate-correction
│   │   └── auth.py                 # ⚠ code mort — jamais monté
│   ├── schemas/
│   │   └── oral.py                 # Schémas Pydantic Expression Orale
│   └── services/
│       ├── llm_service.py          # Orchestrateur LLM (Gemini) + grille CECRL/NCLC
│       └── rag_service.py          # RAG : embeddings Mistral + Qdrant
├── data_pipeline/                  # Pipeline de génération et ingestion
│   ├── datasets/                   # Copies brutes et évaluées (JSONL)
│   ├── generation/                 # Scripts de génération synthétique
│   └── methodology_docs/           # PDF méthodologie (écrit + oral)
├── tests/
│   └── test_tcf_service.py         # 14 tests (13 passent, 1 échoue)
├── docker-compose.vps-sim.yml      # Simulateur Ollama local (optionnel)
├── requirements.txt                # Dépendances Python
├── pyproject.toml                  # Configuration pytest
└── .env                            # Variables d'environnement (non versionné)
```

## Prérequis

- Python 3.10+
- Compte [Google AI Studio](https://aistudio.google.com/) (clé API Gemini)
- Compte [Mistral AI](https://console.mistral.ai/) (clé API — embeddings uniquement)
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
# ⚠ Pensez aussi à installer google-genai (absent de requirements.txt) :
pip install google-genai

# 4. Configurer les variables d'environnement
# Créer un fichier .env (voir .env.example)
```

### Variables d'environnement (`.env`)

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Clé API Google Gemini (**obligatoire** — LLM écrit + oral) |
| `LLM_MODEL_NAME` | (Optionnelle) Modèle Gemini, défaut `gemini-3.8-flash` |
| `MAX_CONCURRENT_LLM_CALLS` | (Optionnelle) Concurrence LLM, défaut `3` |
| `MISTRAL_API_KEY` | Clé API Mistral (embeddings RAG) |
| `QDRANT_URL` | URL de l'instance Qdrant Cloud |
| `QDRANT_API_KEY` | Clé API Qdrant Cloud |
| `TCF_API_KEY` | Clé API pour sécuriser les endpoints métier |
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

14 tests (13 unitaires + 1 intégration) — **état actuel : 13 passent, 1 échoue** (la fixture du test d'intégration ne respecte pas le contrat de réponse). Le test d'intégration requiert `GEMINI_API_KEY` dans l'environnement et contacte réellement Qdrant.

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

### 2. Évaluation Expression Écrite (endpoint principal)

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

`documents_contexte` est uniquement pertinent pour la Tâche 3 (synthèse) — seuls les 2 premiers éléments sont utilisés.

#### Schéma de la réponse

```json
{
  "status": "success",
  "meta": {
    "exam": "TCF Canada",
    "epreuve": "Expression écrite",
    "date_evaluation": "2026-10-18T12:00:00Z",
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
      "nombre_mots_candidat": 85,
      "nombre_mots_exemple": 112,
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
        "version_modele_c2": ""
      },
      "coaching": {
        "points_forts": [],
        "points_a_ameliorer": [],
        "conseils": [],
        "objective_prochaine_copie": ""
      }
    }
  ]
}
```

> ⚠️ Points de vigilance côté client :
> - le champ modèle s'appelle `version_modele_**c2**` (et non `_c1`) ;
> - le coaching utilise `objective_prochaine_copie` (avec un « e », tel que le LLM le renvoie) ;
> - `nombre_mots_candidat` / `nombre_mots_exemple` sont absents des tâches non soumises ;
> - sur une tâche non soumise, `analyse` et `statistiques` sont des objets vides `{}` ;
> - le score global est toujours normalisé sur /20, même si une seule tâche est soumise.

#### Exemple avec curl

```bash
curl -X POST http://localhost:8000/api/v1/tcf/evaluation-complete \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $TCF_API_KEY" \
  -d '{
    "tache_1": {
      "consigne_sujet": "Vous avez récemment déménagé dans une nouvelle ville. Écrivez une lettre à un ami pour lui décrire votre nouveau quartier et l''inviter à vous rendre visite.",
      "texte_candidat": "Cher ami, Je viens de m installer à Lyon et je dois dire que la ville est magnifique ! Mon quartier est animé avec des petits cafés partout. Tu devrais venir me voir le week-end prochain, je te ferai visiter les environs. À bientôt, Marc",
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
| 500 | Erreur interne (Gemini / RAG) |

---

### 3. Fiches de correction Expression Orale (batch)

```
POST /api/v1/oral/generate-corrections
```

Header requis : `X-API-Key: <votre_cle_api_tcf>`

Génère des fiches de correction pédagogique pour une liste de sujets d'Expression Orale (Tâche 2 : interaction ; Tâche 3 : dialectique ou analytique).

**Schéma de la requête :**

```json
{
  "topics": [
    {
      "id": "sujet-001",
      "task_type": "TASK_2",
      "content": "Vous suivez des cours de cuisine. Appelez le centre pour connaître les horaires et les tarifs."
    },
    {
      "id": "sujet-002",
      "task_type": "TASK_3",
      "task3_type": "DIALECTICAL",
      "content": "Les photos sur le CV, pour ou contre ?"
    }
  ]
}
```

| Champ | Valeurs |
|-------|---------|
| `task_type` | `TASK_2` ou `TASK_3` |
| `task3_type` | `DIALECTICAL` ou `ANALYTICAL` (à renseigner pour `TASK_3`) |
| `id` | identifiant libre du côté applicatif |
| `content` | la consigne / l'intitulé du sujet |

**Schéma de la réponse :**

```json
{
  "status": "success",
  "total_processed": 2,
  "corrections": [
    {
      "topic_id": "sujet-001",
      "task_type": "TASK_2",
      "task3_type": null,
      "correction": {
        "context": "Mise en situation…",
        "understanding": "Enjeux…",
        "objective": "Objectif du candidat…",
        "expected_information": ["…"],
        "suggested_questions": ["…"],
        "possible_interaction": [
          { "role": "Candidat", "texte": "Bonjour Monsieur…" },
          { "role": "Examinateur", "texte": "Bonjour ! …" }
        ],
        "useful_expressions": ["…"],
        "common_mistakes": ["…"]
      }
    }
  ]
}
```

Pour `TASK_3`, le bloc `correction` contient selon le sous-type :
- **DIALECTICAL** : `topic_analysis`, `problematic`, `position_example`, `arguments[]` (`argument` / `explanation` / `example`), `counter_argument`, `conclusion_example`, `useful_expressions[]`, `common_mistakes[]`
- **ANALYTICAL** : `topic_analysis`, `axes_of_development[]`, `plan[]`, `arguments[]`, `examples[]`, `conclusion_example`, `useful_expressions[]`, `common_mistakes[]`

Contrairement à l'écrit, la réponse est **validée par Pydantic** : un échec de conformité du LLM remonte en `500`.

#### Codes d'erreur

| Code | Signification |
|------|---------------|
| 200 | Succès |
| 403 | Clé API manquante ou invalide |
| 422 | Payload invalide (liste vide, `task_type` inconnu…) |
| 500 | Erreur Gemini / Qdrant / schéma de sortie invalide |

---

### 4. Régénération d'une fiche orale

```
POST /api/v1/oral/regenerate-correction
```

Header requis : `X-API-Key: <votre_cle_api_tcf>`

Même traitement que l'endpoint batch, mais pour **un seul sujet** (objet `OralTopicRequest`, pas de tableau `topics`). La réponse est directement l'objet `correction` enrichi de `topic_id` / `task_type` / `task3_type`.

> ⚠️ Un échec de régénération remonte en `500` (le `400` prévu par la route est capturé par le handler d'exception général).

---

### Authentification JWT — non exposée

Le fichier `api_app/routes/auth.py` décrit un endpoint `POST /api/v1/auth/token` (compte de test `admin_tcf`), mais ce routeur **n'est jamais monté** dans `main.py` et importe des symboles inexistants. **L'endpoint n'existe pas** : seule la clé API `X-API-Key` est utilisable.

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
| `generate_candidates111.py` | Variante Groq/Mistral (cassée) |
| `generate_dataset.py` | Production de dataset via Groq (cassé) |
| `evaluate_copies.py` | Évaluation des copies par Mistral |
| `ingest_methodology.py` | Chunking et ingestion de **tous** les PDF de `methodology_docs/` dans Qdrant |
| `ingest_to_qdrant.py` | Ingestion des copies évaluées dans Qdrant |
| `validate_dataset.py` | Validation de la cohérence du dataset |

### Datasets (`data_pipeline/datasets/`)

| Fichier | Contenu |
|---------|---------|
| `copies_candidates_brutes.jsonl` | 788 copies brutes (A1-C1) |
| `copies_candidates_brutes1.jsonl` | 171 copies brutes (artefact orphelin) |
| `copies_evaluees.jsonl` | 787 copies avec évaluations expertes |
| `text_file.json` | Exemple de tâche 1 |

### Sources méthodologiques (`data_pipeline/methodology_docs/`)

| Fichier | Usage |
|---------|-------|
| `METHODOLOGIE_expression_ecrite_TCF_CANADA.pdf` | RAG Expression Écrite |
| `TAMARO_Methodologie_Expression_Orale.pdf` | RAG Expression Orale |

### Collections Qdrant

| Collection | Contenu | Usage |
|------------|---------|-------|
| `tcf_methodologie` | Règles méthodologiques (Top 3 pour l'écrit, Top 4 pour l'oral) | Contexte pour le LLM |
| `tcf_copies_dataset` | Copies évaluées avec filtrage par `tache_id` (Top 2) | Few-shot pour le LLM (écrit uniquement) |

---

## Déploiement

### Render / Railway / Fly.io

```bash
# Commandes de démarrage typiques
uvicorn api_app.main:app --host 0.0.0.0 --port $PORT
```

Variables d'environnement requises sur la plateforme :
- `GEMINI_API_KEY`
- `MISTRAL_API_KEY`
- `QDRANT_URL`
- `QDRANT_API_KEY`
- `TCF_API_KEY`

> ⚠️ Le `render.yaml` versionné ne déclare pas encore `GEMINI_API_KEY` : ajoutez-la manuellement dans le dashboard.

### Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD uvicorn api_app.main:app --host 0.0.0.0 --port $PORT
```

> ⚠️ `requirements.txt` ne contient pas encore `google-genai` : ajoutez-le (`pip install google-genai==2.31.0`) avant de construire l'image, sinon le conteneur crash au démarrage.

### Simulateur LLM local (optionnel)

```bash
docker compose -f docker-compose.vps-sim.yml up -d
```

Déploie un serveur **Ollama** sur le port 11434 (`vps_llm_simulation`). Ce service est **indépendant de l'API** : le backend cible l'API Gemini en l'état ; le branchement sur Ollama nécessite le support `LLM_BASE_URL` spécifié dans `prompt_LLM_PROVIDER_SWITCHING_IMPLEMENTATION.md` (non implémenté).
