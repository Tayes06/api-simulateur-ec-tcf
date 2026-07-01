# Fonctionnement détaillé de l'API Simulateur TCF Canada

## Flux d'exécution d'une évaluation

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
    ┌────┴────┐────┐
    │         │    │
    ▼         ▼    ▼
┌────────┐┌────────┐┌────────┐
│ Tâche 1││ Tâche 2││ Tâche 3│  ← Lancées en parallèle
│  /4    ││  /7    ││  /9    │     avec asyncio.gather()
└───┬────┘└───┬────┘└───┬────┘
    │         │         │
    ▼         ▼         ▼
┌──────────────────────────┐
│  RAGService              │  ← recuperer_contexte()
│  api_app/services/       │     Embedding + requête Qdrant
│  rag_service.py          │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Qdrant Cloud            │
│  ┌────────────────────┐  │
│  │ tcf_methodologie   │  │  ← Top 3 règles méthodologiques
│  │ (règles barème)    │  │
│  ├────────────────────┤  │
│  │ tcf_copies_dataset │  │  ← Top 2 copies similaires (même tâche)
│  │ (copies évaluées)  │  │
│  └────────────────────┘  │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Mistral AI (LLM)        │  ← Appel à mistral-large-latest
│  ┌──────────────────────┐│     avec prompt système + RAG
│  │ prompt système       ││
│  │ + instructions tâche ││
│  │ + règles méthodo     ││
│  │ + exemples RAG       ││
│  │ + copie candidat     ││
│  └──────────┬───────────┘│
└─────────────┼────────────┘
              │
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

### Authentification par clé API

Le fichier `security.py` implémente deux mécanismes :

