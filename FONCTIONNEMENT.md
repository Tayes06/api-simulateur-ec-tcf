# Fonctionnement détaillé de l'API Simulateur TCF Canada

L'API expose deux domaines métier :

- **Expression Écrite** — `POST /api/v1/tcf/evaluation-complete` : évaluation des 3 tâches (note /20, CECRL/NCLC, coaching)
- **Expression Orale** — `POST /api/v1/oral/generate-corrections` et `POST /api/v1/oral/regenerate-correction` : génération de fiches de correction pédagogique (Tâche 2 / Tâche 3)

Les deux partagent le même service LLM (**Gemini**, SDK `google-genai`), le même service RAG (**Qdrant** + embeddings **Mistral**) et la même authentification par clé API.

## Flux d'exécution d'une évaluation (Expression Écrite)

```
Requête HTTP
     │
     ▼
┌─────────────────┐
│  Sécurité       │  ← Vérification X-API-Key (api_app/core/security.py)
│  (API Key)      │
└────────┬────────┘
         │ (si valide)
         ▼
┌─────────────────┐
│  Route          │  ← POST /api/v1/tcf/evaluation-complete
│  evaluation.py  │    api_app/routes/evaluation.py
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  LLMService     │  ← evaluer_session_complete()
│  Orchestrateur  │    api_app/services/llm_service.py
└────────┬────────┘
         │
    ┌────┴────────────────┐
    │ Traitement          │  ← SÉQUENTIEL (les 3 tâches l'une après l'autre,
    │ séquentiel          │     plus d'asyncio.gather)
    ▼         ▼         ▼
┌────────┐┌────────┐┌────────┐
│ Tâche 1││ Tâche 2││ Tâche 3│
│  /4    ││  /7    ││  /9    │
└───┬────┘└───┬────┘└───┬────┘
    │         │         │
    ▼         ▼         ▼
┌──────────────────────────┐
│  RAGService              │  ← recuperer_contexte()
│  api_app/services/       │     Embedding Mistral + requête Qdrant
│  rag_service.py          │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Qdrant Cloud            │
│  ┌────────────────────┐  │
│  │ tcf_methodologie   │  │  ← Top 3 règles méthodologiques
│  │ (PDF écrit + oral) │  │
│  ├────────────────────┤  │
│  │ tcf_copies_dataset │  │  ← Top 2 copies similaires (même tâche)
│  │ (copies évaluées)  │  │
│  └────────────────────┘  │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Google Gemini (LLM)     │  ← Appel à gemini-3.8-flash
│  ┌──────────────────────┐│     (SDK google-genai, T=0.0,
│  │ prompt système       ││      sortie JSON contrainte,
│  │ + instructions tâche ││      retry 429/503 ×3)
│  │ + règles méthodo     ││
│  │ + exemples RAG       ││
│  │ + copie candidat     ││
│  └──────────┬───────────┘│
└─────────────┼────────────┘
              │  (via asyncio.to_thread)
              ▼
         Résultat JSON
         (note, analyse, erreurs...)
              │
              ▼
┌──────────────────────────┐
│  Post-traitement         │
│  - Recalcul du niveau    │  ← _calculer_niveaux_par_tache()
│    par tâche (projection)│
│  - Calcul du score total │
│  - Niveau global CECRL   │  ← _determiner_niveaux_tcf()
│  - Construction payload  │
└────────┬─────────────────┘
         │
         ▼
    Réponse HTTP 200 JSON
```

---

## 1. Sécurité (api_app/core/security.py)

### Authentification par clé API (seul mécanisme actif)

- Header attendu : `X-API-Key`
- Clé configurée dans `.env` via `TCF_API_KEY`
- Validation dans `verifier_cle_api()` :
  1. FastAPI extrait le header `X-API-Key` automatiquement via `APIKeyHeader`
  2. Comparaison avec la valeur de `TCF_API_KEY` stockée dans l'environnement
  3. Si absente ou invalide → HTTP 403 avec message "Accès refusé : Clé d'API invalide ou manquante"
  4. Si valide → retourne `"application_react"` (identifiant du client autorisé, jamais utilisé par la suite)

