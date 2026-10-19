# Spécification — Fournisseurs LLM interchangeables & suppression de `mistralai`

> **Statut :** spécification validée, **non implémentée**.
> **But :** document autoportant pour une implémentation future, sans nouvelle phase de découverte.
> **Branche de référence :** `main` @ `b345ed8`
> **Date de rédaction :** 2026-10-10
>
> **Mise à jour (2026-10-18) :** le basculement LLM a été fait **en dehors de cette
> spécification**, directement dans `api_app/services/llm_service.py` via le SDK
> officiel **`google-genai`** (modèle `gemini-3.8-flash`, surchargeable par
> `LLM_MODEL_NAME`). Il n'y a **pas** de `providers.py`, pas de SDK `openai`, pas de
> `LLM_PROVIDER`, et **plus de rétrocompatibilité Mistral côté chat** : `mistralai`
> ne subsiste que pour les embeddings (`mistral-embed`, RAG Qdrant). Le §3.2
> (« Analyse de l'existant ») de ce document décrit donc l'état **avant** cette
> bascule et est désynchronisé du code réel.

---

## 1. Objectif

Permettre de changer de fournisseur LLM et d'embeddings **en modifiant uniquement
une variable d'environnement**, sans toucher au code, et **sans que le projet ne
dépende plus du SDK `mistralai`**.

Contrainte structurante : le projet doit continuer de fonctionner à l'identique
tant que les variables actuelles (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME`,
`MISTRAL_API_KEY`) sont définies. **Aucune régression n'est acceptable sur
l'endpoint `/api/v1/tcf/evaluation-complete`.**

### Ce que « changer de SDK par variable » signifie réellement

Le SDK lui-même **ne peut pas** être piloté par le `.env` : Python doit importer le
paquet au chargement du module, et un paquet non installé ne s'importe pas quel
que soit l'environnement. Un `LLM_SDK=openai|mistralai` obligerait à garder
`mistralai` installé — contraire à l'objectif.

Ce qui est pilotable, c'est le **fournisseur**. Comme Mistral, Groq, OpenAI,
Gemini, Ollama et vLLM exposent tous une API HTTP compatible OpenAI, **un seul
SDK (`openai`) les couvre tous**.

---

## 2. Décisions actées

| # | Décision | Justification |
|---|----------|---------------|
| D1 | SDK unique = `openai` | Tous les fournisseurs ciblés parlent le protocole OpenAI |
| D2 | `LLM_PROVIDER` = **`mistral`** par défaut | Force historique en français, free tier inclut les modèles de pointe |
| D3 | `gemini` disponible **en preset**, non par défaut | Gratuit pour l'interactif, mais Flash uniquement + 250 req/jour (voir §12) |
| D4 | `EMBEDDING_PROVIDER` = **`mistral`**, collections Qdrant **intactes** | Éviter la ré-ingestion et tout changement de dimension |
| D5 | Bascule **au démarrage** (redémarrage requis) | Cohérent avec le déploiement Docker/Render, pas de relecture à chaud |
| D6 | `data_pipeline` migré aussi | Objectif « plus aucune dépendance à mistralai » |

---

## 3. État actuel du code (inventaire de référence)

### 3.1 Dépendance à `mistralai` — 6 fichiers, 11 sites

| Fichier | Lignes | Usage |
|---------|--------|-------|
| `api_app/services/rag_service.py` | 4 (`from mistralai.client import Mistral`), 11 (`self.mistral_api_key`), 15 (`self.mistral_client = Mistral(...)`), 32-35 (`embeddings.create(model="mistral-embed", inputs=[...])`) | Embeddings |
| `data_pipeline/generation/evaluate_copies.py` | 5, 17, 79 (`client.chat.complete(`) | Génération |
| `data_pipeline/generation/generate_candidates.py` | 5, 18, 349 (`client.chat.complete(`) | Génération |
| `data_pipeline/generation/generate_candidates111.py` | 6, 20, 349 (`client.chat.completions.create(`) | Génération |
| `data_pipeline/generation/ingest_methodology.py` | 8, 22, 64-66 (`embeddings.create(inputs=[...])`) | Embeddings |
| `data_pipeline/generation/ingest_to_qdrant.py` | 9, 25, 64-66 (`embeddings.create(inputs=[...])`) | Embeddings |

### 3.2 LLM déjà quasi configurables

`api_app/services/llm_service.py` :

```python
27: MAX_CONCURRENT_CALLS = int(os.environ.get("MAX_CONCURRENT_LLM_CALLS", "1"))
36: class LLMService:
37:     def __init__(self):
39:         base_url = os.environ.get("LLM_BASE_URL")   # ex: http://localhost:11434/v1
40:         api_key  = os.environ.get("LLM_API_KEY", "ollama")
43:         self.client = OpenAI(base_url=base_url if base_url else None, api_key=api_key)
47:         self.modele = os.environ.get("LLM_MODEL_NAME", "mistral")
```

Appel LLM unique : `_appeler_llm_json()` lignes 392-415, avec
`response_format={"type": "json_object"}` ligne 404.

**Défaut latent cassé :** si `LLM_BASE_URL` est absent, `base_url=None` fait
pointer le SDK vers `api.openai.com` avec la clé littérale `"ollama"`. Le défaut
n'est fonctionnel que parce que le `.env` réel définit `LLM_BASE_URL`.

### 3.3 Embeddings codés en dur

`api_app/services/rag_service.py` : modèle `"mistral-embed"` et paramètre
`inputs=` passés en dur. Appelé depuis `:42` (`recuperer_contexte`) et `:95`
(`recuperer_contexte_oral`).

### 3.4 Extraction de réponse — identique dans les deux SDKs

| `mistralai` | `openai` |
|-------------|----------|
| `client.chat.complete(...)` | `client.chat.completions.create(...)` |
| `response.choices[0].message.content` | **identique** |
| `embeddings.create(inputs=[...])` | `embeddings.create(input=[...])` |
| `response.data[].embedding` | **identique** |

**Seules 2 formes d'appel changent** dans toute la base (`.chat.complete(` et
`inputs=`). Les lignes d'extraction (`evaluate_copies.py:88`,
`generate_candidates.py:357`, `ingest_to_qdrant.py:68`) ne bougent pas.

### 3.5 Inventaire des variables d'environnement réellement lues

| Variable | Lue par | Dans `.env.example` ? |
|----------|---------|:---------------------:|
| `LLM_BASE_URL` | `llm_service.py:39` | non |
| `LLM_API_KEY` | `llm_service.py:40` | non |
| `LLM_MODEL_NAME` | `llm_service.py:47` | non |
| `MAX_CONCURRENT_LLM_CALLS` | `llm_service.py:27` | non |
| `MISTRAL_API_KEY` | `rag_service.py:11` + 5 scripts pipeline | oui |
| `QDRANT_URL` / `QDRANT_API_KEY` | `rag_service.py:9-10` | oui |
| `TCF_API_KEY` | `core/security.py` | oui |
| `GROQ_API_KEY` | `generate_dataset.py`, `generate_candidates111.py` | oui |

### 3.6 Dépendances

`requirements.txt` (9 lignes) :

```text
fastapi==0.137.1
uvicorn==0.49.0
pydantic==2.13.4
mistralai==2.5.0      # ← à retirer
qdrant-client==1.18.0
python-dotenv==1.2.2
python-jose==3.5.0
passlib==1.7.4
httpx==0.28.1
```

- `openai==3.24.0` est **installé** mais **absent** de `requirements.txt`
  (`pip show openai` → `Required-by:` vide). Le déploiement depuis le fichier
  échouerait sur `llm_service.py:6`.
- `groq` et `pypdf` sont importés par `data_pipeline` mais absents du fichier
  (constat préexistant, hors périmètre — voir §11).

### 3.7 Contraintes de dimension

- `mistral-embed` → **1024** dimensions.
- Collections Qdrant actuelles : `tcf_copies_dataset`, `tcf_methodologie`.
- `ingest_to_qdrant.py:29` code en dur `DIMENSION_EMBEDDING = 1024`.

Tout changement de modèle d'embedding impose une **ré-ingestion complète** et un
changement de dimension. C'est la raison de la décision **D4**.

---

## 4. Étape bloquante à exécuter AVANT toute modification

Le SDK `openai` 3.24.0 envoie le paramètre `input`. `mistralai` envoie `inputs`.
Google confirme `input` pour Gemini (doc officielle). **Mistral n'a pas été
vérifié.**

```python
# Script éphémère, hors dépôt, avec la vraie clé
from openai import OpenAI
c = OpenAI(api_key=MISTRAL_API_KEY, base_url="https://api.mistral.ai/v1")
r = c.embeddings.create(model="mistral-embed", input=["test en français"])
assert len(r.data[0].embedding) == 1024
```

- **Succès** → poursuivre le plan tel quel.
- **Échec (400)** → isoler le repli dans `providers.py` uniquement :
  `extra_body={"inputs": [...]}` au lieu de `input=`.

Cette vérification conditionne l'ensemble de l'étape 6.2 et 6.3.

---

## 5. Architecture cible

### 5.1 Nouveau module `api_app/core/providers.py`

Contrainte : **aucun import `api_app`** dans ce module (seulement `os`,
`dataclasses`, `typing`), afin que `data_pipeline` puisse l'importer sans
dépendance circulaire.

```python
from dataclasses import dataclass
from typing import Optional
import os

@dataclass(frozen=True)
class Configuration:
    base_url: Optional[str]
    modele: str
    cle: Optional[str]
    dimension: Optional[int] = None   # embeddings uniquement

# --- Presets ---
PRESETS_LLM = {
    "mistral": Configuration("https://api.mistral.ai/v1", "mistral-large-latest", "MISTRAL_API_KEY"),
    "gemini":  Configuration("https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-3.8-flash", "GEMINI_API_KEY"),
    "openai":  Configuration("https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY"),
    "groq":    Configuration("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "GROQ_API_KEY"),
    "ollama":  Configuration("http://localhost:11434/v1", None, None),
    "vllm":    Configuration("http://localhost:8000/v1", None, None),
    "lmstudio":Configuration("http://localhost:1234/v1", None, None),
}

PRESETS_EMBEDDING = {
    "mistral": Configuration("https://api.mistral.ai/v1", "mistral-embed", "MISTRAL_API_KEY", 1024),
    "gemini":  Configuration("https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-embedding-001", "GEMINI_API_KEY", 3072),
    "openai":  Configuration("https://api.openai.com/v1", "text-embedding-3-small", "OPENAI_API_KEY", 1536),
    "ollama":  Configuration("http://localhost:11434/v1", "nomic-embed-text", None, None),
}
```

API publique :

```python
def resoudre_llm() -> Configuration          # merge preset + overrides env
def resoudre_embedding() -> Configuration
def client_llm() -> tuple[OpenAI, str]       # (client configuré, nom du modèle)
def client_embedding() -> tuple[OpenAI, str]
def valider_configuration() -> list[str]     # erreurs fatales au démarrage
```

> Note : `client_llm()` / `client_embedding()` importent `openai` localement.
> `valider_configuration()` et `resoudre_*()` restent importables sans le SDK.

### 5.2 Presets LLM

| `LLM_PROVIDER` | `base_url` | modèle par défaut | clé attendue |
|----------------|-----------|-------------------|--------------|
| `mistral` ⭐ | `https://api.mistral.ai/v1` | `mistral-large-latest` | `MISTRAL_API_KEY` |
| `gemini` | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-3.8-flash` | `GEMINI_API_KEY` |
| `openai` | `https://api.openai.com/v1` | `gpt-4o-mini` | `OPENAI_API_KEY` |
| `groq` | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` | `GROQ_API_KEY` |
| `ollama` | `http://localhost:11434/v1` | `LLM_MODEL_NAME` | aucune |
| `vllm` | `http://localhost:8000/v1` | `LLM_MODEL_NAME` | aucune |
| `lmstudio` | `http://localhost:1234/v1` | `LLM_MODEL_NAME` | aucune |
| `custom` | `LLM_BASE_URL` | `LLM_MODEL_NAME` | `LLM_API_KEY` |

### 5.3 Presets embeddings

| `EMBEDDING_PROVIDER` | `base_url` | modèle | dimension |
|----------------------|-----------|--------|-----------|
| `mistral` ⭐ | `https://api.mistral.ai/v1` | `mistral-embed` | **1024** |
| `gemini` | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-embedding-001` | 3072 ⚠ |
| `openai` | `https://api.openai.com/v1` | `text-embedding-3-small` | 1536 |
| `ollama` | `http://localhost:11434/v1` | `nomic-embed-text` | variable |
| `custom` | `EMBEDDING_BASE_URL` | `EMBEDDING_MODEL_NAME` | `EMBEDDING_DIMENSION` |

### 5.4 Règles de résolution

```python
provider = os.environ.get("LLM_PROVIDER")          # peut être None
preset   = PRESETS_LLM.get(provider, PRESET_VIDE)  # None -> preset vide

base_url = os.environ.get("LLM_BASE_URL")   or preset.base_url or None
modele   = os.environ.get("LLM_MODEL_NAME") or preset.modele   or "mistral"
cle      = os.environ.get("LLM_API_KEY")    or preset.cle      or "ollama"
```

Embeddings, même logique, avec un repli supplémentaire sur la clé Mistral :

```python
cle = (os.environ.get("EMBEDDING_API_KEY")
       or preset.cle_env and os.environ.get(preset.cle_env)
       or os.environ.get("MISTRAL_API_KEY")
       or os.environ.get("LLM_API_KEY"))
```

**Garanties de rétro-compatibilité :**

1. `LLM_PROVIDER` absent → `preset` vide → expressions **identiques** au code
   actuel (lignes 39-47). Le `.env` existant garde exactement le même sens.
2. `EMBEDDING_PROVIDER` absent → `preset` vide → repli sur `MISTRAL_API_KEY` et
   modèle `mistral-embed` (1024), comme aujourd'hui.

**Corollaire :** `LLM_PROVIDER=mistral` **répare** le défaut latent §3.2, puisque
`base_url` devient `https://api.mistral.ai/v1` même sans `LLM_BASE_URL`.

### 5.5 Variables d'environnement cibles

```dotenv
# --- LLM (protocole compatible OpenAI) ---
LLM_PROVIDER=mistral              # mistral | gemini | openai | groq | ollama | vllm | lmstudio | custom
LLM_BASE_URL=                     # override optionnel
LLM_API_KEY=                      # override optionnel
LLM_MODEL_NAME=                   # override optionnel
MAX_CONCURRENT_LLM_CALLS=1

# --- Embeddings (indépendants du LLM) ---
EMBEDDING_PROVIDER=mistral
EMBEDDING_BASE_URL=               # override optionnel
EMBEDDING_API_KEY=                # override optionnel
EMBEDDING_MODEL_NAME=             # override optionnel
EMBEDDING_DIMENSION=1024          # requis pour custom uniquement

# --- Clés fournisseurs ---
MISTRAL_API_KEY=votre_cle_mistral
GEMINI_API_KEY=                   # requise si LLM_PROVIDER=gemini ou EMBEDDING_PROVIDER=gemini
OPENAI_API_KEY=
GROQ_API_KEY=

# --- Existant ---
QDRANT_URL=votre_url_qdrant
QDRANT_API_KEY=votre_cle_qdrant
TCF_API_KEY=votre_cle_api_tcf
```

---

## 6. Modifications fichier par fichier

### 6.1 `api_app/core/providers.py` — nouveau

Voir §5.1. Environ 120 lignes. Une fois l'étape 4 concluante, encapsuler
l'appel embeddings réel dans une petite fonction
`embedding_input(texte) -> dict` pour centraliser le cas `input=` / `inputs=`.

### 6.2 `api_app/services/llm_service.py`

Remplacer **uniquement** le corps de `__init__` (lignes 37-48) :

```python
-    def __init__(self):
-        base_url = os.environ.get("LLM_BASE_URL")
-        api_key = os.environ.get("LLM_API_KEY", "ollama")
-        self.client = OpenAI(base_url=base_url if base_url else None, api_key=api_key)
-        self.modele = os.environ.get("LLM_MODEL_NAME", "mistral")
-        self.model_name = self.modele
+    def __init__(self):
+        from api_app.core.providers import client_llm
+        self.client, self.modele = client_llm()
+        self.model_name = self.modele
```

- `import os` reste nécessaire (ligne 27) → **ne pas le retirer**.
- `_appeler_llm_json` (392-415) et `response_format` (404) : **inchangés**.
- Attention : `response_format={"type": "json_object"}` n'est pas supporté par
  tous les endpoints compatibles. Prévoir un repli (voir §10, risque R3).

### 6.3 `api_app/services/rag_service.py`

```python
-4: from mistralai.client import Mistral
+4: from api_app.core.providers import client_embedding

 7: class RAGService:
 8:     def __init__(self):
-11:        self.mistral_api_key = os.environ.get("MISTRAL_API_KEY")
-15:        self.mistral_client = Mistral(api_key=self.mistral_api_key)
+15:        self.client_embedding, self.modele_embedding = client_embedding()

30:    def _generer_embedding(self, texte: str):
-32:        response = self.mistral_client.embeddings.create(
-33:            model="mistral-embed",
-34:            inputs=[texte]
-35:        )
+           response = self.client_embedding.embeddings.create(
+               model=self.modele_embedding,
+               input=[texte]           # ou extra_body selon étape 4
+           )
```

Les appels `:42` et `:95` restent inchangés. La sortie
`response.data[0].embedding` est identique.

### 6.4 `data_pipeline/generation/` — 5 fichiers

Pour chaque script, après le bloc `load_dotenv` existant (ex.
`ingest_to_qdrant.py:15`), ajouter :

```python
import sys
sys.path.insert(0, str(chemin_racine))
from api_app.core.providers import client_llm, client_embedding
```

Puis :

| Fichier | Remplacement |
|---------|--------------|
| `evaluate_copies.py` | `client = Mistral(...)` → `client, model = client_llm()` ; `client.chat.complete(` → `client.chat.completions.create(` (+ `model=model`) |
| `generate_candidates.py` | idem |
| `generate_candidates111.py` | idem (l'import `groq` ligne 5 est préexistant, laisser) |
| `ingest_methodology.py` | `mistral_client` → `client_embedding()` ; `embeddings.create(input=...)` |
| `ingest_to_qdrant.py` | idem, **et** remplacer `DIMENSION_EMBEDDING = 1024` (ligne 29) par la dimension lue depuis `providers.py` |

> L'ajout `sys.path` est indispensable : lancé via
> `python data_pipeline/generation/ingest_to_qdrant.py`, `sys.path[0]` est le
> dossier du script, pas la racine. Aucun script ne le fait aujourd'hui.

### 6.5 `api_app/main.py`

Ajouter une validation au démarrage (sans bloquer l'import des tests) :

```python
from api_app.core.providers import valider_configuration

@app.on_event("startup")
def _verifier_configuration():
    erreurs = valider_configuration()
    if erreurs:
        raise RuntimeError("Configuration LLM invalide : " + " | ".join(erreurs))
```

> `valider_configuration()` ne doit **jamais** lever au premier accès Qdrant :
> le contrôle de dimension est *best-effort* (ignoré si Qdrant est injoignable).

### 6.6 `requirements.txt` et `.env.example`

```diff
 mistralai==2.5.0        # SUPPRIMÉ
+openai==3.24.0          # AJOUTÉ (déjà installé)
```

`.env.example` : ajouter le bloc §5.5.

### 6.7 Documentation

| Fichier | Sections |
|---------|----------|
| `README.md` | tableau techno (l.19-25), prérequis (l.54-55), variables (l.77-85), **nouvelle section « Changer de fournisseur »** avant l.87, déploiement (l.384-388) |
| `FONCTIONNEMENT.md` | §3.1 (l.137-146, **actuellement faux**), §4.1 (l.245-258), §4.2 (l.260-272), l.127, §7 (l.443-447) |
| `DOCUMENTATION.md` | §3.4 (l.159-165), §5.3 (l.248-268), **nouveau §5.4**, §9.2 (l.703-726), §9.3 (l.777-782), constat #35 (l.1463), Annexe C (l.1539+) |

**À corriger en priorité, déjà faux aujourd'hui :**
`FONCTIONNEMENT.md:142-146` et `DOCUMENTATION.md:781-782` décrivent encore
`Mistral(...)` + `"mistral-large-latest"` alors que le code utilise déjà `OpenAI`
+ `LLM_MODEL_NAME`.

---

## 7. Validation au démarrage

`valider_configuration()` produit une liste d'erreurs **bloquantes** :

1. `LLM_PROVIDER` renseigné mais inconnu → lister les presets valides.
2. `EMBEDDING_PROVIDER` renseigné mais inconnu → idem.
3. Preset exigeant une clé absente → nommer la variable (`GEMINI_API_KEY`, …).
4. `*_PROVIDER=custom` sans `*_BASE_URL` ni `*_MODEL_NAME` → bloquant.
5. Qdrant joignable **et** dimension collection ≠ dimension modèle → bloquant
   (*best-effort*, ne pas lever si Qdrant est injoignable).

---

## 8. Tests à écrire (`tests/test_providers.py`)

1. Chaque preset résout correctement `base_url` / modèle / clé.
2. Variable explicite > preset (ex. `LLM_PROVIDER=groq` + `LLM_BASE_URL=x`).
3. `LLM_PROVIDER` absent → résultat **identique** au comportement actuel.
4. `EMBEDDING_PROVIDER` absent → `mistral-embed` + `MISTRAL_API_KEY`.
5. Provider inconnu → `valider_configuration()` retourne une erreur.
6. Clé manquante pour un preset qui l'exige → erreur nommant la variable.
7. `LLMService()` lit bien la config (`monkeypatch.setenv`).
8. `RAGService._generer_embedding()` appelle le bon modèle et le bon endpoint
   (client mocké).

---

## 9. Checklist de vérification finale

- [ ] Étape 4 (input vs inputs) concluante
- [ ] `grep -r "mistralai" . --include=*.py` → **0 résultat** (hors `venv/`)
- [ ] `pip show mistralai` → absent ; `openai` présent **et déclaré**
- [ ] `pytest tests/ -q` → **13 passed, 1 failed** (baseline préexistante inchangée)
- [ ] `LLM_PROVIDER=mistral` **sans** `LLM_BASE_URL` → appel LLM OK
- [ ] `LLM_PROVIDER=gemini` + `GEMINI_API_KEY` → appel LLM OK
- [ ] `LLM_PROVIDER=inconnu` → échec clair **au démarrage**
- [ ] `EMBEDDING_PROVIDER` absent → comportement embeddings identique à avant
- [ ] `uvicorn api_app.main:app` démarre, `/docs` accessible
- [ ] `python data_pipeline/generation/ingest_to_qdrant.py --help` (ou dry-run)
      n'échoue pas à l'import

---

## 10. Risques et points de vigilance

| # | Risque | Mitigation |
|---|--------|------------|
| R1 | Mistral refuse `input=` (SDK openai) | Étape 4 ; repli `extra_body={"inputs": …}` isolé dans `providers.py` |
| R2 | **Corruption silencieuse de la recherche vectorielle** si le modèle d'embedding change sans ré-ingestion | D4 (on ne bouge pas) + contrôle de dimension au démarrage §7.5 |
| R3 | Certains endpoints compatibles rejettent `response_format={"type":"json_object"}` (`llm_service.py:404`) | Ajouter un repli : sur 400, réessayer sans `response_format` et extraire le JSON du texte |
| R4 | Modèles « thinking » (Gemini 3.x) ajoutent latence et tokens | Exposer `reasoning_effort`/`thinking_config` via `extra_body` ou documenter |
| R5 | `sys.path` dans `data_pipeline` fragile selon le répertoire de lancement | Tester depuis la racine ; documenter la commande exacte |
| R6 | Le free tier Gemini peut servir les prompts à l'entraînement Google | Documenter ; rester sur Mistral par défaut (D2/D3) |

---

## 11. Hors périmètre

- `data_pipeline/generation/generate_dataset.py` — utilise déjà le SDK `groq`, non touché.
- `groq` et `pypdf` absents de `requirements.txt` — préexistant, à traiter séparément.
- Changement de base vectorielle (Qdrant → pgvector/Weaviate/Milvus) — non demandé.
- Basculer les embeddings sur Gemini — chantier séparé (ré-ingestion ≈ 1 400 appels, ~50 min + changement de dimension).

---

## 12. Notes de recherche (vérifiées 2026-10-10)

### Gemini — compatibilité OpenAI (confirmée)

```python
from openai import OpenAI
client = OpenAI(
    api_key="GEMINI_API_KEY",
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)
client.chat.completions.create(model="gemini-3.8-flash", messages=[...])
client.embeddings.create(input="...", model="gemini-embedding-001")
```

Source : `https://ai.google.dev/gemini-api/docs/openai`

### Comparaison des free tiers

| | Gemini | Mistral |
|---|--------|---------|
| Modèles inclus | Flash / Flash-Lite uniquement (Pro **payant depuis le 01/04/2026**) | **Tous**, y compris Mistral Large |
| Cadence | ≈ 10 RPM / **250 req/jour** (Flash) | ≈ **1 Md tokens/mois**, ~1 req/s |
| Données | free tier : *« Used to improve our products: Yes »* | — |
| Rebuild pipeline (~1 400 appels) | ≈ **6 jours** | ≈ **25 min** |

### Dimensions des embeddings

| Modèle | Dimension par défaut | Configurable |
|--------|---------------------|--------------|
| `mistral-embed` | 1024 | — |
| `gemini-embedding-001` | 3072 | 768 / 1536 / 3072 (max 2048 tokens d'entrée) |
| `text-embedding-3-small` | 1536 | oui |

---

## 13. Ordre d'exécution recommandé

1. **Étape 4** (test `input` vs `inputs`) — bloquante.
2. Créer `api_app/core/providers.py` + `tests/test_providers.py`.
3. Migrer `llm_service.py` puis `rag_service.py`.
4. Lancer `pytest tests/ -q` → vérifier la baseline.
5. Migrer les 5 scripts `data_pipeline`.
6. `requirements.txt`, `.env.example`.
7. Handler de démarrage dans `main.py`.
8. Documentation (§6.7).
9. Checklist §9.