**Clé API (endpoint d'évaluation) :**
- Header attendu : `X-API-Key`
- Clé configurée dans `.env` via `TCF_API_KEY`
- Validation dans `verifier_cle_api()` :
  1. FastAPI extrait le header `X-API-Key` automatiquement via `APIKeyHeader`
  2. Comparaison avec la valeur de `TCF_API_KEY` stockée dans l'environnement
  3. Si absente ou invalide → HTTP 403 avec message "Accès refusé : Clé d'API invalide ou manquante"
  4. Si valide → retourne `"application_react"` (identifiant du client autorisé)

**JWT (login) :**
- Endpoint `POST /api/v1/auth/token` pour obtenir un token JWT
- Utilisateur unique simulé : `admin_tcf` / `tcf_password_2026` (hash SHA-256)
- Le token JWT n'est pas utilisé par l'endpoint d'évaluation (qui utilise la clé API), mais peut servir pour d'autres usages frontend

---

## 2. Route d'évaluation (api_app/routes/evaluation.py)

### Endpoint : `POST /api/v1/tcf/evaluation-complete`

**Schémas Pydantic :**

```python
class TachePayload(BaseModel):
    consigne_sujet: str           # La consigne de l'exercice
    texte_candidat: str           # La production écrite du candidat
    documents_contexte: list[str] # Uniquement pour la Tâche 3 (synthèse)

class TCFExamenRequest(BaseModel):
    tache_1: TachePayload | None
    tache_2: TachePayload | None
    tache_3: TachePayload | None
```

**Injection de dépendances :**
- `get_rag_service()` → instancie `RAGService` (connexion Qdrant)
- `get_llm_service()` → instancie `LLMService` (connexion Mistral)
- `verifier_cle_api` → valide la clé API

**Gestion d'erreurs :**
- Toute exception levée par `evaluer_session_complete()` est catchée et renvoyée en HTTP 500 avec le message d'erreur

---

## 3. LLMService (api_app/services/llm_service.py)

### 3.1 Initialisation

```python
class LLMService:
    def __init__(self):
        self.client = Mistral(api_key=os.environ.get("MISTRAL_API_KEY"))
        self.modele = "mistral-large-latest"
```

Utilise le SDK officiel `mistralai` avec la clé API lue depuis l'environnement.

### 3.2 Orchestrateur : `evaluer_session_complete()`

C'est le point d'entrée principal. Déroulement :

1. **Lancement parallèle** des 3 tâches via `asyncio.gather()` :
   - Tâche 1 : `_analyser_une_tache(1, 4, payload.tache_1, rag)`
   - Tâche 2 : `_analyser_une_tache(2, 7, payload.tache_2, rag)`
   - Tâche 3 : `_analyser_une_tache(3, 9, payload.tache_3, rag)`

2. **Post-traitement par tâche** :
   - Si la tâche a retourné un résultat (non-null) : recalcule le niveau CECRL/NCLC via `_calculer_niveaux_par_tache()` avec la note réelle, puis ajoute au score total
   - Si la tâche est nulle (non soumise ou vide) : génère un bloc vide via `_generer_tache_vide()` avec score 0

3. **Calcul du bilan global** :
   - Total sur 20 = somme des notes obtenues
   - Pourcentage = `(note_sur_20 / 20) × 100`
   - Niveau global = `_determiner_niveaux_tcf(note_sur_20)` → (CECRL, NCLC, mention)

### 3.3 Analyse d'une tâche : `_analyser_une_tache()`

Pour chaque tâche non vide :

1. **Récupération du contexte RAG** via `rag_service.recuperer_contexte(texte, num_tache)`
   - Extrait les règles méthodologiques (Top 3)
   - Extrait les exemples de copies similaires (Top 2, filtrés par tache_id)

2. **Génération du prompt système** via `_generer_prompt_systeme()` :
   - Instructions spécifiques à la tâche (format, longueur, critères)
   - Règles méthodologiques issues de Qdrant
   - Exemples de copies de référence
   - Structure JSON attendue

3. **Appel à Mistral** :
   - Exécuté dans un thread séparé via `loop.run_in_executor()` pour ne pas bloquer la boucle asynchrone
   - Format de réponse forcé en `json_object`
   - Parsing du JSON de réponse

4. **Post-traitement** :
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

---

## 4. RAGService (api_app/services/rag_service.py)

### 4.1 Initialisation

```python
class RAGService:
    def __init__(self):
        self.qdrant_client = QdrantClient(url=..., api_key=..., check_compatibility=False)
        self.mistral_client = Mistral(api_key=...)
        self.coll_copies = "tcf_copies_dataset"
        self.coll_methode = "tcf_methodologie"
```

- Connexion à Qdrant Cloud (base vectorielle)
- Connexion à Mistral AI (pour les embeddings)
- Création automatique d'un index sur `tache_id` dans la collection `tcf_copies_dataset` pour le filtrage

### 4.2 Génération d'embedding : `_generer_embedding()`

Utilise le modèle `mistral-embed` pour transformer un texte en vecteur :

```python
response = self.mistral_client.embeddings.create(
    model="mistral-embed",
    inputs=[texte]
)
return response.data[0].embedding
```

Retourne `None` silencieusement en cas d'erreur.

### 4.3 Récupération de contexte : `recuperer_contexte()`

Pour une copie candidate donnée, récupère en parallèle deux types de contexte :

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
        {"texte_candidat": "...", "evaluation_expert": "..."},
        {"texte_candidat": "...", "evaluation_expert": "..."}
    ]
}
```

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

**`tcf_methodologie`** : contient les règles issues du PDF `METHODOLOGIE_TCF_CANADA_TAYES.pdf` :
- Règles de barème (grille de notation)
- Consignes méthodologiques par tâche
- Critères d'évaluation détaillés

**`tcf_copies_dataset`** : contient les copies évaluées avec :
- `texte_candidat` : production écrite
- `evaluation_expert` : évaluation détaillée (note, analyse, niveau)
- `tache_id` : identifiant de la tâche (1, 2 ou 3) - indexé pour filtrage

---

## 6. Structure complète des réponses

### Réponse succès (200)

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
      "controle_methodologie": { ... },
      "analyse": { ... },
      "statistiques": { ... },
      "erreurs": [ ... ],
      "versions": { ... },
      "coaching": { ... }
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
  "detail": "Erreur lors de l'appel à Mistral AI: ..."
}
```

---

## 7. Gestion des cas particuliers

### Tâche non soumise (`null`)
- La tâche n'est pas envoyée à Mistral
- Score forcé à 0.0
- Niveau A1 / "3 ou moins"
- Pas d'analyse ni d'erreurs

### Tâche avec texte vide
- Traitée comme non soumise (même comportement que `null`)

### Erreur Mistral (timeout, API down)
- L'exception remonte jusqu'à la route
- Renvoyée en HTTP 500 avec le message d'erreur

### Erreur Qdrant (connexion, embedding)
- `recuperer_contexte()` retourne `{"regles": [], "exemples": []}`
- Le LLM évalue sans contexte RAG (fallback silencieux)

---

## 8. Performances

- Les 3 tâches sont évaluées **en parallèle** via `asyncio.gather()`
- Chaque appel Mistral est exécuté dans un thread séparé (`run_in_executor`) pour ne pas bloquer
- Temps de réponse typique : 10-30 secondes (dépend de Mistral API)
- Le RAG ajoute ~500ms par tâche (embedding + 2 requêtes Qdrant)