> ⚠️ Si `TCF_API_KEY` est absente de l'environnement, la comparaison retombe sur la valeur de repli `"cle_par_defaut_si_vide"` — l'endpoint devient alors accessible à quiconque envoie cette valeur.

### Authentification JWT — code mort

Le fichier `api_app/routes/auth.py` décrit un endpoint `POST /api/v1/auth/token` (compte simulé `admin_tcf`, hash SHA-256), mais :

- le routeur **n'est jamais monté** dans `main.py` (seuls `evaluation.router` et `oral_correction.router` le sont),
- il importe `creer_access_token` et `verifier_mot_de_passe`, **inexistants** dans `security.py` : l'import lèverait un `ImportError`.

Cet endpoint **n'existe pas** dans l'API déployée.

---

## 2. Route d'évaluation (api_app/routes/evaluation.py)

### Endpoint : `POST /api/v1/tcf/evaluation-complete`

**Schémas Pydantic :**

```python
class TachePayload(BaseModel):
    consigne_sujet: str            # La consigne de l'exercice
    texte_candidat: str            # La production écrite du candidat
    documents_contexte: list[str]  # Uniquement pour la Tâche 3 (synthèse)

class TCFExamenRequest(BaseModel):
    tache_1: TachePayload | None
    tache_2: TachePayload | None
    tache_3: TachePayload | None
```

**Injection de dépendances :**
- `get_rag_service()` → instancie `RAGService` (connexion Qdrant + client embeddings Mistral)
- `get_llm_service()` → instancie `LLMService` (connexion Gemini — requiert `GEMINI_API_KEY`)
- `verifier_cle_api` → valide la clé API

**Gestion d'erreurs :**
- Toute exception levée par `evaluer_session_complete()` est catchée et renvoyée en HTTP 500 avec le message d'erreur (y compris les erreurs de SDK tiers).

---

## 3. LLMService (api_app/services/llm_service.py)

### 3.1 Initialisation

```python
class LLMService:
    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("LLM_API_KEY")
        if not api_key:
            raise ValueError("❌ GEMINI_API_KEY est introuvable dans les variables d'environnement.")
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(api_version="v1"))
        self.modele = os.environ.get("LLM_MODEL_NAME", "gemini-3.8-flash")
```

Utilise le SDK officiel `google-genai`. Le nom du modèle est surchargeable via `LLM_MODEL_NAME`. **L'instanciation échoue sans clé Gemini** — y compris dans la suite de tests.

### 3.2 Orchestrateur : `evaluer_session_complete()`

C'est le point d'entrée principal. Déroulement :

