# Documentation technique complète — API Simulateur TCF Canada

> **Objet** : API REST de génération de corrections pédagogiques pour le **TCF Canada** (France Éducation International) : évaluation automatique de l'**Expression Écrite** + fiches de correction d'**Expression Orale**. LLM **Google Gemini** (`google-genai`), RAG **Qdrant** (embeddings **Mistral** `mistral-embed`).
>
> **Version de l'API** : `1.0.0` · **Version d'analyse** : `1.0.0` · **Dernière revue** : octobre 2026 (mi-parcours du module Expression Orale + bascule LLM Mistral → Gemini)

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [L'épreuve TCF Expression Écrite](#2-lépreuve-tcf-expression-écrite)
3. [Architecture technique](#3-architecture-technique)
4. [Arborescence du projet](#4-arborescence-du-projet)
5. [Installation et configuration](#5-installation-et-configuration)
6. [Lancement de l'application](#6-lancement-de-lapplication)
7. [Référence API REST](#7-référence-api-rest)
8. [Pipeline d'exécution détaillé](#8-pipeline-dexécution-détaillé)
9. [Services internes — référence du code](#9-services-internes--référence-du-code)
10. [Grille de notation CECRL / NCLC](#10-grille-de-notation-cecrl--nclc)
11. [Construction du prompt LLM](#11-construction-du-prompt-llm)
12. [Pipeline de données (`data_pipeline/`)](#12-pipeline-de-données-datapipeline)
13. [Base vectorielle Qdrant](#13-base-vectorielle-qdrant)
14. [Tests](#14-tests)
15. [Déploiement](#15-déploiement)
16. [Points d'attention et écarts constatés](#16-points-dattention-et-écarts-constatés)
17. [Glossaire](#17-glossaire)

---

## 1. Vue d'ensemble

L'application est une API **FastAPI** qui poursuit deux objectifs pour le TCF Canada :

1. **Expression Écrite** — recevoir les productions écrites d'un candidat pour les **3 tâches**, les faire évaluer par un LLM enrichi d'un contexte RAG, et renvoyer un **bilan chiffré et pédagogique** :
   - une **note sur 20** globale (agrégation des barèmes 4 / 7 / 9),
   - un **niveau CECRL** (A1→C2) et **NCLC** (1→12),
   - pour chaque tâche : une note, une analyse par critère, un relevé d'erreurs typé, une version corrigée, une version modèle C2 et un coaching.
2. **Expression Orale** — générer des **fiches de correction pédagogique** (JSON structuré et validé par Pydantic) pour une liste de sujets de Tâche 2 (interaction) et Tâche 3 (dialectique / analyse), enrichies par le même RAG méthodologique.

### Fonctionnement en une phrase

> Pour l'écrit, le backend traite les 3 tâches **séquentiellement** : chacune est évaluée par `gemini-3.8-flash` (sortie JSON contrainte) enrichie des règles méthodologiques (Top 3 chunks Qdrant) et de 2 copies de référence de la même tâche (Top 2 filtré) ; les notes sont ensuite recalculées et agrégées. Pour l'oral, un prompt par type de tâche + Top 4 chunks méthodologie alimentent une génération validée contre un schéma Pydantic strict.

### Ce que l'application **n'est pas**

- Ce n'est pas une plateforme de passage d'examen : elle **note**, elle ne délivre pas de diplôme.
- L'authentification JWT reste **du code mort** : le routeur `api_app/routes/auth.py` n'est jamais monté dans `main.py` et importe des symboles inexistants (`creer_access_token`, `verifier_mot_de_passe`). Seule la clé API `X-API-Key` protège les endpoints métier.
- Il n'y a **ni base de données, ni persistance** : l'API est **stateless** (le module oral génère des fiches à la volée, sans stockage).

---

## 2. L'épreuve TCF Expression Écrite

L'épreuve dure **60 minutes** et se compose de 3 tâches avec des barèmes et contraintes de longueur distincts.

| Tâche | Type de production | Barème | Longueur exigée | Documents fournis |
|-------|--------------------|--------|-----------------|-------------------|
| **1** | Message / lettre (amicale ou formelle) : récit, description, invitation | **/ 4** | 60 – 120 mots | Non |
| **2** | Article, lettre formelle, témoignage ou commentaire | **/ 7** | 120 – 150 mots | Non |
| **3** | Synthèse argumentative : résumer 2 documents puis prendre position | **/ 9** | 120 – 180 mots | **Oui (2 documents)** |

**Total : 20 points.**

### Structure attendue par tâche

- **Tâche 1** — Salutation → Corps (avec connecteurs) → Formule de politesse / d'espoir → Formule d'adieu → Signature. Séparés par des sauts de ligne doubles.
- **Tâche 2** — Titre → Salutation → Introduction → Développement (arguments) → Recommandation → Prénom / signature.
- **Tâche 3** — Titre (≤ 9 mots) → Partie 1 : résumé neutre + confrontation des deux points de vue (45-55 mots) → Partie 2 : avis personnel + argument 1 illustré + argument 2 illustré (60-80 mots) → Conclusion avec nuance (20-30 mots).

---

## 3. Architecture technique

### 3.1 Schéma global

```
                          ┌──────────────────────┐
                          │  Client (React SPA)  │
                          └──────────┬───────────┘
                                     │ HTTPS  +  X-API-Key
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        FastAPI (api_app)                               │
│                                                                         │
│  ┌────────────────┐   ┌──────────────────────────────────────────────┐ │
│  │ Sécurité       │──▶│ POST /api/v1/tcf/evaluation-complete         │ │
│  │ verifier_cle_api│   │ POST /api/v1/oral/generate-corrections      │ │
│  └────────────────┘   │ POST /api/v1/oral/regenerate-correction     │ │
│                        └───────────────┬──────────────────────────────┘ │
│                                       ▼                                │
│                          ┌────────────────────────┐                    │
│                          │  LLMService            │                    │
│                          │  evaluer_session_…     │                    │
│                          │  generer_corrections_  │                    │
│                          │  orales_batch()        │                    │
│                          └───┬────────────────┬───┘                    │
│                              │ RAG             │ JSON                  │
│                              ▼                 ▼                       │
│                    ┌───────────────┐   ┌──────────────────────┐        │
│                    │  RAGService  │   │  Google Gemini API    │        │
│                    │  embeddings  │   │  gemini-3.8-flash     │        │
│                    │  mistral-embed│   │  (SDK google-genai)  │        │
│                    └───────┬───────┘   └──────────────────────┘        │
└────────────────────────────┼───────────────────────────────────────────┘
                             ▼
              ┌──────────────────────────────┐
              │  Qdrant Cloud                │
              │  ├─ tcf_methodologie   (Top3 écrit / Top4 oral)│
              │  └─ tcf_copies_dataset (Top2, écrit seulement) │
              └──────────────────────────────┘
```

> **Bascule fournisseur (octobre 2026)** : l'appel LLM est passé de Mistral (`mistralai`, `mistral-large-latest`) à **Gemini** (`google-genai`, `gemini-3.8-flash` par défaut, surchargeable via `LLM_MODEL_NAME`). Les **embeddings restent sur Mistral** (`mistral-embed`, 1024 dims) pour préserver les collections Qdrant existantes. Le SDK `mistralai` est donc toujours requis (embeddings + `data_pipeline`), tout comme `google-genai` (LLM) — or **aucun des deux n'est correctement déclaré** dans `requirements.txt` (voir §16.7).

### 3.2 Flux d'exécution d'une requête (Expression Écrite)

```
1. POST /api/v1/tcf/evaluation-complete  (X-API-Key)
      │
2. Sécurité — verifier_cle_api() compare l'en-tête à TCF_API_KEY
      │                                  (échec → 403)
3. Validation Pydantic — TCFExamenRequest
      │                                  (échec → 422)
4. Construction des dépendances : RAGService() + LLMService()
      │                                  (instanciés à chaque requête)
5. LLMService.evaluer_session_complete(payload, rag)
      │
      ├─ Traitement SÉQUENTIEL (plus d'asyncio.gather) :
      │     │
      │     ├─ _analyser_une_tache(1, 4, …)
      │     ├─ (si MAX_CONCURRENT_LLM_CALLS == 1 : asyncio.sleep(1.0))
      │     ├─ _analyser_une_tache(2, 7, …)   chacun :
      │     ├─ (si MAX_CONCURRENT_LLM_CALLS == 1 : asyncio.sleep(1.0))   ① RAG (embedding + 2 requêtes Qdrant)
      │     └─ _analyser_une_tache(3, 9, …)   ② consigne (T3 : + 2 documents)
      │                                       ③ prompt système + appel Gemini
      │                                          (asyncio.to_thread + retry 429/503)
      │                                       ④ parsing JSON
      │                                       ⑤ injection texte original + nb de mots
      │
      ├─ Post-traitement par tâche :
      │     • _calculer_niveaux_par_tache() → écrase niveau_estime
      │     • reconstruction du bloc "consigne"
      │     • nombre_mots_candidat / nombre_mots_exemple
      │     • ou _generer_tache_vide() si tâche absente/vide
      │
      └─ Bilan global : somme des notes /20 → _determiner_niveaux_tcf()
      │
6. Sérialisation + validation par TCFEvaluationGlobaleResponse
      │
7. HTTP 200 JSON
```

> **Régression de parallélisme** : la version précédente lançait les 3 tâches via `asyncio.gather()`. Le code actuel les exécute **l'une après l'autre** (`llm_service.py:244-296`) : la latence totale est la **somme** des 3 appels Gemini (~3 × 3-10 s). La variable `MAX_CONCURRENT_LLM_CALLS` (défaut `3`) **ne parallélise rien** côté écrit : elle ne pilote qu'un `asyncio.sleep(1.0)` conditionnel (si la valeur vaut `1`) et le sémaphore du flux oral.

### 3.3 Technologies employées

| Couche | Technologie | Version | Rôle |
|--------|-------------|---------|------|
| Framework web | FastAPI | 0.137.1 | Endpoints REST, validation, OpenAPI auto |
| Serveur ASGI | Uvicorn | 0.49.0 | Exécution HTTP |
| Validation | Pydantic | 2.13.4 | Schémas requête / réponse (écrit + **oral strict**) |
| LLM | `google-genai` | 2.31.0 | Évaluation écrite + génération des fiches orales (`gemini-3.8-flash`) |
| Embeddings | `mistralai` | 2.5.0 | Vecteurs 1024 dims pour Qdrant (`mistral-embed`) — **plus utilisé pour le chat** |
| Base vectorielle | `qdrant-client` | 1.18.0 | RAG (2 collections) |
| Variables d'env | `python-dotenv` | 1.2.2 | Chargement du `.env` |
| Auth JWT | `python-jose` | 3.5.0 | **Déclaré mais inutilisé** |
| Hash | `passlib` | 1.7.4 | **Déclaré mais inutilisé** |
| Client HTTP | `httpx` | 0.28.1 | Transport des tests ASGI |
| Tests | `pytest` / `pytest-asyncio` | 9.1.1 / 1.4.0 | **Absents de `requirements.txt`** |

> ⚠️ `requirements.txt` n'a **pas suivi la bascule** : il déclare encore `mistralai` (utile) mais **omet `google-genai`**, sans lequel `llm_service.py` lève `ModuleNotFoundError` au premier import. Toute image Docker construite depuis ce fichier est **cassée** (voir §16.1).

### 3.4 Modèles IA utilisés

| Modèle | Endpoint | Usage | Température |
|--------|----------|-------|-------------|
| `gemini-3.8-flash` (défaut `LLM_MODEL_NAME`) | Gemini Developer API v1 (`genai.Client`, `models.generate_content`) | Évaluation pédagogique des copies **et** fiches orales ; sortie `application/json` (+ `response_schema` Pydantic pour l'oral) | **0.0** |
| `mistral-embed` | `mistralai` `embeddings.create` | Vecteurs 1024 dims pour Qdrant (écrit + oral) | — |
| `llama-3.3-70b-versatile` | Groq (data pipeline) | Génération synthétique de dataset | 0.7 – 0.8 |

L'appel Gemini est **synchrone** (`client.models.generate_content`) et déporté via `asyncio.to_thread`. Un retry à backoff exponentiel (2 s → 4 s → 8 s) est appliqué sur les erreurs `429` / `503` (`_appeler_llm_json`, 3 essais maximum).

---

## 4. Arborescence du projet

```
api-simulateur-ec-tcf/
│
├── api_app/                              # ── APPLICATION RUNTIME ──
│   ├── main.py                           # Point d'entrée : app FastAPI, chargement .env,
│   │                                     #   montage des routeurs, endpoint racine
│   ├── core/
│   │   └── security.py                   # Auth par clé API (X-API-Key)
│   ├── prompts/
│   │   └── oral_prompts.py               # 3 prompts système (T2, T3 dialectique, T3 analytique)
│   ├── routes/
│   │   ├── evaluation.py                 # Routeur écrit + schémas Pydantic
│   │   ├── oral_correction.py            # Routeur oral (2 endpoints)
│   │   └── auth.py                       # ⚠ NON MONTÉ + imports inexistants
│   ├── schemas/
│   │   └── oral.py                       # Schémas Pydantic Expression Orale (request + response)
│   └── services/
│       ├── llm_service.py                # Orchestrateur LLM (Gemini) + grille CECRL/NCLC + oral
│       └── rag_service.py                # Embeddings Mistral + requêtes Qdrant (écrit + oral)
│
├── data_pipeline/                        # ── PIPELINE HORS LIGNE ──
│   ├── datasets/
│   │   ├── copies_candidates_brutes.jsonl    788 copies non notées  (1.2 Mo)
│   │   ├── copies_candidates_brutes1.jsonl   171 copies (artefact orphelin)
│   │   ├── copies_evaluees.jsonl            787 copies notées (2.9 Mo)
│   │   └── text_file.json                   Exemple de payload de requête
│   ├── generation/
│   │   ├── generate_candidates.py            Génération brute (Mistral) — Pipeline 1 & 2
│   │   ├── generate_candidates111.py         Variante de sauvegarde (cassée)
│   │   ├── generate_dataset.py               ⚠ Dataset fine-tuning Groq (casse : NameError)
│   │   ├── evaluate_copies.py                Notation experte (Mistral) — Pipeline 3
│   │   ├── ingest_to_qdrant.py               Injection copies → tcf_copies_dataset
│   │   ├── ingest_methodology.py             Chunking PDFs → tcf_methodologie (batch 10 + retry 429)
│   │   └── validate_dataset.py               Contrôle qualité (stdlib seul)
│   └── methodology_docs/
│       ├── METHODOLOGIE_expression_ecrite_TCF_CANADA.pdf   20 p. — source du RAG écrit
│       └── TAMARO_Methodologie_Expression_Orale.pdf        source du RAG oral
│       (l'ancien METHODOLOGIE_TCF_CANADA_TAYES.pdf a été supprimé du dépôt)
│
├── tests/
│   ├── test_tcf_service.py               # 14 tests (13 unitaires + 1 intégration)
│   └── test.json                         # Payload manuel pour curl
│
├── Dockerfile                            # Image python:3.12-slim
├── .dockerignore                         # Exclut venv, data_pipeline, tests, .env
├── docker-compose.vps-sim.yml            # Simulateur LLM local (Ollama) pour la VPS
├── render.yaml                           # Blueprint Render (runtime: docker)
├── requirements.txt                      # 9 dépendances pinnées (⚠ incomplet : pas de google-genai)
├── pyproject.toml                        # Config pytest (pythonpath, asyncio_mode)
├── .env / .env.example                   # Configuration (.env.example complété en oct. 2026)
├── README.md                             # Documentation d'usage
├── FONCTIONNEMENT.md                     # Explication du fonctionnement interne
├── prompt_TAMARO_ORAL_API_IMPLEMENTATION.md      # Spécification du module oral (historique)
└── prompt_LLM_PROVIDER_SWITCHING_IMPLEMENTATION.md  # Spécification fournisseurs LLM (non appliquée)
```

> **Note** : aucun fichier `__init__.py` n'existe. Les paquets `api_app`, `api_app.core`, `api_app.routes`, `api_app.services` et `data_pipeline` fonctionnent comme des **namespace packages** PEP 420. L'import fonctionne si le dossier racine est dans le `PYTHONPATH` (garanti par `pythonpath = ["."]` dans `pyproject.toml` pour les tests, mais **pas** pour un lancement `uvicorn` hors dossier racine).

---

## 5. Installation et configuration

### 5.1 Prérequis

- **Python 3.10+** (le `Dockerfile` cible 3.12 ; l'environnement de développement utilise 3.14)
- Un compte [Google AI Studio](https://aistudio.google.com/) → clé API **Gemini** (`GEMINI_API_KEY`) — indispensable pour le LLM
- Un compte [Mistral AI](https://console.mistral.ai/) → clé API **Mistral** (`MISTRAL_API_KEY`) — embeddings uniquement
- Une instance [Qdrant Cloud](https://cloud.qdrant.io/) → URL + clé API
- `pytest` + `pytest-asyncio` pour la suite de tests (non fournis par `requirements.txt`)

### 5.2 Installation

```bash
git clone <url-du-depot>
cd api-simulateur-ec-tcf

# Environnement virtuel
python -m venv venv
# Windows      → venv\Scripts\activate
# Linux/macOS  → source venv/bin/activate

# Dépendances
pip install -r requirements.txt

# Dépendances de développement optionnelles (tests + pipeline PDF)
pip install pytest pytest-asyncio pypdf groq
```

### 5.3 Variables d'environnement

Le fichier `.env` est chargé par `api_app/main.py:7-8` via `load_dotenv(dotenv_path=chemin_racine / ".env")`. Les scripts de `data_pipeline/` font de même (chargement explicite du chemin racine).

| Variable | Obligatoire | Utilisée par | Description |
|----------|:-----------:|--------------|-------------|
| `GEMINI_API_KEY` | ✅ | `LLMService` (`llm_service.py:68`) — **écrit ET oral** | Clé API Google AI Studio (Gemini). Repli accepté : `LLM_API_KEY` |
| `MISTRAL_API_KEY` | ✅ | `RAGService`, `ingest_to_qdrant.py`, `ingest_methodology.py`, `generate_candidates.py`, `evaluate_copies.py` | Clé API Mistral — **embeddings uniquement** (`mistral-embed`) |
| `QDRANT_URL` | ✅ | `RAGService`, scripts d'ingestion | URL de l'instance Qdrant |
| `QDRANT_API_KEY` | ✅ | idem | Clé API Qdrant Cloud |
| `TCF_API_KEY` | ✅ | `core/security.py` | Clé attendue dans l'en-tête `X-API-Key` |
| `LLM_MODEL_NAME` | ➖ | `LLMService` | Modèle Gemini (défaut : `gemini-3.8-flash`) |
| `LLM_API_KEY` | ➖ | `LLMService` | Repli de `GEMINI_API_KEY` |
| `MAX_CONCURRENT_LLM_CALLS` | ➖ | `llm_service.py:32` | Défaut `3`. Sémaphore oral + `sleep(1.0)` entre tâches écrites si `1` (**ne parallélise pas l'écrit**) |
| `GROQ_API_KEY` | ➖ | `generate_dataset.py`, `generate_candidates111.py` | Génération de datasets (scripts non utilisés en production) |

**Modèle `.env.example` (versionné depuis octobre 2026) :**

```dotenv
# LLM (obligatoire — chat écrit + oral via Google Gemini)
GEMINI_API_KEY=votre_cle_gemini
# Repli accepté par le code : LLM_API_KEY
# LLM_MODEL_NAME=gemini-3.8-flash
# MAX_CONCURRENT_LLM_CALLS=3

# Embeddings RAG (obligatoire — Mistral)
MISTRAL_API_KEY=votre_cle_mistral

# Qdrant (obligatoire)
QDRANT_URL=votre_url_qdrant
QDRANT_API_KEY=votre_cle_qdrant

# Sécurité API (obligatoire)
TCF_API_KEY=votre_cle_api_tcf

# Optionnel
GROQ_API_KEY=votre_cle_groq_optionnelle
```

> ✅ Le `.env.example` versionné mentionne désormais `GEMINI_API_KEY`, `LLM_MODEL_NAME` et `MAX_CONCURRENT_LLM_CALLS` (complété en octobre 2026) ; `render.yaml`, lui, ne déclare toujours pas `GEMINI_API_KEY` (voir §15.3).

> ⚠️ **Valeur de repli dangereuse** : si `TCF_API_KEY` est absente, `security.py:13` retombe sur la chaîne littérale `"cle_par_defaut_si_vide"`. L'endpoint reste alors accessible à quiconque envoie cette valeur.

> ⚠️ Le `.env` réel **n'est pas versionné** (`.gitignore` ligne 1) mais le README documente publiquement la valeur `tcf_secret_dev_key_2026` comme clé d'exemple, et le test d'intégration la code en dur.

---

## 6. Lancement de l'application

```bash
# Développement (rechargement automatique)
uvicorn api_app.main:app --reload --port 8000

# Production
uvicorn api_app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

| URL | Description |
|-----|-------------|
| `http://localhost:8000/` | Health check |
| `http://localhost:8000/docs` | Swagger UI (interactif) |
| `http://localhost:8000/redoc` | Documentation ReDoc |
| `http://localhost:8000/openapi.json` | Schéma OpenAPI 3.1 |

**Surface de l'API vérifiée (via `app.openapi()`) :**

```
POST  /api/v1/tcf/evaluation-complete
POST  /api/v1/oral/generate-corrections
POST  /api/v1/oral/regenerate-correction
GET   /
```

C'est **tout**. L'endpoint `POST /api/v1/auth/token` décrit par `api_app/routes/auth.py` **n'est pas exposé** (voir §16, ligne 3) — le README le documente désormais comme « non exposé ».

> ⚠️ **Simulateur LLM local** : `docker-compose.vps-sim.yml` déploie un conteneur **Ollama** (`vps_llm_simulation`, port 11434) destiné aux tests sur VPS. Ce service est **indépendant de l'API** : rien dans `llm_service.py` ne cible `localhost:11434` — la bascule locale passerait par `LLM_PROVIDER`/`LLM_BASE_URL`, spécifiés dans `prompt_LLM_PROVIDER_SWITCHING_IMPLEMENTATION.md` mais **non implémentés**.

---

## 7. Référence API REST

### 7.1 `GET /` — Health check

Route déclarée dans `api_app/main.py:18-20`.

**Authentification** : aucune
**Code de retour** : `200`

```json
{ "status": "online" }
```

---

### 7.2 `POST /api/v1/tcf/evaluation-complete` — Évaluation complète

Route déclarée dans `api_app/routes/evaluation.py:75-87`. **C'est l'endpoint principal.**

**Authentification** : en-tête `X-API-Key` (dépendance `verifier_cle_api`)
**Content-Type** : `application/json`
**Modèle de réponse** : `TCFEvaluationGlobaleResponse`

#### 7.2.1 Modèle de requête

```python
class TachePayload(BaseModel):
    consigne_sujet: str                  # obligatoire
    texte_candidat: str                  # obligatoire
    documents_contexte: list[str] = []   # défaut : liste vide (Tâche 3 uniquement)

class TCFExamenRequest(BaseModel):
    tache_1: TachePayload | None = None
    tache_2: TachePayload | None = None
    tache_3: TachePayload | None = None
```

**Sémantique**

- Chaque tâche est **indépendante et optionnelle**. `null` ou `texte_candidat` vide ⇒ tâche considérée **non soumise** (bloc à zéro, aucun appel LLM).
- `documents_contexte` n'a d'effet que sur la **Tâche 3**. Seuls les **2 premiers** éléments sont utilisés (`docs[0]`, `docs[1]`), les suivants sont ignorés.
- L'API **ne vérifie pas** que la consigne respecte la longueur attendue, ni que `texte_candidat` est dans la marge de mots : c'est le LLM qui l'apprécie et le rapporte dans `controle_methodologie.respect_nombre_mots`.

**Exemple de payload :**

```json
{
  "tache_1": {
    "consigne_sujet": "Vous avez déménagé dans une nouvelle ville. Écrivez un message à un ami pour lui décrire votre quartier et l'inviter.",
    "texte_candidat": "Cher ami,\n\nJe viens de m'installer à Lyon...",
    "documents_contexte": []
  },
  "tache_2": {
    "consigne_sujet": "Écrivez un article expliquant pourquoi vous avez abandonné les réseaux sociaux.",
    "texte_candidat": "Pourquoi j'ai quitté les réseaux sociaux...",
    "documents_contexte": []
  },
  "tache_3": {
    "consigne_sujet": "Les photos sur le CV, pour ou contre ?",
    "texte_candidat": "La place de la photo sur un CV...",
    "documents_contexte": [
      "Document 1 : ...",
      "Document 2 : Christophe adhère à l'idée..."
    ]
  }
}
```

#### 7.2.2 Modèle de réponse

```python
class ScoreGlobal(BaseModel):
    sur_20: float      # ex. 12.5
    pourcentage: int   # ex. 62
    mention: str       # ex. "Assez Bien"

class NiveauGlobal(BaseModel):
    cecrl: str         # A1 | A2 | B1 | B2 | C1 | C2
    nclc: str          # "3" | "4" | ... | "9" | "10+"

class BilanGlobalResponse(BaseModel):
    score: ScoreGlobal
    niveau: NiveauGlobal
    resume: str
    points_forts: list[str] = []           # toujours vide en v1
    priorites_progression: list[str] = []  # toujours vide en v1

class MetaResponse(BaseModel):
    exam: str              # "TCF Canada"
    epreuve: str           # "Expression écrite"
    date_evaluation: str   # ISO 8601 UTC, ex. "2026-09-25T12:00:00Z"
    version_analyse: str   # "1.0.0"
    mode: str              # "evaluation_complete"

class TCFEvaluationGlobaleResponse(BaseModel):
    status: str
    meta: MetaResponse
    bilan_global: BilanGlobalResponse
    evaluations: list[dict | None]   # ← PASSE-PLAIT : aucun schéma typé
```

> ⚠️ `evaluations` est typé `List[Optional[Dict[str, Any]]]`. **Aucune validation de la structure interne n'est effectuée par FastAPI** : la forme exacte des blocs par tâche n'est garantie que par le prompt envoyé au LLM. Si le LLM dévie du JSON demandé, la réponse est renvoyée telle quelle au client.

#### 7.2.3 Structure d'un bloc d'évaluation (`evaluations[i]`)

Champs produits pour une tâche **soumise et notée** :

```jsonc
{
  "tache": 1,                          // 1 | 2 | 3
  "consigne": "…",                     // T1/T2 = consigne brute ; T3 = "TITRE : …\n\n<doc1>\n\n<doc2>"
  "copie": {
    "texte_original": "…",             // injecté côté backend
    "nombre_mots": 85                  // injecté côté backend (len(texte.split()))
  },

  // ↓ Champs non documentés dans le README mais bien émis par le service
  "nombre_mots_candidat": 85,          // _compter_mots(texte_candidat)
  "nombre_mots_exemple": 112,          // _compter_mots(versions.version_modele_c2)

  "score": { "obtenu": 3.0, "maximum": 4 },
  "niveau_estime": { "cecrl": "B2", "nclc": "7" },

  "controle_methodologie": {           // 9 drapeaux booléens
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

  "analyse": {                         // 6 axes, chacun {note, commentaire}
    "comprehension_sujet":   { "note": 0.0, "commentaire": "…" },
    "respect_methodologie":  { "note": 0.0, "commentaire": "…" },
    "coherence_cohesion":    { "note": 0.0, "commentaire": "…" },
    "lexique":               { "note": 0.0, "commentaire": "…" },
    "grammaire":             { "note": 0.0, "commentaire": "…" },
    "orthographe":           { "note": 0.0, "commentaire": "…" }
  },

  "statistiques": {                    // 3 indicateurs
    "richesse_lexicale":       { "score": 0, "niveau": "…", "commentaire": "…" },
    "complexite_syntaxique":   { "score": 0, "niveau": "…", "commentaire": "…" },
    "fluidite":                { "score": 0, "niveau": "…", "commentaire": "…" }
  },

  "erreurs": [                         // tableau, vide si aucune erreur
    {
      "id": 1,
      "gravite": "Moyenne",            // "Faible" | "Moyenne" | "Grave"
      "type": "Grammaire",            // "Grammaire" | "Orthographe" | "Lexique" | "Syntaxe" …
      "segment_original": "…",         // extrait fautif
      "correction": "…",              // forme corrigée
      "explication": "…",
      "regle": "…",                   // règlegrammaticale applicable
      "exemple": "…"
    }
  ],

  "versions": {
    "version_corrigee":   "…",   // texte du candidat nettoyé des fautes, dans la marge de mots
    "version_modele_c2":  "…"    // rédaction modèle niveau C2 (nom du champ : **c2**, pas c1)
  },

  "coaching": {
    "points_forts":                ["…"],
    "points_a_ameliorer":         ["…"],
    "conseils":                    ["…"],
    "objective_prochaine_copie":   "…"   // ⚠ nom exact : "objective", pas "objectif"
  }
}
```

Champs produits pour une tâche **non soumise** (`_generer_tache_vide`) :

```jsonc
{
  "tache": 2,
  "consigne": "",                 // ou la consigne si le payload existe
  "copie": { "texte_original": "", "nombre_mots": 0 },
  "score": { "obtenu": 0.0, "maximum": 7 },
  "niveau_estime": { "cecrl": "A1", "nclc": "3 ou moins" },
  "controle_methodologie": { /* les 9 drapeaux à false */ },
  "analyse": {},                  // objets VIDES (pas de structure à 6 axes)
  "statistiques": {},             // objets VIDES
  "erreurs": [],
  "versions": { "version_corrigee": "", "version_modele_c2": "" },
  "coaching": {
    "points_forts": [],
    "points_a_ameliorer": ["Tâche non traitée."],
    "conseils": [],
    "objective_prochaine_copie": ""
  }
}
```

> ⚠️ Le backend **ne rajoute pas** `nombre_mots_candidat` / `nombre_mots_exemple` sur les tâches vides : un client qui lit ces deux clés doit tolérer leur absence. De même, `analyse` et `statistiques` sont `{}` (pas `None`), ce qui casse une lecture stricte du schéma.

#### 7.2.4 Exemples d'appel

**cURL — 2 tâches sur 3 :**

```bash
curl -X POST http://localhost:8000/api/v1/tcf/evaluation-complete \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $TCF_API_KEY" \
  -d '{
    "tache_1": {
      "consigne_sujet": "Vous avez récemment déménagé dans une nouvelle ville. Écrivez un message à un ami pour lui décrire votre nouveau quartier et l''inviter à vous rendre visite.",
      "texte_candidat": "Cher ami,\n\nJe viens de m installer à Lyon...",
      "documents_contexte": []
    },
    "tache_2": {
      "consigne_sujet": "Écrivez un article sur les raisons de votre arrêt des réseaux sociaux.",
      "texte_candidat": "Pourquoi j ai quitté les réseaux sociaux...",
      "documents_contexte": []
    },
    "tache_3": null
  }'
```

**cURL — payload depuis un fichier :**

```bash
curl -X POST http://localhost:8000/api/v1/tcf/evaluation-complete \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $TCF_API_KEY" \
  -d @tests/test.json
```

**Python (httpx) :**

```python
import httpx, os

payload = {
    "tache_1": {
        "consigne_sujet": "…",
        "texte_candidat": "…",
        "documents_contexte": [],
    },
    "tache_3": None,
}

r = httpx.post(
    "http://localhost:8000/api/v1/tcf/evaluation-complete",
    json=payload,
    headers={"X-API-Key": os.environ["TCF_API_KEY"]},
    timeout=120.0,
)
bilan = r.json()
print(bilan["bilan_global"]["score"], bilan["bilan_global"]["niveau"])
```

#### 7.2.5 Codes de réponse

| Code | Cause | Corps de la réponse |
|------|-------|---------------------|
| `200` | Évaluation réussie | `TCFEvaluationGlobaleResponse` |
| `403` | `X-API-Key` absent ou ≠ `TCF_API_KEY` | `{"detail": "Accès refusé : Clé d'API invalide ou manquante dans l'en-tête X-API-Key"}` |
| `422` | Payload invalide (champ manquant, type incorrect) | Liste d'erreurs Pydantic standard |
| `500` | Exception dans `evaluer_session_complete` (Gemini, Qdrant, JSON malformé) | `{"detail": "<message de l'exception>"}` |

> ⚠️ Le `500` renvoie `str(e)` **en clair**. Les messages d'erreur des SDK tiers (Gemini, Qdrant, Mistral) peuvent contenir des fragments d'URL, des identifiants de requête ou des extraits de prompt — information divulgée au client.

---

### 7.3 `POST /api/v1/oral/generate-corrections` — Fiches orales en batch

Route déclarée dans `api_app/routes/oral_correction.py:22-43`. Module **Expression Orale** (sujets Tâche 2 et Tâche 3).

**Authentification** : en-tête `X-API-Key` (dépendance `verifier_cle_api`)
**Content-Type** : `application/json`
**Modèle de réponse** : `BatchOralCorrectionResponse`

#### 7.3.1 Modèle de requête (`api_app/schemas/oral.py`)

```python
class OralTaskType(str, Enum):
    TASK_2 = "TASK_2"
    TASK_3 = "TASK_3"

class Task3Subtype(str, Enum):
    DIALECTICAL = "DIALECTICAL"
    ANALYTICAL  = "ANALYTICAL"

class OralTopicRequest(BaseModel):
    id: str                                 # obligatoire — ID du sujet côté front
    task_type: OralTaskType                 # obligatoire — TASK_2 | TASK_3
    task3_type: Task3Subtype | None = None  # requis si TASK_3 (non vérifié ici !)
    content: str                            # obligatoire — consigne / intitulé

class BatchOralTopicRequest(BaseModel):
    topics: list[OralTopicRequest]          # min 1 élément (Field min_items, ⚠ déprécié Pydantic)
```

> ⚠️ La contrainte `task3_type requis si TASK_3` n'est **pas** exprimée dans le schéma (pas de `model_validator`) : elle est levée *in fine* en `ValueError` dans `_obtenir_config_prompt_oral()` (`llm_service.py:415-426`) et se traduit par un **500** au lieu d'un **422**.

**Exemple de payload :**

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

#### 7.3.2 Modèle de réponse

```python
class BatchOralCorrectionResponse(BaseModel):
    status: str                              # "success"
    total_processed: int                     # len(topics)
    corrections: list[OralTopicCorrectionItem]

class OralTopicCorrectionItem(BaseModel):
    topic_id: str
    task_type: OralTaskType
    task3_type: Task3Subtype | None
    correction: Task2Correction | Task3DialecticalCorrection | Task3AnalyticalCorrection
```

La structure de `correction` dépend du type :

| Type | Schéma | Champs principaux |
|------|--------|-------------------|
| `TASK_2` | `Task2Correction` | `context`, `understanding`, `objective`, `expected_information[]`, `suggested_questions[]`, `possible_interaction[]` (5-8 paires `{role, texte}`), `useful_expressions[]`, `common_mistakes[]` |
| `TASK_3` + `DIALECTICAL` | `Task3DialecticalCorrection` | `topic_analysis`, `problematic`, `position_example`, `arguments[]` (2-3 × `{argument, explanation, example}`), `counter_argument`, `conclusion_example`, `useful_expressions[]`, `common_mistakes[]` |
| `TASK_3` + `ANALYTICAL` | `Task3AnalyticalCorrection` | `topic_analysis`, `axes_of_development[]`, `plan[]`, `arguments[]`, `examples[]`, `conclusion_example`, `useful_expressions[]`, `common_mistakes[]` |

**Validation** : contrairement à l'écrit (passe-plaît `dict | None`), la réponse orale est **validée par Pydantic** (`response_schema.model_validate(response_json)`, `llm_service.py:406`). Les validateurs `mode="before"` (`schemas/oral.py:62-106`) tolèrent que le LLM renvoie des listes sous forme de chaîne multiligne, ou `possible_interaction` sous forme de texte `Rôle: réplique`.

**Codes de réponse** : `200` succès · `403` clé invalide · `422` payload invalide · `500` exception Gemini/Qdrant (message en clair).

#### 7.3.3 Traitement interne

```
generer_corrections_orales_batch(topics, rag)          llm_service.py:350-371
  ├─ asyncio.Semaphore(MAX_CONCURRENT_CALLS)           # défaut 3 appels simultanés
  ├─ asyncio.gather(*[_traiter_avec_limite(t) …])      # parallèle, SANS return_exceptions
  └─ _traiter_un_sujet_oral(topic, rag)                llm_service.py:373-413
        ├─ rag.recuperer_contexte_oral(content, task_type, task3_type)  # Top 4 méthodologie
        ├─ prompt système (oral_prompts.py) + schéma Pydantic
        ├─ user_prompt = contexte RAG + sujet
        ├─ Gemini via asyncio.to_thread(_appeler_llm_json, response_schema=…)
        └─ OralTopicCorrectionItem(correction=…)
```

> ⚠️ Ici, contrairement à l'écrit, `asyncio.gather` est utilisé **sans `return_exceptions=True`** : une erreur sur un seul sujet fait échouer l'intégralité du batch (500), y compris les sujets déjà traités avec succès.

### 7.4 `POST /api/v1/oral/regenerate-correction` — Régénération unitaire

Route déclarée dans `api_app/routes/oral_correction.py:45-70`.

Reprend exactement le même chemin que §7.3 avec une liste d'un seul sujet, et renvoie directement le `OralTopicCorrectionItem` (sans enveloppe batch).

**Schéma de requête** : `OralTopicRequest` (un objet, pas une liste).

> ⚠️ **Bug de code d'erreur** : la route lève un `HTTPException(400)` si la régénération échoue (`oral_correction.py:61-64`), mais ce `raise` se trouve **à l'intérieur du `try`** et le `except Exception` englobant le retransforme en **500** (`oral_correction.py:66-70`, `HTTPException` étant une sous-classe d'`Exception`). Le 400 est donc inatteignable.

---

## 8. Pipeline d'exécution détaillé

### 8.1 Étape 1 — Sécurité

`api_app/core/security.py:11-22`

```python
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verifier_cle_api(api_key: str = Security(api_key_header)):
    cle_attendue = os.getenv("TCF_API_KEY", "cle_par_defaut_si_vide")
    if not api_key or api_key != cle_attendue:
        raise HTTPException(status_code=403, detail="Accès refusé : …")
    return "application_react"
```

- `auto_error=False` ⇒ FastAPI ne génère pas son propre 403 ; c'est la fonction qui lève.
- Comparaison par `!=` ⇒ **pas de comparaison à temps constant** (`hmac.compare_digest` serait préférable).
- La valeur de retour (`"application_react"`) est injectée dans le handler sous le nom `current_user` mais **n'est jamais utilisée**.
- Aucun de ces contrôles n'est branché sur l'endpoint `/` ni sur `/docs` ⇒ la documentation OpenAPI est publique.

### 8.2 Étape 2 — Validation d'entrée

`api_app/routes/evaluation.py:14-22`. Une `422` est levée si `consigne_sujet` ou `texte_candidat` est absent d'une tâche fournie. Aucun contrôle de **longueur** ni de **présence des documents** n'est effectué.

### 8.3 Étape 3 — Résolution des dépendances

```python
def get_rag_service():  return RAGService()    # nouvelle instance par requête
def get_llm_service():  return LLMService()    # nouvelle instance par requête
```

Ces deux dépendances FastAPI **sans `cache`** sont réévaluées à chaque requête. Conséquences :

- un nouveau `QdrantClient` (avec son propre pool de connexions HTTP) est construit à chaque appel ;
- `RAGService.__init__` appelle `create_payload_index(...)` sur Qdrant **à chaque requête** (l'exception « index déjà existant » est avalée silencieusement) ;
- le SDK Mistral est ré-instancié.

Pour un débit soutenu, il faudrait `@lru_cache` sur ces dépendances ou une ressource applicative (`lifespan`).

### 8.4 Étape 4 — Évaluation d'une tâche

`api_app/services/llm_service.py:176-211`

```
_analyser_une_tache(num_tache, bareme_max, donnees_tache, rag_service)
  │
  ├─ garde : if not donnees_tache or not donnees_tache.texte_candidat → return None
  │
  ├─ 1. RAG
  │     contexte = rag_service.recuperer_contexte(texte_candidat, num_tache)
  │     regles_txt   = "\n".join(f"- {r}" for r in contexte["regles"])
  │     exemples_txt = json.dumps(contexte["exemples"], ensure_ascii=False)
  │
  ├─ 2. Consigne enrichie
  │     Tâche 3 → "TITRE : {consigne}\n\nDocument 1 :\n{doc1}\n\nDocument 2 :\n{doc2}"
  │     T1 / T2 → consigne_sujet brut
  │
  ├─ 3. sys_prompt = _generer_prompt_systeme(num_tache, bareme_max, regles_txt, exemples_txt)
  │     user_prompt = "Consigne:\n{consigne}\n\nCopie du candidat:\n{texte}"
  │
  ├─ 4. Appel Gemini (bloquant placé dans un thread via asyncio.to_thread)
  │     response_json = await asyncio.to_thread(
  │         self._appeler_llm_json,          # llm_service.py:428-463
  │         system_prompt=sys_prompt,
  │         user_prompt=user_prompt
  │     )
  │     # config : temperature=0.0, response_mime_type="application/json"
  │     # retry ×3 sur 429/503 (backoff 2 → 4 → 8 s), puis relance l'exception
  │
  └─ 5. Post-traitement
        res_dict = json.loads(response.text)          # ← peut lever JSONDecodeError
        res_dict["copie"]["nombre_mots"]    = len(texte.split())
        res_dict["copie"]["texte_original"] = texte
        res_dict["consigne"]                = consigne_complete
```

**Points techniques notables**

- `response_mime_type="application/json"` force une sortie JSON, mais **n'impose pas le schéma** (pas de `response_schema` sur le flux écrit) : la présence de `score.obtenu` ou `niveau_estime` n'est pas garantie. Un `KeyError` sur ces clés remonte en `500`.
- Le client Gemini est **synchrone** (`models.generate_content`) : `asyncio.to_thread` délègue au pool de threads par défaut (équivalent de l'ancien `run_in_executor`).
- L'appel **bloquant** de `recuperer_contexte()` (Qdrant + embeddings Mistral) est effectué **directement dans la coroutine**, sans offloading : il bloque la boucle d'événements.
- Le retry `429`/`503` utilise `time.sleep()` **dans le thread** (correct : le thread est bloqué, pas la boucle).

### 8.5 Étape 5 — Agrégation

`api_app/services/llm_service.py:240-326`

```python
res_t1 = await self._analyser_une_tache(1, 4, examen_payload.tache_1, rag_service)
# … post-traitement T1 …
res_t2 = await self._analyser_une_tache(2, 7, examen_payload.tache_2, rag_service)
# … post-traitement T2 …
res_t3 = await self._analyser_une_tache(3, 9, examen_payload.tache_3, rag_service)
# … post-traitement T3 …
```

- Les 3 tâches sont traitées **séquentiellement** (l'ancien `asyncio.gather` a été supprimé). Si **une seule** tâche lève (échec Gemini, JSON malformé…), toute la requête échoue en `500` — y compris les tâches déjà évaluées (dont l'appel LLM est déjà payé).
- Si `MAX_CONCURRENT_LLM_CALLS == 1`, un `asyncio.sleep(1.0)` est inséré **entre** chaque tâche (palier de rate-limit).
- Pour chaque tâche non nulle :
  - `_calculer_niveaux_par_tache(obtenu, bareme)` **écrase** le `niveau_estime` renvoyé par le LLM ;
  - `consigne` est réécrite ;
  - `nombre_mots_candidat` et `nombre_mots_exemple` sont ajoutés ;
  - `obtenu` est ajouté à `score_total_obtenu`.
- Pour chaque tâche nulle : `_generer_tache_vide(num_tache, bareme, payload)` et **aucun point n'est ajouté**.

**Calcul du bilan global :**

```python
note_sur_20  = round(score_total_obtenu, 2)
pourcentage  = round((note_sur_20 / 20) * 100)
cecrl, nclc, mention = self._determiner_niveaux_tcf(note_sur_20)
```

> ⚠️ **Le dénominateur est toujours 20**, même si une seule tâche est soumise. Soumettre uniquement la Tâche 1 plafonne mécaniquement le candidat à **4/20 → CECRL A2 « À renforcer »**, quel que soit le qualité de sa rédaction. Le `pourcentage` reflète cette même normalisation. Ce comportement n'est signalé nulle part dans la réponse (aucun champ du type `taches_soumises`).

### 8.6 Étape 6 — Sérialisation

FastAPI valide la réponse contre `TCFEvaluationGlobaleResponse` puis la sérialise. Un écart de forme sur `meta` / `bilan_global` provoque un `ResponseValidationError` → `500`, **alors même que l'évaluation a réussi et payé son appel LLM**.

---

## 9. Services internes — référence du code

### 9.1 `api_app/core/security.py`

| Symbole | Type | Rôle |
|---------|------|------|
| `API_KEY_NAME = "X-API-Key"` | constante | Nom de l'en-tête attendu |
| `api_key_header` | `APIKeyHeader` | Extracteur FastAPI, `auto_error=False` |
| `verifier_cle_api(api_key)` | `async` → `str` | Compare à `TCF_API_KEY`, lève 403, retourne `"application_react"` |

> Le fichier ne contient **ni** `creer_access_token` **ni** `verifier_mot_de_passe`, pourtant importés par `api_app/routes/auth.py:3`.

---

### 9.2 `api_app/services/rag_service.py`

#### `RAGService.__init__()`

| Attribut | Valeur |
|----------|--------|
| `self.qdrant_url` | `os.environ["QDRANT_URL"]` |
| `self.qdrant_api_key` | `os.environ["QDRANT_API_KEY"]` |
| `self.mistral_api_key` | `os.environ["MISTRAL_API_KEY"]` |
| `self.qdrant_client` | `QdrantClient(url, api_key, check_compatibility=False)` |
| `self.mistral_client` | `Mistral(api_key=…)` |
| `self.coll_copies` | `"tcf_copies_dataset"` |
| `self.coll_methode` | `"tcf_methodologie"` |

Crée (ou tolerate comme déjà présente) un index de payload `tache_id` de type `INTEGER` sur `tcf_copies_dataset`.

#### `_generer_embedding(texte: str) -> list[float] | None`

```python
self.mistral_client.embeddings.create(model="mistral-embed", inputs=[texte])
return response.data[0].embedding
```

Retourne `None` et journalise `[-] Erreur génération embedding : {e}` en cas d'échec.

#### `recuperer_contexte(texte_utilisateur: str, tache_id: int) -> dict`

| Étape | Requête | Filtre | Limite | Extraction |
|-------|---------|--------|--------|------------|
| 0 | `mistral-embed` sur `texte_utilisateur` | — | — | vecteur 1024 dims |
| 0 bis | si embedding `None` | — | — | **retourne `{"regles": [], "exemples": []}`** |
| 1 | `tcf_methodologie` | aucun | **3** | `payload["contenu_regle"]` |
| 2 | `tcf_copies_dataset` | `tache_id == {tache_id}` | **2** | `texte_candidat` + `evaluation_expert` |

```python
filtre_tache = Filter(must=[FieldCondition(key="tache_id", match=MatchValue(value=tache_id))])
```

**Retour :**

```python
{
  "regles":   ["…", "…", "…"],                 # ≤ 3 chaînes
  "exemples": [                                 # ≤ 2 dicts
    {"texte_candidat": "…", "evaluation_expert": {…}},
    {"texte_candidat": "…", "evaluation_expert": {…}},
  ],
}
```

**Comportement en cas de panne**

| Panne | Effet |
|-------|-------|
| Échec de l'embedding | Contexte vide, **pas d'erreur** → le LLM évalue sans RAG |
| Panne Qdrant sur la requête | **Exception non rattrapée** → remonte en `500` |
| `mistral-embed` renvoie un vecteur de mauvaise dimension | Erreur Qdrant → `500` |

> Le fallback silencieux de l'embedding est utile (dégradation gracieuse) mais **invisible pour l'appelant** : la réponse ne contient aucun indicateur permettant de savoir que l'évaluation a été faite sans références.

#### `recuperer_contexte_oral(content_sujet, task_type, task3_type) -> list[str]`

Méthode ajoutée avec le module oral (`rag_service.py:84-120`).

| Étape | Détail |
|-------|--------|
| 1 | Construction d'une requête textuelle : `"Méthodologie TCF Canada Expression Orale {task_type}[ {task3_type}] : {content_sujet}"` |
| 2 | Embedding `mistral-embed` sur cette requête (même `_generer_embedding`) |
| 3 | Si embedding `None` → retourne `[]` (fallback silencieux, comme l'écrit) |
| 4 | `query_points` sur `tcf_methodologie`, **sans filtre**, `limit=4` |
| 5 | Extraction de `payload["contenu_regle"]` **ou** `payload["text"]` (clé `text` tolérée mais **jamais produite** par `ingest_methodology.py`, qui n'écrit que `contenu_regle`) |
| 6 | Toute exception Qdrant est rattrapée → `[]` (contrairement à l'écrit, qui remonte en `500`) |

```python
context_rag = rag_service.recuperer_contexte_oral(topic.content, "TASK_3", "DIALECTICAL")
context_str = "\n---\n".join(context_rag) or "Aucun contexte spécifique trouvé."
```

> ⚠️ La recherche orale **ne filtre ni par tâche ni par document source** : les Top 4 chunks peuvent provenir indifféremment du PDF Expression Écrite ou du PDF Expression Orale ingérés dans la même collection `tcf_methodologie`. Aucun mécanisme ne garantit que le contexte injecté concerne l'oral.

---

### 9.3 `api_app/services/llm_service.py`

#### Fonction utilitaire de module

```python
def _compter_mots(texte: str) -> int:
    if not texte: return 0
    return len(texte.split())
```

Découpage sur **tous les espaces**. La ponctuation reste attachée aux mots : `"salut,"` compte pour 1. Le décompte est **légèrement différent** du décompte officiel du TCF (qui isole la ponctuation), et la valeur dépend de la normalisation des espaces par le candidat. À garder en tête pour tout affichage de « nombre de mots ».

#### `LLMService.__init__()` — `llm_service.py:67-79`

| Attribut | Valeur |
|----------|--------|
| `self.client` | `genai.Client(api_key=GEMINI_API_KEY ou LLM_API_KEY, http_options=HttpOptions(api_version="v1"))` |
| `self.modele` | `os.environ["LLM_MODEL_NAME"]` (défaut `gemini-3.8-flash`, préfixes `models/` / `google/` retirés) |

Lève `ValueError("❌ GEMINI_API_KEY est introuvable…")` si aucune clé n'est présente : **l'instanciation du service exige l'environnement**, y compris dans les tests (fixture `llm_service` de `tests/test_tcf_service.py`).

#### `_appeler_llm_json(system_prompt, user_prompt, response_schema=None, max_retries=3)` — `llm_service.py:428-463`

Appel unique vers Gemini, utilisé par l'écrit **et** l'oral :

```python
config = types.GenerateContentConfig(
    system_instruction=system_prompt,
    response_mime_type="application/json",
    temperature=0.0,
    response_schema=_clean_schema_for_gemini(response_schema),  # oral uniquement
)
response = self.client.models.generate_content(model=self.modele, contents=user_prompt, config=config)
return json.loads(response.text)
```

- `response_schema` (modèle Pydantic) n'est passé que pour l'oral ; `_clean_schema_for_gemini()` (`llm_service.py:41-63`) retire récursivement les clés `additionalProperties` rejetées par l'API Gemini.
- Retry **uniquement** sur `429` / `503` (détection par sous-chaîne dans le message d'erreur), backoff `2 * 2**attempt` secondes ; toute autre exception est relancée telle quelle.

#### `_generer_prompt_systeme(num_tache, bareme_max, regles, exemples) -> str`

Signature et comportement détaillés en [§11](#11-construction-du-prompt-llm).

#### `_analyser_une_tache(num_tache, bareme_max, donnees_tache, rag_service) -> dict | None`

Voir [§8.4](#84-étape-4--évaluation-dune-tâche).

#### `_determiner_niveaux_tcf(note_sur_20: float) -> tuple[str, str, str]`

Retourne `(cecrl, nclc, mention)`. Grille détaillée en [§10](#10-grille-de-notation-cecrl--nclc).

#### `_calculer_niveaux_par_tache(note_obtenue: float, note_max: int) -> tuple[str, str]`

```python
if note_max <= 0:  return "A1", "3 ou moins"
note_sur_20   = (note_obtenue / note_max) * 20
note_arrondie = round(note_sur_20)      # arrondi « banker » de Python
```

Mêmes paliers que ci-dessus mais **sans la mention** (retour à 2 éléments).

> `round()` en Python utilise l'arrondi *banker's rounding* (demi-pair) : `round(12.5) == 12`, `round(8.5) == 8`, `round(4.5) == 4`. C'est le comportement **effectivement testé** dans la suite, et il diverge de l'arrondi scolaire attendu (12.5 → 13, 8.5 → 9, 4.5 → 5).

#### `evaluer_session_complete(examen_payload, rag_service) -> dict`

Orchestrateur. Voir [§8.5](#85-étape-5--agrégation).

#### `_generer_tache_vide(num_tache, max_points, payload_tache) -> dict`

Construit le bloc à zéro pour une tâche non soumise. Voir [§7.2.3](#723-structure-dun-bloc-dévaluation-evaluationsi).

#### Méthodes du module Expression Orale

| Méthode | Emplacement | Rôle |
|---------|-------------|------|
| `generer_corrections_orales_batch(topics, rag_service)` | `llm_service.py:350-371` | Orchestrateur : sémaphore `MAX_CONCURRENT_CALLS` + `asyncio.gather` (sans `return_exceptions`) |
| `_traiter_un_sujet_oral(topic, rag_service)` | `llm_service.py:373-413` | RAG oral → prompt → Gemini (`response_schema`) → validation Pydantic → `OralTopicCorrectionItem` |
| `_obtenir_config_prompt_oral(topic)` | `llm_service.py:415-426` | Routage TASK_2 / TASK_3-DIALECTICAL / TASK_3-ANALYTICAL → (prompt, schéma) ; lève `ValueError` sinon |

Les prompts système sont externalisés dans `api_app/prompts/oral_prompts.py` :

| Constante | Utilisée pour |
|-----------|---------------|
| `PROMPT_SYSTEM_TASK_2` | Interaction / recherche d'informations (impose 5-8 répliques `{role, texte}`) |
| `PROMPT_SYSTEM_TASK_3_DIALECTICAL` | Prise de position (pour/contre/nuance) |
| `PROMPT_SYSTEM_TASK_3_ANALYTICAL` | Analyse (causes, conséquences, enjeux) |

> Contrairement à l'écrit, le JSON oral est **validé contre le schéma** (`response_schema.model_validate`) : une déviation du LLM lève une `ValidationError` Pydantic → `500` (avec son message détaillé renvoyé en clair par la route).

---

## 10. Grille de notation CECRL / NCLC

### 10.1 Barème global (note sur 20)

Implémenté dans `_determiner_niveaux_tcf()` — `llm_service.py:214-224`.

| Note (arrondie) | CECRL | NCLC | Mention |
|:---------------:|:-----:|:----:|---------|
| ≥ 18 | **C2** | 10+ | Excellent |
| ≥ 16 | **C1** | 10+ | Très Bien |
| ≥ 14 | **C1** | 9 | Bien |
| ≥ 12 | **B2** | 8 | Assez Bien |
| ≥ 10 | **B2** | 7 | Passable |
| ≥ 7 | **B1** | 6 | Médiocre |
| = 6 | **B1** | 5 | Insuffisant |
| ≥ 4 | **A2** | 4 | Très Insuffisant |
| < 4 | **A1** | 3 | À renforcer |

### 10.2 Projection par tâche

`_calculer_niveaux_par_tache()` — `llm_service.py:226-238`. La note de la tâche est ramenée sur 20 puis passe dans la même grille.

```
note_projetée = (note_obtenue / note_max) × 20
```

**Exemples :**

| Tâche | Note obtenue | Barème | Projection /20 | CECRL | NCLC |
|-------|-------------:|:------:|:--------------:|:-----:|:----:|
| 1 | 2.5 | 4 | 12,5 → 12 | B2 | 8 |
| 2 | 4.5 | 7 | 12,86 → 13 | B2 | 8 |
| 3 | 5.5 | 9 | 12,22 → 12 | B2 | 8 |
| 1 | 1.0 | 4 | 5,0 → 5 | A2 | 4 |
| 2 | 0.0 | 7 | 0 | A1 | 3 |

> La note obtenue est **prise telle que** le LLM la renvoie. Aucune validation de bornes n'est appliquée : une note `7.0` sur la Tâche 1 (max 4) est acceptée telle quelle, `round(35)` = 35 ⇒ `_determiner_niveaux_tcf` tombe dans le palier `else` (« A1 / 3 / À renforcer »), un résultat contre-intuitif.

### 10.3 Cohérence du total

`score.sur_20` est la **somme brute** des notes des tâches soumises, arrondie à 2 décimales. Il n'y a **pas de renormalisation** : `sur_20 ∈ [0, 20]` uniquement si le LLM respecte les barèmes.

### 10.4 Deux grilles distinctes coexistent dans le projet

| Contexte | Barème | Échelle NCLC | Implémentation |
|----------|--------|--------------|----------------|
| **Pipeline de données** (génération/notation du corpus) | 4 / 7 / 9 | `NCLC 1` … `NCLC 12` (entier) | `evaluate_copies.py` |
| **API runtime** | 4 / 7 / 9 → somme /20 | `"3"`, `"4"`, …, `"9"`, `"10+"` (chaîne) | `llm_service.py` |

Les deux systèmes sont **cohérents sur les notes** mais **divergent sur le format et les bornes du NCLC**. Toute fusion future des deux corpus devra traiter cette différence.

---

## 11. Construction du prompt LLM

### 11.1 Anatomie du prompt système

`_generer_prompt_systeme()` produit un prompt unique composé de 7 blocs :

```
┌─ 1. RÔLE ────────────────────────────────────────────────────┐
│ "Tu es un examinateur officiel intransigeant du TCF Canada     │
│  pour France Éducation International (FEI)."                    │
├─ 2. BARÈME ───────────────────────────────────────────────────┤
│ "La note maximale absolue pour cette tâche est de {bareme_max}│
│  points. Tu dois ventiler les sous-notes de l'évaluation      │
│  ('analyse') de manière à ce que leur somme soit strictement   │
│  égale à la note obtenue."                                     │
├─ 3. INSTRUCTIONS SPÉCIFIQUES (selon num_tache) ────────────────┤
├─ 4. RÈGLES RAG ────────────────────────────────────────────────┤
│ "Règles méthodologiques issues de la base de connaissances    │
│  (RAG) : … {regles}"                                          │
├─ 5. EXEMPLES RAG (few-shot) ──────────────────────────────────┤
│ "Exemples de copies de référence : {exemples}"                 │
├─ 6. RIGUEUR D'EXTRACTION DES ERREURS ─────────────────────────┤
│ "Ne liste que les vraies erreurs. S'il n'y a pas d'erreur,      │
│  renvoie un tableau vide []."                                  │
├─ 7. SCHÉMA JSON ATTENDU ───────────────────────────────────────┤
│ {json.dumps(structure_json_tache)}                            │
└────────────────────────────────────────────────────────────────┘
```

### 11.2 Instructions par tâche

| Tâche | Longueur exigée | Contrainte sur `version_modele_c2` | Structure imposée |
|-------|-----------------|-----------------------------------|------------------|
| **1** | 60 – 120 mots | **≤ 120 mots** (cible 100) | `\n\n` entre Salutation / Corps / Formule de politesse / Signature |
| **2** | 120 – 150 mots | **entre 120 et 150 mots** | `\n\n` entre Titre / Introduction / Développement / Recommandation / Signature |
| **3** | 120 – 180 mots | **≤ 170 mots** | `\n\n` : Titre (≤ 9 mots) / Partie 1 (45-55 mots) / Partie 2 (60-80 mots) / Conclusion (20-30 mots) |

> **Incohérence** : le schéma JSON annonce `version_corrigee` et `version_modele_c2` en T3 « **max 170** », alors que la consigne d'épreuve impose 180 mots. La divergence est introduite délibérément (commit `7a7c25a` « force strict word count limits for LLM model versions ») pour obtenir des versions modèle plus concises, mais elle produit un modèle C2 qui, pour la Tâche 3, est **hors marge de l'épreuve officielle** (120-180).

### 11.3 Schéma JSON injecté

```jsonc
{
  "tache": 1,
  "consigne": "Répéter ici scrupuleusement la consigne complète du sujet initial fournie.",
  "copie": { "texte_original": "", "nombre_mots": 0 },
  "score": { "obtenu": 0.0, "maximum": 4 },
  "niveau_estime": { "cecrl": "A1 à C2", "nclc": "3 à 10+" },
  "controle_methodologie": { /* 9 booléens, tous à true comme gabarit */ },
  "analyse": {
    "comprehension_sujet":   { "note": 0.0, "commentaire": "" },
    "respect_methodologie":  { "note": 0.0, "commentaire": "" },
    "coherence_cohesion":    { "note": 0.0, "commentaire": "" },
    "lexique":               { "note": 0.0, "commentaire": "" },
    "grammaire":             { "note": 0.0, "commentaire": "" },
    "orthographe":           { "note": 0.0, "commentaire": "" }
  },
  "statistiques": { /* richesse_lexicale, complexite_syntaxique, fluidite */ },
  "erreurs": [ /* 1 erreur gabarit, id: 1 */ ],
  "versions": { "version_corrigee": "…", "version_modele_c2": "…" },
  "coaching": { "points_forts": [], "points_a_ameliorer": [],
                "conseils": [], "objective_prochaine_copie": "" }
}
```

Le gabarit sert de **few-shot implicite** : en fournissant des valeurs par défaut non nulles (`note: 0.0`, `true`, `maximum: 4`), on oriente le modèle vers une structure complète plutôt que vers un JSON vide.

### 11.4 Prompt utilisateur

```
Consigne:
{consigne enrichie — pour la T3, inclut les 2 documents}

Copie du candidat:
{texte_candidat brut}
```

La copie est envoyée **telle quelle**, sans prétraitement, sans normalisation de la ponctuation, sans découpage en paragraphes.

### 11.5 Contraintes de comptage injectées

Le prompt comporte 3 rappels redondants sur les limites de mots (§3 du prompt, ligne 99 ; §3.1 de la tâche ; description de `versions`) et un encadré « 🚨 CONSIGNE DE COMPTAGE INVIOLABLE » demandant explicitement de « viser une cible basse » et de « supprimer les fioritures ». Cette accumulation est la trace d'une itération sur des débordements de longueur constatés en production (cf. commits `945563a` et `b345ed8`).

---

## 12. Pipeline de données (`data_pipeline/`)

Ce pipeline est **entièrement hors ligne** : il construit le contenu des deux collections Qdrant. Aucun de ces scripts n'est appelé par l'API.

### 12.1 Vue d'ensemble

```
   Mistral AI  ─────────────┐
   Groq API                 │
       │                    │
       ▼                    │
┌─────────────────┐         │  34 sujets
│ generate_       │         │  × 3 profils
│ candidates.py   │         │  × 6 niveaux CECRL
└────────┬────────┘         │  = 612 combinaisons
         │                  │
         ▼                  │
copies_candidates_brutes.jsonl   (788 enregistrements réels)
         │
         ▼
┌─────────────────┐   mistral-large-latest, temperature 0.1
│ evaluate_       │   barème 4 / 7 / 9 + NCLC 1-12
│ copies.py       │
└────────┬────────┘
         ▼
copies_evaluees.jsonl          (787 enregistrements)
         │                              │
         │                              └──▶ ingest_to_qdrant.py ──▶ Qdrant `tcf_copies_dataset`
         │
         └──▶ validate_dataset.py (contrôle qualité, stdlib seul)

   METHODOLOGIE_expression_ecrite_TCF_CANADA.pdf (20 p.)
   TAMARO_Methodologie_Expression_Orale.pdf
         │
         └──▶ ingest_methodology.py (pypdf, chunks 800/150, lots de 10, retry 429)
                    ──▶ Qdrant `tcf_methodologie`
```

### 12.2 Scripts

| Script | Rôle | Modèle | Sortie | Statut |
|--------|------|--------|--------|--------|
| `generate_candidates.py` | **Générateur principal** de copies simulées | `mistral-large-latest`, T=0.7 | `copies_candidates_brutes.jsonl` | ✅ Opérationnel |
| `generate_candidates111.py` | Variante / sauvegarde | Groq (`llama-3.3-70b`) via SDK Mistral | idem | ❌ Cassé (`AttributeError`) |
| `generate_dataset.py` | Dataset de fine-tuning chat (Groq) | `llama-3.3-70b-versatile`, T=0.7 | `tcf_dataset_preparation.jsonl` | ❌ Cassé (`NameError`) |
| `evaluate_copies.py` | **Notation experte** des copies | `mistral-large-latest`, T=0.1 | `copies_evaluees.jsonl` | ✅ Opérationnel |
| `validate_dataset.py` | Contrôle qualité du dataset | — (stdlib) | rapport console | ✅ Opérationnel |
| `ingest_to_qdrant.py` | Injection des copies évaluées | `mistral-embed` | Qdrant `tcf_copies_dataset` | ✅ Opérationnel |
| `ingest_methodology.py` | Chunking + injection de **tous** les PDF/TXT de `methodology_docs/` | `mistral-embed` + `pypdf` | Qdrant `tcf_methodologie` | ✅ Opérationnel |

#### `generate_candidates.py` en détail

**Banque de sujets** — `BANQUE_SUJETS` : **34 sujets** (10 en Tâche 1, 11 en Tâche 2, 13 en Tâche 3) :

```json
{
  "tache_id": 3,
  "consigne": "Les photos sur le CV, pour ou contre ?",
  "documents_contexte": ["Document 1 : …", "Document 2 : …"],
  "contraintes": { "min_mots": 120, "max_mots": 180, "type_texte": "Synthèse & Prise de position" }
}
```

`documents_contexte` est `[]` pour les tâches 1 et 2, et contient exactement 2 éléments pour la tâche 3.

**Profils de candidats** — `PROFILS_CANDIDATS` : **3 personas** simulant des.originaux linguistiques distincts.

| `profil_id` | Origine | Lexique | Style |
|-------------|---------|---------|-------|
| `candidat_debutant_limite` | Allophone | Très limité | Phrases juxtaposées, calques grossiers |
| `candidat_anglophone_syntaxe_intermediaire` | Anglophone | Intermédiaire | Accords genre/nombre oubliés, faux-amis |
| `candidat_expert_academique` | Universitaire | Soutenu | Figures de style, subordonnées complexes |

**Niveaux cibles** — `NIVEAUX_CECRL = ["A1","A2","B1","B2","C1","C2"]` avec équivalence NCLC :

```python
CONVERSION_NCLC = {"A1":"NCLC 1-2", "A2":"NCLC 3-4", "B1":"NCLC 5-6",
                   "B2":"NCLC 7-8", "C1":"NCLC 9-10", "C2":"NCLC 11-12"}
```

**Boucle principale :** `34 sujets × 3 profils × 6 niveaux = 612` combinaisons, écrites en streaming (mode `append`) avec `time.sleep(2.0)` entre chaque appel.

**Politique de retry :** `retries = 5`, `backoff_delay = 4 s`, **doublement** à chaque `429` / `rate_limited` (4 → 8 → 16 → 32 s). Toute autre exception ⇒ abandon immédiat avec `None`.

**Schéma d'un enregistrement brut :**

```json
{
  "tache_id": 1,
  "sujet_consigne": "…",
  "documents_contexte": [],
  "contraintes": { "min_mots": 60, "max_mots": 120, "type_texte": "Message amical" },
  "metadata_candidat": {
    "profil_id": "candidat_debutant_limite",
    "niveau_cecrl_cible": "A1",
    "equivalent_nclc": "NCLC 1-2"
  },
  "texte_candidat": "…"
}
```

#### `evaluate_copies.py` en détail

Prompt de notation comportant le sujet, les documents contextuels (si présents), la copie délimitée par les sentinelles `--- DÉBUT DE LA COPIE ---` / `--- FIN DE LA COPIE ---`, et 4 critères :

1. respect de la consigne et de la longueur,
2. cohérence / structure / connecteurs,
3. richesse lexicale et syntaxique,
4. grammaire et orthographe.

**JSON attendu :**

```json
{
  "evaluation_analytique": {
    "note_obtenue": 0,
    "note_maximale_tache": 4,
    "niveau_nclc_estime": "NCLC 5",
    "analyse_critères": {
      "consigne_et_structure": "…",
      "lexique_et_grammaire": "…"
    },
    "justification_pedagogique": "…"
  }
}
```

Le champ `evaluation_expert` est ensuite fusionné **dans l'enregistrement d'origine**, qui est réécrit tel quel dans `copies_evaluees.jsonl` (7 clés).

#### `validate_dataset.py` en détail

Porte de qualité, **sans aucune dépendance réseau** :

1. Le fichier existe-t-il ?
2. Chaque ligne est-elle du JSON valide ? (sinon `lignes_corrompues += 1`)
3. Les 4 clés requises sont-elles présentes ? → `["tache_id", "sujet_consigne", "texte_candidat", "evaluation_expert"]`
4. La note est-elle dans `[0, plafond]` avec `plafond = 4 | 7 | 9` selon la tâche ?
5. `note_obtenue` est-elle présente ?
6. Répartition par tâche + distribution NCLC.

**Verdict final** : `🎉 SUCCÈS` seulement si `lignes_corrompues == 0 and alertes_bareme == 0`.

**État actuel : `copies_evaluees.jsonl` passe le contrôle (787/787).**

### 12.3 Datasets

| Fichier | Enregistrements | T1 / T2 / T3 | Niveaux CECRL | Statut |
|---------|:---------------:|:------------:|---------------|--------|
| `copies_candidates_brutes.jsonl` | **788** (+ 2 lignes vides) | 319 / 217 / 252 | 132/132/131/131/131/131 | Source de `evaluate_copies.py` |
| `copies_candidates_brutes1.jsonl` | **171** | 134 / 19 / 18 | 29/29/28/28/28/29 | Artefact orphelin (aucun script ne le lit) |
| `copies_evaluees.jsonl` | **787** | 318 / 217 / 252 | 132/132/131/131/130/131 | Source de `ingest_to_qdrant.py` |
| `text_file.json` | 1 payload (3 tâches) | — | — | Exemple de requête, non référencé par le code |

> **Écart 788 → 787** : un enregistrement s'est perdu entre les deux étapes (tâche 1). Et **788 > 612** (nombre attendu pour une exécution complète) : le fichier est l'accumulation de plusieurs exécutions interrompues, ce qui explique aussi les 2 lignes vides. Les scripts écrivent tous en mode `append` sans dé-duplication.

#### Répartition du corpus évalué

| Dimension | Répartition |
|-----------|-------------|
| **Tâche** | T1 : 318 · T2 : 217 · T3 : 252 |
| **Profil** | `candidat_debutant_limite` : 269 · `candidat_anglophone_syntaxe_intermediaire` : 259 · `candidat_expert_academique` : 259 |
| **Niveau cible** | A1 : 132 · A2 : 132 · B1 : 131 · B2 : 131 · C1 : 130 · C2 : 131 |
| **NCLC estimé par le LLM** | NCLC 3 : 47 · NCLC 4 : 199 · NCLC 5 : 185 · NCLC 6 : 76 · NCLC 7 : 82 · NCLC 8 : 39 · NCLC 9 : 25 · NCLC 10 : 113 · NCLC 11 : 21 |
| **Notes moyennes** | T1 : 2,47/4 · T2 : 4,70/7 · T3 : 5,58/9 |

> **Biais du corpus** : le LLM n'a **jamais** attribué les niveaux extrêmes — aucun `NCLC 1`, `NCLC 2` ni `NCLC 12` sur 787 enregistrements. La distribution est fortement concentrée sur NCLC 4-5 et NCLC 10. Ces copies servent de few-shot : le modèle peut donc être **biaisé vers le milieu de l'échelle**.

### 12.4 Sources méthodologiques

Le dossier `data_pipeline/methodology_docs/` contient **deux PDF** (l'ancien `METHODOLOGIE_TCF_CANADA_TAYES.pdf` a été **supprimé** du dépôt et remplacé) :

| Fichier | Taille | Usage |
|---------|--------|-------|
| `METHODOLOGIE_expression_ecrite_TCF_CANADA.pdf` | ~211 Ko | Source du RAG **Expression Écrite** (ancien PDF TAYES renommé/remplacé) |
| `TAMARO_Methodologie_Expression_Orale.pdf` | ~55 Ko | Source du RAG **Expression Orale** (module TAMARO) |

`ingest_methodology.py` traite **indistinctement** tous les `*.pdf` et `*.txt` du dossier : les chunks des deux documents sont mélangés dans la collection `tcf_methodologie` (aucun champ de filtrage par épreuve n'est ajouté au payload — seuls `source_document`, `index_chunk`, `contenu_regle` sont écrits).

| Pages (PDF écrit) | Contenu |
|------:|---------|
| 1 | Couverture |
| 2 | Structure de l'épreuve (durée, barèmes, longueurs) |
| 3-5 | Méthodologie Tâche 1 + exemples corrigés annotés |
| 6-10 | Types d'exercices T1 (courrier formel/informel, courriel, petite annonce) |
| 11-15 | Méthodologie Tâche 2 (9 étapes) + témoignage + commentaire |
| 16-18 | Méthodologie Tâche 3 (6 blocs) + connecteurs d'opposition + résumés annotés |
| 19 | Cas pratique Tâche 3 (les fast-foods) |
| 20 | Pied de page |

> ⚠️ **Droits d'auteur** : l'ancien PDF portait la mention « Ce document est la propriété exclusive de TAYES FORMATION. Reproduction interdite sans autorisation préalable. » Il a été retiré du dépôt, mais les **deux PDF actuels** restent versionnés dans git et **embeddés dans une base vectorielle**. Vérifiez les droits de chacun (dont `TAMARO_Methodologie_Expression_Orale.pdf`) avant toute mise en production ou redistribution.

---

## 13. Base vectorielle Qdrant

### 13.1 `tcf_copies_dataset` — corpus few-shot

| Attribut | Valeur |
|----------|--------|
| **Rôle** | Exemples de copies notées, injectés dans le prompt (Top 2 filtrés par tâche) |
| **Dimension** | 1024 |
| **Distance** | `COSINE` |
| **Vecteur** | Embedding de `texte_candidat` **uniquement** |
| **Index payload** | `tache_id` → `INTEGER` |
| **ID des points** | `uuid5(NAMESPACE_DNS, md5(texte))` — **idempotent** (ré-ingestion sans doublon) |
| **Upsert** | Par lots de 25, `wait=True`, `time.sleep(0.5)` entre les lots |

**Payload :**

```json
{
  "tache_id": 1,
  "texte_candidat": "…",
  "sujet_consigne": "…",
  "documents_contexte": [],
  "metadata_candidat": { "profil_id": "…", "niveau_cecrl_cible": "…", "equivalent_nclc": "…" },
  "evaluation_expert": {
    "note_obtenue": 1,
    "note_maximale_tache": 4,
    "niveau_nclc_estime": "NCLC 3",
    "analyse_critères": { "consigne_et_structure": "…", "lexique_et_grammaire": "…" },
    "justification_pedagogique": "…"
  }
}
```

### 13.2 `tcf_methodologie` — règles

| Attribut | Valeur |
|----------|--------|
| **Rôle** | Règles de barème et consignes méthodologiques (Top 3 pour l'écrit, Top 4 pour l'oral) |
| **Dimension** | 1024, `COSINE` |
| **Source** | `methodology_docs/*.pdf` **et** `*.txt` (actuellement : PDF expression écrite + PDF expression Orale, mélangés) |
| **Extraction** | `pypdf.PdfReader`, pages concaténées avec le séparateur `\n--- [Page N] ---\n` |
| **Chunking** | Fenêtre glissante : taille 800 caractères, chevauchement 150 (**stride 650**) ; embeddings générés par **lots de 10** avec retry 429 (5 s) |
| **ID des points** | `uuid5(NAMESPACE_DNS, md5(chunk))` — idempotent |

**Payload :**

```json
{ "source_document": "METHODOLOGIE_expression_ecrite_TCF_CANADA.pdf", "index_chunk": 7, "contenu_regle": "…" }
```

> Le chunking est **naïf** (découpe purement par caractères, sans respect des phrases ni des paragraphes) : un chunk peut commencer ou finir au milieu d'une phrase, ce qui dégrade la qualité des règles injectées.

### 13.3 Ré-ingestion

Les deux scripts d'ingestion sont **idempotents** grâce aux identifiants déterministes : relance ⇒ écrasement des mêmes points, pas de duplication. En revanche, un changement de modèle d'embedding ou de dimension **invalide tout le corpus** et nécessite une reconstruction complète.

---

## 14. Tests

### 14.1 Configuration

`pyproject.toml` :

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
asyncio_mode = "strict"
```

- `pythonpath = ["."]` rend `api_app` importable sans installation.
- `asyncio_mode = "strict"` impose le décorateur explicite `@pytest.mark.asyncio` sur chaque test asynchrone.
- **Aucun `conftest.py`** : pas de fixtures partagées, pas de blocage réseau, pas de stub d'environnement.
- `pytest`, `pytest-asyncio` et `pypdf` ne figurent **pas** dans `requirements.txt` (présents uniquement dans le `venv` local).

### 14.2 Exécution

```bash
pytest tests/ -v
```

**Résultat réel constaté (revérifié en octobre 2026) : `13 passed, 1 failed`** (le README annonce « 14 tests » sans préciser l'état).

> ⚠️ Depuis la bascule Gemini, la fixture `llm_service` **requiert `GEMINI_API_KEY`** (défaut `LLM_API_KEY`) dans l'environnement, sous peine de `ValueError` à l'instanciation. Le test d'intégration instancie également une vraie `RAGService()` (connexion Qdrant + `create_payload_index` réel).

### 14.3 Inventaire des tests

`tests/test_tcf_service.py` — 3 fonctions de test, 14 cas au total.

#### Test 1 — `test_determiner_niveaux_tcf_global` (8 cas, paramétré)

Fixture `llm_service` → `LLMService()` réel (aucun appel réseau à la construction).

| Note /20 | CECRL attendu | NCLC attendu |
|---------:|:-------------:|:------------:|
| 18.0 | C2 | 10+ |
| 15.0 | C1 | 9 |
| 12.5 | B2 | 8 |
| 10.0 | B2 | 7 |
| 8.5 | B1 | 6 |
| 6.0 | B1 | 5 |
| 4.5 | A2 | 4 |
| 2.0 | A1 | 3 |

✅ **8/8 passent.** Couvre les paliers `>=18`, `>=14`, `>=12`, `>=10`, `>=7`, `==6`, `>=4`, `else`.

> Le 3ᵉ élément du tuple (la mention) est reçu puis ignoré via `cecrl, nclc, _`. **Les mentions ne sont jamais testées.**

#### Test 2 — `test_calculer_niveaux_par_tache_proportionnel` (5 cas, paramétré)

| Note obtenue | Barème | CECRL attendu |
|-------------:|:------:|:-------------:|
| 2.5 | 4 | B2 |
| 4.5 | 7 | B2 |
| 5.5 | 9 | B2 |
| 1.0 | 4 | A2 |
| 0.0 | 7 | A1 |

✅ **5/5 passent.** Valide la projection `(note / max) × 20` sur les trois barèmes réels (4, 7, 9).

> Le cas `note_max <= 0` et le 2ᵉ retour (NCLC) ne sont pas testés.

#### Test 3 — `test_evaluation_complete_endpoint_success` (1 cas, `@pytest.mark.asyncio`)

Test d'intégration bout-en-bout sur l'**application FastAPI réelle**, via `httpx.ASGITransport` (sans socket).

- **Payload** : `tache_1` et `tache_2` renseignées, **`tache_3 = None`** (teste le chemin « tâche non soumise »).
- **Auth** : en-tête `X-API-Key: tcf_secret_dev_key_2026` **codé en dur** — doit être égal à `TCF_API_KEY` du `.env`, sinon `403`.
- **Mock** : `AsyncMock` posé sur `LLMService.evaluer_session_complete` via
  `setattr(LLMService, "evaluer_session_complete", mock)`.
- **Assertions** : `status_code == 200`, `status == "success"`, `bilan_global.score.sur_20 == 8.0`,
  `bilan_global.niveau.cecrl == "B1"`, `evaluations[0].niveau_estime.cecrl == "C1"`,
  `evaluations[2].score.obtenu == 0.0`, `evaluations[2].niveau_estime.cecrl == "A1"`.

❌ **ÉCHEC** — `fastapi.exceptions.ResponseValidationError`. La réponse du mock ne respecte pas le modèle de sortie :

```
response.meta                                              → manquant
response.bilan_global.score.pourcentage                     → manquant
response.bilan_global.score.mention                         → manquant
response.bilan_global.resume                                → manquant
```

Le mock est **périmé** par rapport au contrat de sortie : `evaluer_session_complete` émet toujours `meta`, `bilan_global.score.{pourcentage,mention}` et `bilan_global.resume`, mais la fixture de test ne les fournit pas.

### 14.4 Couverture

| Composant | Couvert | Remarque |
|-----------|:-------:|----------|
| `_determiner_niveaux_tcf` | ✅ 8 cas | mentions non testées |
| `_calculer_niveaux_par_tache` | ✅ 5 cas | garde `note_max <= 0` non testée |
| Route + validation + auth | ⚠️ indirect | 1 seul cas, et il échoue |
| `evaluer_session_complete` | ❌ | entièrement mocké |
| `_generer_tache_vide` | ⚠️ | testé indirectement (tâche 3), mais via le mock |
| `_compter_mots` | ❌ | |
| `_generer_prompt_systeme` | ❌ | |
| `RAGService` | ❌ | aucun test |
| `data_pipeline/*` (7 scripts) | ❌ | aucun test |
| Chemin `403` (clé invalide) | ❌ | |
| Chemin `500` | ❌ | |

> Le `MagicMock()` nommé `mock_rag` dans le test d'intégration n'est **jamais injecté** : la dépendance `get_rag_service` construit une vraie `RAGService()`, qui instancie un `QdrantClient` et appelle `create_payload_index`. Le test touche donc réellement le réseau au travers de `Depends`. De plus, `setattr` est posé sur la **classe** sans teardown (pas de `monkeypatch`) : le patch fuit vers les tests suivants de la session.

### 14.5 Recommandations de couverture

1. Décorréler les tests d'intégration de Qdrant (injection d'un faux `RAGService` via `app.dependency_overrides`).
2. Ajouter les cas manquants : `403`, `500`, tâche `null` isolée, `text_file.json` en entrée.
3. Tester `_compter_mots`, `_generer_prompt_systeme` et `_generer_tache_vide`.
4. Tester les 7 scripts de `data_pipeline` sur des fixtures JSONL miniatures (sans réseau, via monkeypatch du client Mistral).
5. Migrer `setattr` vers `monkeypatch.setattr`.
6. Ajouter `pytest`, `pytest-asyncio`, `pypdf`, `groq` à un `requirements-dev.txt`.

---

## 15. Déploiement

### 15.1 Docker

`Dockerfile` :

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD uvicorn api_app.main:app --host 0.0.0.0 --port $PORT
```

`.dockerignore` **exclut** : `venv/`, `__pycache__/`, `.pytest_cache/`, `.git/`, `data_pipeline/`, `tests/`, `.env`, `.env.example`, `*.pyc`.

**Conséquences :**
- L'image **ne contient ni le pipeline de données ni les tests** : c'est le plus léger possible pour le runtime, mais il faut construire les collections Qdrant depuis une machine de développement.
- `.env` est exclu ⇒ les variables doivent être injectées par la plateforme.
- Le `CMD` est en **forme shell** (sans `JSON` exec) : `$PORT` est bien interpolé par `/bin/sh -c`. En forme exec (`["uvicorn", …]`) il ne le serait pas.
- **Bug** : la commande est `uvicorn … --port $PORT` (le paramètre `--port` est vide si `PORT` n'est pas défini, produisant `--port` orphelin suivi de l'argument suivant). Préférer `--port ${PORT:-8000}`.
- **Bloquant** : `requirements.txt` ne contient pas `google-genai` alors que `llm_service.py` l'importe au chargement. `docker build` **réussit** (pip installe les 9 dépendances listées) mais le conteneur **crashe au démarrage** sur `ModuleNotFoundError: No module named 'google'`. Ajouter `google-genai==2.31.0` (et idéalement `pytest`, `pypdf`, `groq` pour le pipeline) avant toute déploiement.

```bash
docker build -t api-tcf .
docker run -p 8000:8000 --env-file .env api-tcf
```

### 15.2 Simulateur local — `docker-compose.vps-sim.yml`

```yaml
services:
  vps_llm_engine:
    image: ollama/ollama:latest
    container_name: vps_llm_simulation
    ports: ["11434:11434"]
    volumes: [ollama_storage:/root/.ollama]
    restart: unless-stopped
```

Fournit un **serveur Ollama** local (port 11434) pour tester un LLM hors cloud. ⚠️ L'API **ne l'utilise pas en l'état** : `llm_service.py` ne cible que l'API Gemini. Pour y brancher le backend, il faudrait le support `LLM_BASE_URL` spécifié dans `prompt_LLM_PROVIDER_SWITCHING_IMPLEMENTATION.md` (non implémenté).

### 15.3 Render

`render.yaml` :

```yaml
services:
  - type: web
    name: api-simulateur-ec-tcf
    runtime: docker
    envVars:
      - key: GEMINI_API_KEY   # sync: false → à saisir dans le dashboard (MANQUANT dans le render.yaml actuel)
      - key: MISTRAL_API_KEY
      - key: QDRANT_URL
      - key: QDRANT_API_KEY
      - key: TCF_API_KEY
```

Le `render.yaml` versionné ne déclare que les 4 variables d'origine (`MISTRAL_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `TCF_API_KEY`) : **`GEMINI_API_KEY` doit être ajoutée manuellement** dans le dashboard, sans quoi le service crashe au premier appel `LLMService()`.

### 15.4 Checklist de mise en production

- [ ] **Ajouter `google-genai==2.31.0` à `requirements.txt`** (et `GEMINI_API_KEY` au dashboard / `render.yaml`) — sans quoi le service ne démarre pas
- [ ] `TCF_API_KEY` réellement définie (jamais laissée sur la valeur de repli)
- [ ] **Ajouter `CORSMiddleware`** — sans lui, **aucun appel depuis un navigateur React ne fonctionnera** (le RAG n'a pas d'`Access-Control-Allow-Origin`). Le README mentionne un « Frontend (React) » sans jamais configurer le CORS.
- [ ] Remplacer la comparaison `!=` de la clé API par `hmac.compare_digest`
- [ ] Remplacer l'appel synchrone Gemini par `client.aio` (SDK `google-genai` asynchrone) pour un vrai non-blocage
- [ ] Rendre le `RAGService` / `LLMService` **singletons** (`lru_cache` ou `lifespan`)
- [ ] Isoler les pannes de tâche : soit restaurer un `gather(return_exceptions=True)`, soit rattraper localement pour renvoyer un bilan partiel
- [ ] Supprimer le `sleep(1.0)` conditionnel à `MAX_CONCURRENT_LLM_CALLS == 1` (hack de rate-limit inutile avec le retry Gemini)
- [ ] Cacher les prompts système (seuls les blocs RAG changent d'une requête à l'autre)
- [ ] Servir la réponse via `StreamingResponse` ou un mécanisme de job asynchrone (les appels séquentiels peuvent dépasser 30 s)
- [ ] Ne plus renvoyer `str(e)` au client en `500` (fuite d'information)
- [ ] Restreindre `/docs` et `/openapi.json` en production
- [ ] Fixer la ré-ingestion Qdrant dans un job séparé, exécuté avant le déploiement du code
- [ ] Vérifier la licence des **deux** PDF de méthodologie (écrit + oral TAMARO)

### 15.5 Performance

| Facteur | Valeur |
|---------|--------|
| Latence typique (écrit) | **somme de 3 appels Gemini séquentiels** ≈ 9 – 30 s (contre 10-30 s en parallèle auparavant) |
| Latence typique (oral) | `ceil(n_topics / 3)` × ~3-8 s (sémaphore à 3) |
| Surcoût RAG | ~500 ms par tâche (1 embedding Mistral + requêtes Qdrant) |
| Parallélisme écrit | **aucun** (séquentiel) ; `MAX_CONCURRENT_LLM_CALLS` ne pilote qu'un sleep conditionnel |
| Parallélisme oral | sémaphore `MAX_CONCURRENT_CALLS` + `asyncio.gather` |
| Offloading | `asyncio.to_thread` pour l'appel Gemini (mais **pas** pour le RAG) |
| Levier principal | Réintroduire le parallélisme sur l'écrit + cache applicatif sur le bloc « règles + schéma JSON » (prompts quasi identiques d'une requête à l'autre) |

---

## 16. Points d'attention et écarts constatés

Cette section relève les écarts **vérifiés** entre la documentation existante, l'intention du code et le comportement réel.

### 16.1 Bloquant

| # | Constat | Emplacement | Impact |
|---|---------|-------------|--------|
| 1 | **Le test d'intégration échoue** — le mock ne respecte pas `TCFEvaluationGlobaleResponse` (4 champs manquants) | `tests/test_tcf_service.py:65-94` | `1 failed, 13 passed`. CI rouge. |
| 2 | **`google-genai` absent de `requirements.txt`** alors que `llm_service.py` l'importe au chargement | `llm_service.py:11` vs `requirements.txt` | Image Docker fonctionnelle à l'build mais **crash au démarrage** (`ModuleNotFoundError`). Idem pour tout `pip install -r requirements.txt` neuf. |
| 3 | **`api_app/routes/auth.py` n'est pas monté** dans `main.py` (seuls `evaluation.router` et `oral_correction.router` sont inclus) | `main.py:17-18` vs `auth.py:5` | `POST /api/v1/auth/token` **n'existe pas**, contrairement au README et au `tokenUrl` déclaré en `evaluation.py:70`. |
| 4 | **`auth.py` importe deux symboles inexistants** : `creer_access_token`, `verifier_mot_de_passe` ne sont pas dans `security.py` | `auth.py:3` vs `security.py` | `ImportError` dès que le module est importé. Le fichier est **mort**. |
| 5 | **Aucun middleware CORS** dans `main.py` | `main.py` | Un front React navigateur ne peut pas appeler l'API. Le README annonce pourtant un front React. |

### 16.2 Fonctionnel

| # | Constat | Emplacement | Impact |
|---|---------|-------------|--------|
| 6 | **Dénominateur global toujours fixé à 20** | `llm_service.py:298-299` | Soumettre 1 seule tâche ⇒ score plafonné à 4/20 ⇒ CECRL A2. Aucun indicateur de tâches soumises dans la réponse. |
| 7 | **`consigne` de la tâche 3 réécrite sans les libellés de documents** | `llm_service.py:289` vs `189-193` | `_analyser_une_tache` construit `"Document 1 :\n…"` puis `evaluer_session_complete` **réécrit** `consigne` avec `"TITRE : …\n\n<doc1>\n\n<doc2>"` : les libellés `Document 1/2` disparaissent de la réponse finale. |
| 8 | **Le prompt T3 et la limite de 180 mots** sont en tension avec la consigne « max 170 mots » du schéma | `llm_service.py:102-103` vs `156` | La `version_modele_c2` de la tâche 3 sort de la marge officielle de l'épreuve (120-180). |
| 9 | **Traitement séquentiel des 3 tâches** (l'ancien `asyncio.gather` a été supprimé) | `llm_service.py:244-296` | Latence = somme des 3 appels Gemini. Une erreur sur une tâche annule tout le bilan (y compris les tâches déjà payées). `MAX_CONCURRENT_LLM_CALLS` ne parallélise **rien** côté écrit. |
| 10 | ~~`version_modele_c1` vs `version_modele_c2`~~ **corrigé dans le README** (oct. 2026) | `llm_service.py:143` | — |
| 11 | ~~`objectif_prochaine_copie` vs `objective_prochaine_copie`~~ **corrigé dans le README** (oct. 2026) | `llm_service.py:145` | — |
| 12 | ~~`bilan_global.score.maximum` documenté mais non émis~~ **corrigé dans le README** (oct. 2026) | README | — |
| 13 | **`nombre_mots_candidat` / `nombre_mots_exemple`** absents des tâches vides | `llm_service.py:251-252` vs `328-348` | Un client qui lit ces clés sans `.get()` casse sur les tâches non soumises. |
| 14 | **`analyse` et `statistiques` valent `{}`** (et non la structure à 6/3 axes) sur les tâches non soumises | `llm_service.py:343-344` | Forme de réponse **non uniforme** selon la tâche. |
| 15 | **Aucune borne sur la note renvoyée par le LLM** | `llm_service.py:246,263,280` | Une note hors barème est acceptée ; `round(35) = 35` retombe sur le palier `else` ⇒ « A1 / À renforcer », résultat contre-intuitif. |
| 16 | **Aucune tolérance de la déviation JSON du LLM** (écrit) | `llm_service.py:454` puis `246` | `JSONDecodeError` ou `KeyError('obtenu')` ⇒ `500` **après** avoir payé l'appel Gemini. |
| 17 | **`task3_type` non requis côté schéma** pour `TASK_3` | `schemas/oral.py:17-21` | Un sujet TASK_3 sans `task3_type` provoque un `ValueError` → **500** au lieu d'un **422** de validation. |
| 18 | **`regenerate-correction` : le `400` annoncé est inatteignable** | `oral_correction.py:61-69` | Le `raise HTTPException(400)` est à l'intérieur du `try` et rattrapé par le `except Exception` → retransformé en `500`. |
| 19 | **Batch oral : un seul sujet en échec annule tout le batch** | `llm_service.py:365` | `asyncio.gather` sans `return_exceptions=True` sur le flux oral. |
| 20 | **RAG oral non filtré** : Top 4 de `tcf_methodologie` sans distinction écrit/oral ni par tâche | `rag_service.py:100-104` | Le contexte méthodologique injecté peut concerner l'expression écrite pour un sujet d'oral. |

### 16.3 Sécurité

| # | Constat | Emplacement |
|---|---------|-------------|
| 21 | **Valeur de repli de la clé API** : `"cle_par_defaut_si_vide"` | `security.py:13` |
| 22 | **Comparaison non constante dans le temps** (`!=` au lieu de `hmac.compare_digest`) | `security.py:16` |
| 23 | **`str(e)` renvoyé au client en 500** (messages d'erreur de SDK tiers, y compris `ValidationError` Pydantic détaillée sur l'oral) | `evaluation.py:87`, `oral_correction.py:42,69` |
| 24 | **Comptes en dur** dans le code mort `auth.py` (`admin_tcf` / hash SHA-256 du mot de passe), et valeur de la clé d'exemple publiée dans le README | `auth.py:8-15`, README |
| 25 | **Hash SHA-256 brut** (sans sel) du mot de passe | `auth.py:12` |
| 26 | **`/docs`, `/redoc`, `/openapi.json` publics** (non protégés) | `main.py` |
| 27 | **PDF sous droits d'auteur** versionnés dans git **et** embeddés dans un vector store (PDF écrit + PDF oral TAMARO) | `methodology_docs/` |
| 28 | **`.env` non versionné** (correct) mais l'exemple de clé est publié | `.gitignore`, README |

### 16.4 Performance & robustesse

| # | Constat | Emplacement |
|---|---------|-------------|
| 29 | **`RAGService` et `LLMService` recréés à chaque requête** (nouveau `QdrantClient`, `create_payload_index` systématiquement rappelé) — idem côté oral | `evaluation.py:63-67`, `oral_correction.py:16-20` |
| 30 | **Appel RAG bloquant dans la coroutine** (non passé en offloading, contrairement à Gemini) | `llm_service.py:181` |
| 31 | **Aucune mise en cache** des embeddings ni des prompts système | `llm_service.py:197-198` |
| 32 | **Exposant de prompt volumineux** : les 2 exemples RAG (texte + évaluation experte complète) sont sérialisés en JSON dans chaque prompt | `llm_service.py:183` |
| 33 | **Le fallback RAG silencieux** ne laisse aucune trace dans la réponse (écrit **et** oral) | `rag_service.py:43-44`, `96-97` |
| 34 | **Régression de parallélisme** : 3 appels Gemini séquentiels côté écrit (voir #9) | `llm_service.py:244-296` |

### 16.5 Qualité des données

| # | Constat | Impact |
|---|---------|--------|
| 35 | **Écritures en `append` sans dé-duplication** dans `generate_candidates.py` et `evaluate_copies.py` | Relancer duplique les enregistrements (explique 788 > 612) |
| 36 | **2 lignes vides** dans `copies_candidates_brutes.jsonl` | Tolérées par `validate_dataset.py`, pas par les autres |
| 37 | **Biais du corpus** : aucun NCLC 1, 2 ni 12 sur 787 enregistrements | Few-shot biaisés vers le milieu de l'échelle |
| 38 | **Chunking naïf par caractères** (800/150) | Règles RAG coupées en milieu de phrase |
| 39 | **`copies_candidates_brutes1.jsonl` orphelin** (171 lignes) | Fichier mort, non référencé |
| 40 | **`text_file.json` et `tests/test.json` quasi identiques** | Duplication de fixtures |
| 41 | **Les deux PDF méthodologie alimentent la même collection sans étiquette** | Le RAG oral peut injecter des règles d'écrit (voir #20) |

### 16.6 Scripts cassés

| Script | Défaut | Emplacement |
|--------|--------|-------------|
| `generate_dataset.py` | **`NameError: name 'config' is not defined`** — la f-string de `user_prompt` référence `config`, jamais lié, et est construite **avant** le `try`. Le script ne peut pas s'exécuter. | `generate_dataset.py:70,74,86` |
| `generate_dataset.py` | Chemin de sortie `"../datasets"` **relatif au CWD** (tous les autres scripts utilisent un chemin absolu dérivé de `__file__`). | `generate_dataset.py:120` |
| `generate_candidates111.py` | **Appel de style Groq (`client.chat.completions.create`) sur un client Mistral** ⇒ `AttributeError`. Exige en plus `GROQ_API_KEY` inutilisé, sans retry 429. | `generate_candidates111.py:349` |
| `evaluate_copies.py` | `evaluation["evaluation_analytique"]` non protégé ⇒ un `KeyError` avorte l'intégralité d'un run de 787 enregistrements. | `evaluate_copies.py:131` |
| `ingest_to_qdrant.py` | `donnees["evaluation_expert"]` en accès direct, alors que c'est le fichier enrichi. | `ingest_to_qdrant.py:117` |

### 16.7 Dépendances & configuration

| # | Constat |
|---|---------|
| 42 | **`google-genai` absent de `requirements.txt`** (voir #2) ; `pytest`, `pytest-asyncio`, `pypdf`, `groq` toujours absents alors que 4 scripts / la suite de tests en dépendent. |
| 43 | `python-jose` et `passlib` **déclarés mais jamais importés** (le `auth.py` mort importerait `creer_access_token`, qui utiliserait probablement `jose`). |
| 44 | `oauth2_scheme` déclaré dans `evaluation.py:70` mais **jamais utilisé** comme dépendance ; son `tokenUrl` pointe vers une route inexistante. |
| 45 | **Aucun `__init__.py`** : les paquets ne fonctionnent que comme namespace packages PEP 420. `uvicorn api_app.main:app` échoue si le CWD n'est pas la racine (seul `api_app/prompts/__init__.py` existe désormais). |
| 46 | **Incohérence de version Python** : README « 3.10+ », Dockerfile `3.12-slim`, venv local `3.14`. |
| 47 | `documents_contexte: Optional[List[str]] = Field(default=[])` — **défaut mutable** (toléré par Pydantic v2, mais anti-pattern). `evaluation.py:17` |
| 48 | `tests/test_tcf_service.py:100-103` — `MagicMock()` `mock_rag` créé mais **jamais injecté** ; `setattr` sur la classe sans teardown (fuite entre tests). |
| 49 | `data_pipeline/generation/generate_candidates.py:379` — `os.remove(fichier_sorties)` laissé en commentaire : risque de purge accidentelle lors d'un décommentage. |
| 50 | `pyproject.toml` ne déclare **aucune métadonnée de projet** (ni `[project]`, ni `[build-system]`) : le dépôt n'est pas installable comme paquet, seulement exécutable depuis la racine. |
| 51 | `schemas/oral.py:24` — `Field(min_items=1)` est **déprécié** sous Pydantic v2 (avertissement `PydanticDeprecatedSince20` en console) ; utiliser `min_length=1`. |
| 52 | `schemas/oral.py:35-36` — `return [str(v)]` après un `return` : **code mort** dans `_coerce_string_to_list`. |
| 53 | `render.yaml` **n'expose pas** `GEMINI_API_KEY` / `LLM_MODEL_NAME` / `MAX_CONCURRENT_LLM_CALLS`, alors qu'il sert de modèle de configuration (voir §5.3, §15.3). Le `.env.example` a été complété en octobre 2026. |
| 54 | `prompt_LLM_PROVIDER_SWITCHING_IMPLEMENTATION.md` décrit un basculement par `providers.py` + SDK `openai` **non implémenté** ; la bascule réelle vers Gemini a été faite directement via `google-genai`, sans rétrocompatibilité Mistral côté chat. |

---

## 17. Glossaire

| Terme | Signification |
|-------|---------------|
| **CECRL** | *Cadre Européen Commun de Référence pour les Langues* — échelle A1→C2 |
| **NCLC** | *Niveaux de Compétence Linguistique en Français* — échelle 1→12 (échelle officielle TCF Canada) |
| **RAG** | *Retrieval-Augmented Generation* — enrichissement du prompt par documents récupérés d'une base vectorielle |
| **Few-shot** | Ajout d'exemples dans le prompt pour guider le format et le comportement du LLM |
| **TCF** | *Test de Connaissance du Français* — examen de France Éducation International |
| **FEI** | France Éducation International (organisme éditeur du TCF) |
| **Mistral-embed** | Modèle d'embeddings Mistral (1024 dimensions) — toujours utilisé pour le RAG après la bascule LLM |
| **Gemini** | Modèle LLM de Google (`gemini-3.8-flash` par défaut), appelé via le SDK `google-genai` |
| **Cosine** | Mesure de similarité entre vecteurs (comparaison d'angles, insensible à la norme) |
| **`response_schema`** | Paramètre Gemini forçant la sortie JSON **et** sa conformité à un JSON Schema (utilisé pour l'oral) |
| **Payload index** | Index Qdrant sur un champ du payload, permettant un filtrage efficace des recherches vectorielles |
| **Namespace package** | Paquet Python sans `__init__.py` (PEP 420) |
| **Banker's rounding** | Arrondi « demi-pair » de `round()` en Python : `round(2.5) == 2` |

---

## Annexe A — Référence rapide de l'API

```bash
BASE=http://localhost:8000
KEY=$TCF_API_KEY

# Health check
curl $BASE/

# Documentation
open http://localhost:8000/docs

# Évaluation complète
curl -X POST $BASE/api/v1/tcf/evaluation-complete \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -d @tests/test.json

# Extraction du bilan
curl -s -X POST $BASE/api/v1/tcf/evaluation-complete \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -d @tests/test.json \
  | python -c "import sys,json; d=json.load(sys.stdin)['bilan_global']; print(d['score'], d['niveau'])"

# Fiches de correction Expression Orale (batch)
curl -X POST $BASE/api/v1/oral/generate-corrections \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -d '{
    "topics": [
      {"id": "s1", "task_type": "TASK_2", "content": "Appelez le centre de cours pour connaître les horaires."},
      {"id": "s2", "task_type": "TASK_3", "task3_type": "DIALECTICAL", "content": "Les photos sur le CV, pour ou contre ?"}
    ]
  }'

# Régénération d'une seule fiche
curl -X POST $BASE/api/v1/oral/regenerate-correction \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -d '{"id": "s2", "task_type": "TASK_3", "task3_type": "ANALYTICAL", "content": "Expliquez les causes du vieillissement de la population."}'
```

## Annexe B — Reconstruire les collections Qdrant

```bash
# 1. Générer le corpus brut     (~612 appels Mistral, ~20 min)
python data_pipeline/generation/generate_candidates.py

# 2. Noter les copies          (~787 appels Mistral, ~30 min)
python data_pipeline/generation/evaluate_copies.py

# 3. Contrôler la qualité
python data_pipeline/generation/validate_dataset.py

# 4. Injecter les copies évaluées dans tcf_copies_dataset
python data_pipeline/generation/ingest_to_qdrant.py

# 5. Chunker et injecter les PDF (écrit + oral) dans tcf_methodologie
python data_pipeline/generation/ingest_methodology.py
```

## Annexe C — Checklist avant mise en production

1. Corriger la fixture de test (`meta`, `pourcentage`, `mention`, `resume`).
2. Ajouter `google-genai==2.31.0` à `requirements.txt` (+ `GEMINI_API_KEY` dans `render.yaml` — `.env.example` est déjà à jour).
3. Supprimer ou réparer `api_app/routes/auth.py` et retirer `tokenUrl` de `oauth2_scheme`.
4. Ajouter `CORSMiddleware` avec une liste d'origines explicite.
5. Rendre `RAGService` / `LLMService` singletons.
6. Réintroduire le parallélisme sur l'écrit (`gather(return_exceptions=True)`) et normaliser le score sur le nombre de tâches réellement soumises.
7. Valider et borner les notes renvoyées par le LLM avant calcul.
8. Ne plus exposer `str(e)` au client (écrit + oral).
9. Corriger le code d'erreur de `regenerate-correction` (400 rattrapé → 500) et valider `task3_type` côté schéma (422).
10. Filtrer le RAG oral (par épreuve / `source_document`) pour éviter les règles d'écrit.
11. Définir `TCF_API_KEY` et vérifier l'absence de repli.
12. Décider du sort de `generate_dataset.py` et `generate_candidates111.py` (réparer ou supprimer).
13. Ajouter `pytest`, `pytest-asyncio`, `pypdf`, `groq` aux dépendances de développement.
14. Vérifier les droits de redistribution des **deux** PDF de méthodologie (écrit + oral TAMARO).
15. Mettre à jour ou archiver `prompt_LLM_PROVIDER_SWITCHING_IMPLEMENTATION.md` (spécification désynchronisée du code réel).