1. **Traitement séquentiel** des 3 tâches (l'ancien `asyncio.gather()` a été supprimé) :
   - Tâche 1 : `_analyser_une_tache(1, 4, payload.tache_1, rag)`
   - Tâche 2 : `_analyser_une_tache(2, 7, payload.tache_2, rag)`
   - Tâche 3 : `_analyser_une_tache(3, 9, payload.tache_3, rag)`
   - Si `MAX_CONCURRENT_LLM_CALLS == 1`, un `asyncio.sleep(1.0)` est inséré entre chaque tâche (palier de rate-limit). Cette variable **ne parallélise rien** côté écrit.

2. **Post-traitement par tâche** :
   - Si la tâche a retourné un résultat (non-null) : recalcule le niveau CECRL/NCLC via `_calculer_niveaux_par_tache()` avec la note réelle, réécrit `consigne`, ajoute `nombre_mots_candidat` / `nombre_mots_exemple`, puis ajoute au score total
   - Si la tâche est nulle (non soumise ou vide) : génère un bloc vide via `_generer_tache_vide()` avec score 0

3. **Calcul du bilan global** :
   - Total sur 20 = somme des notes obtenues (dénominateur **toujours 20**, même pour une seule tâche soumise)
   - Pourcentage = `(note_sur_20 / 20) × 100`
   - Niveau global = `_determiner_niveaux_tcf(note_sur_20)` → (CECRL, NCLC, mention)

> Une exception sur une seule tâche (échec Gemini, JSON malformé…) interrompt toute la requête en HTTP 500, y compris les tâches déjà évaluées.

### 3.3 Analyse d'une tâche : `_analyser_une_tache()`

Pour chaque tâche non vide :

1. **Récupération du contexte RAG** via `rag_service.recuperer_contexte(texte, num_tache)`
   - Extrait les règles méthodologiques (Top 3)
   - Extrait les exemples de copies similaires (Top 2, filtrés par tache_id)

2. **Construction de la consigne** :
   - Tâches 1 et 2 : `consigne_sujet` brut
   - Tâche 3 : construction à partir de `consigne_sujet` + 2 premiers `documents_contexte` ; après appel, la `consigne` de la réponse est **réécrite** en `"TITRE : {titre}\n\n{doc1}\n\n{doc2}"` (sans libellé « Document 1/2 »)

3. **Génération du prompt système** via `_generer_prompt_systeme()` :
   - Instructions spécifiques à la tâche (format, longueur, critères)
   - Règles méthodologiques issues de Qdrant
   - Exemples de copies de référence
   - Structure JSON attendue

4. **Appel à Gemini** :
   - Exécuté dans un thread séparé via `asyncio.to_thread(_appeler_llm_json, …)` pour ne pas bloquer la boucle asynchrone
   - Config : `response_mime_type="application/json"`, `temperature=0.0`
   - Retry ×3 sur les erreurs `429` / `503` (backoff 2 s → 4 s → 8 s)
   - Parsing du JSON de réponse

5. **Post-traitement** :
   - Injection du nombre réel de mots et du texte original
   - Injection de la consigne

### 3.4 Génération du prompt système : `_generer_prompt_systeme()`

Le prompt système est structuré en 3 parties :

**Instructions spécifiques à la tâche :**

| Tâche | Type | Consignes de format | Éléments requis |
|-------|------|---------------------|-----------------|
| 1 | Récit/Description (lettre) | 60-120 mots, format lettre | Salutation, conclusion, signature |
| 2 | Article/Lettre formelle | 120-150 mots, paragraphes | Titre, introduction, arguments, conclusion |
| 3 | Synthèse argumentative | 120-180 mots, 2 parties | Titre, confrontation, avis personnel |

**Contenu dynamique ajouté :**
- Règles méthodologiques (contexte RAG)
- Exemples de copies de référence (few-shot)
- Structure JSON exacte que le LLM doit remplir

### 3.5 Grille de niveaux : `_determiner_niveaux_tcf()`

Conversion de la note sur 20 en niveau CECRL/NCLC selon la grille officielle TCF Canada :

```
Note  →  CECRL  →  NCLC
────────────────────────
18-20 →  C2     →  10+
16-17 →  C1     →  10+
14-15 →  C1     →  9
12-13 →  B2     →  8
10-11 →  B2     →  7
7-9   →  B1     →  6
6     →  B1     →  5
4-5   →  A2     →  4
0-3   →  A1     →  3
```

### 3.6 Projection par tâche : `_calculer_niveaux_par_tache()`

Chaque tâche a son propre barème (4, 7 ou 9 points). Pour déterminer le niveau de la tâche :
1. Projection sur 20 : `(note_obtenue / note_max) × 20`
2. Arrondi à l'entier le plus proche
3. Application de la même grille que ci-dessus

### 3.7 Tâche vide : `_generer_tache_vide()`

Pour une tâche non soumise, génère un bloc avec :
- Score : 0.0 / max
- Niveau : A1 / "3 ou moins"
- Contrôle méthodologique : tout False
- Analyse, statistiques : objets vides
- Erreurs : tableau vide
- Coaching : pointe "Tâche non traitée."

### 3.8 Module Expression Orale

Méthodes dédiées dans le même service :

| Méthode | Rôle |
|---------|------|
| `generer_corrections_orales_batch(topics, rag)` | Orchestrateur : sémaphore `MAX_CONCURRENT_LLM_CALLS` + `asyncio.gather` (parallèle, sans tolérance de panne partielle) |
| `_traiter_un_sujet_oral(topic, rag)` | RAG oral → prompt → Gemini (`response_schema` Pydantic) → validation stricte de la sortie |
| `_obtenir_config_prompt_oral(topic)` | Routage TASK_2 / TASK_3-DIALECTICAL / TASK_3-ANALYTICAL → (prompt, schéma) |

Les prompts sont externalisés dans `api_app/prompts/oral_prompts.py`, les schémas dans `api_app/schemas/oral.py`. Contrairement à l'écrit, la sortie du LLM est **validée par Pydantic** avant d'être renvoyée.

---

## 4. RAGService (api_app/services/rag_service.py)

### 4.1 Initialisation

```python
class RAGService:
    def __init__(self):
        self.qdrant_client = QdrantClient(url=..., api_key=..., check_compatibility=False)
        self.mistral_client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
        self.coll_copies = "tcf_copies_dataset"
        self.coll_methode = "tcf_methodologie"
```

- Connexion à Qdrant Cloud (base vectorielle)
- Connexion à Mistral AI (**embeddings uniquement**, le chat est passé à Gemini)
- Création automatique d'un index sur `tache_id` dans la collection `tcf_copies_dataset` pour le filtrage

### 4.2 Génération d'embedding : `_generer_embedding()`

Utilise le modèle `mistral-embed` pour transformer un texte en vecteur (1024 dimensions) :

```python
response = self.mistral_client.embeddings.create(
    model="mistral-embed",
    inputs=[texte]
)
return response.data[0].embedding
```

Retourne `None` silencieusement en cas d'erreur.

### 4.3 Récupération de contexte : `recuperer_contexte()` (écrit)

Pour une copie candidate donnée, récupère deux types de contexte :

**1. Règles méthodologiques (collection `tcf_methodologie`)**
- Embedding du texte candidat → recherche de similarité vectorielle
- Top 3 résultats les plus proches
- Extraction du champ `contenu_regle` de chaque hit

**2. Exemples de copies (collection `tcf_copies_dataset`)**
- Même embedding
- Filtre strict par `tache_id` (seules les copies de la même tâche sont retournées)
- Top 2 résultats les plus proches
- Extraction des champs `texte_candidat` et `evaluation_expert`

**Structure retournée :**
```python
{
    "regles": ["règle 1", "règle 2", "règle 3"],
    "exemples": [
        {"texte_candidat": "...", "evaluation_expert": {...}},
        {"texte_candidat": "...", "evaluation_expert": {...}}
    ]
}
```

### 4.4 Récupération de contexte oral : `recuperer_contexte_oral()`

Pour un sujet d'Expression Orale :

1. Construction d'une requête : `"Méthodologie TCF Canada Expression Orale {task_type}[ {task3_type}] : {content}"`
2. Embedding `mistral-embed` de cette requête
3. Recherche Top 4 dans `tcf_methodologie` — **sans filtre** (les chunks des PDF écrit et oral sont mélangés)
4. Retour de la liste des chunks (`contenu_regle`), ou `[]` si embedding ou requête échoue (fallback silencieux, y compris exceptions Qdrant)

---

## 5. Pipeline de données (data_pipeline/)

### 5.1 Génération des datasets

Les scripts dans `data_pipeline/generation/` servent à créer le contenu des collections Qdrant :

```
Mistral AI / Groq
      │
      ▼
  generate_candidates.py  ───▶  copies_candidates_brutes.jsonl
  generate_dataset.py           (copies brutes)
      │
      ▼
  evaluate_copies.py      ───▶  copies_evaluees.jsonl
                                (copies + évaluations expertes)
      │
      ▼
  ingest_to_qdrant.py     ───▶  Qdrant Cloud
  ingest_methodology.py         collections vectorisées
```

### 5.2 Validation

`validate_dataset.py` vérifie la cohérence des données :
- Structure JSON valide
- Cohérence des notes
- Distribution des niveaux NCLC
- Lignes corrompues ou aberrantes

### 5.3 Collections Qdrant

**`tcf_methodologie`** : contient les règles issues des PDF de `methodology_docs/` :
- `METHODOLOGIE_expression_ecrite_TCF_CANADA.pdf` (Expression Écrite)
- `TAMARO_Methodologie_Expression_Orale.pdf` (Expression Orale)

Les chunks des deux documents sont **mélangés** dans la même collection (payload : `source_document`, `index_chunk`, `contenu_regle`). L'ingestion (`ingest_methodology.py`) est idempotente (IDs déterministes) et traite les embeddings par lots de 10 avec retry 429.

**`tcf_copies_dataset`** : contient les copies évaluées avec :
- `texte_candidat` : production écrite
- `evaluation_expert` : évaluation détaillée (note, analyse, niveau)
- `tache_id` : identifiant de la tâche (1, 2 ou 3) - indexé pour filtrage

---

## 6. Structure complète des réponses

### Réponse succès (200) — Expression Écrite

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
      "controle_methodologie": { ... },
      "analyse": { ... },
      "statistiques": { ... },
      "erreurs": [ ... ],
      "versions": {
        "version_corrigee": "...",
        "version_modele_c2": "..."
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

### Réponse succès (200) — Expression Orale

```json
{
  "status": "success",
  "total_processed": 1,
  "corrections": [
    {
      "topic_id": "sujet-001",
      "task_type": "TASK_2",
      "task3_type": null,
      "correction": { ... }  // Task2Correction | Task3Dialectical | Task3Analytical
    }
  ]
}
```

### Réponses d'erreur

**403 - Clé API invalide :**
```json
{
  "detail": "Accès refusé : Clé d'API invalide ou manquante dans l'en-tête X-API-Key"
}
```

**422 - Validation Pydantic :**
```json
{
  "detail": [
    {
      "loc": ["body", "tache_1", "consigne_sujet"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

**500 - Erreur interne :**
```json
{
  "detail": "Erreur lors de l'appel au LLM : ..."
}
```

---

## 7. Gestion des cas particuliers

### Tâche non soumise (`null`)
- La tâche n'est pas envoyée à Gemini
- Score forcé à 0.0
- Niveau A1 / "3 ou moins"
- Pas d'analyse ni d'erreurs

### Tâche avec texte vide
- Traitée comme non soumise (même comportement que `null`)

### Erreur LLM (quota, API down, JSON malformé)
- L'exception remonte jusqu'à la route (les tâches déjà traitées sont perdues)
- Renvoyée en HTTP 500 avec le message d'erreur

### Erreur Qdrant (connexion, embedding)
- `recuperer_contexte()` retourne `{"regles": [], "exemples": []}`
- `recuperer_contexte_oral()` retourne `[]`
- Le LLM évalue sans contexte RAG (fallback silencieux, invisible côté client)

### Sujet oral `TASK_3` sans `task3_type`
- `ValueError` levé dans `_obtenir_config_prompt_oral()` → HTTP 500 (et non 422)

---

## 8. Performances

- Les 3 tâches écrites sont évaluées **séquentiellement** (régression : l'ancienne version utilisait `asyncio.gather`)
- Chaque appel Gemini est exécuté dans un thread séparé (`asyncio.to_thread`) pour ne pas bloquer
- Temps de réponse typique (écrit) : **somme de 3 appels Gemini** ≈ 9-30 secondes
- Temps de réponse typique (oral) : `ceil(n / 3)` fenêtres de concurrence (`MAX_CONCURRENT_LLM_CALLS`, défaut 3)
- Le RAG ajoute ~500ms par tâche (embedding Mistral + requêtes Qdrant), non déporté en thread
