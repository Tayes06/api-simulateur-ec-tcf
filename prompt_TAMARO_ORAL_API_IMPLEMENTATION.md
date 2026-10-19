# TAMARO — Module Expression Orale · Implémentation API
## Instructions destinées à l'agent de développement IDE

> Lis l'intégralité de ce document avant d'ouvrir un seul fichier.
> La Phase 0 (analyse) est bloquante. Ne modifie aucun fichier existant avant d'avoir présenté ton analyse et reçu une validation.

---

## Contexte critique — Ce que tu dois savoir avant de commencer

### Nature du projet existant

Le backend actuel est une **API FastAPI en Python**, stateless, sans base de données ni ORM. Son seul endpoint métier est :

```
POST /api/v1/tcf/evaluation-complete
```

Il reçoit les productions écrites d'un candidat, appelle **Mistral AI** (`mistral-large-latest`) enrichi par un contexte **RAG via Qdrant Cloud**, et renvoie un bilan JSON.

L'API est organisée ainsi (à vérifier dans le repository) :

```
api_app/
├── main.py              — point d'entrée FastAPI, montage des routers
├── models/
│   └── evaluation.py    — modèles Pydantic (TCFExamenRequest, TCFEvaluationGlobaleResponse, etc.)
├── routes/
│   ├── evaluation.py    — route POST /api/v1/tcf/evaluation-complete
│   └── auth.py          — code mort (ne pas toucher)
├── services/
│   ├── llm_service.py   — LLMService : orchestration des appels Mistral
│   └── rag_service.py   — RAGService : embeddings + recherche Qdrant
└── security.py          — verifier_cle_api() via header X-API-Key
```

### Points d'attention identifiés dans la documentation

Avant toute décision d'architecture, prends en compte les faits suivants documentés sur le projet existant :

1. **Aucune base de données, aucun ORM** : le projet actuel est purement stateless. Le module Expression Orale requiert une persistance. Tu dois donc introduire une base de données. Ce choix est structurant — présente tes options avant d'implémenter.

2. **Aucun système d'authentification fonctionnel** : `auth.py` est du code mort. La sécurité actuelle repose uniquement sur un header `X-API-Key` comparé à une variable d'environnement. Il n'existe pas de notion de rôle ADMIN fonctionnel. Tu dois concevoir un système d'authentification minimal pour protéger les endpoints d'administration du module oral, en cohérence avec l'existant ou en le complétant proprement.

3. **`LLMService` et `RAGService` sont recréés à chaque requête** : c'est un problème de performance documenté. Ne pas répliquer ce pattern pour le module oral. Concevoir les services oraux comme des singletons ou les passer comme dépendances FastAPI (`Depends()`).

4. **Le format de sortie LLM est du JSON brut** : Mistral est appelé avec `response_format: json_object` (à vérifier dans `llm_service.py`). La réponse est parsée avec `json.loads()`. Il n'y a pas de validation de schéma en aval. Le module oral doit introduire une validation de schéma de la réponse IA — voir section Validation ci-dessous.

5. **Pas de `__init__.py`** dans les paquets. Respecte ce choix ou suis la convention existante dans le repository tel que tu le trouves.

6. **Les prompts sont construits inline dans `llm_service.py`** : pour le module oral, les prompts doivent être dans des fichiers séparés. Ne pas les inliner dans le service.

---

## Phase 0 — Analyse obligatoire (bloquante)

**N'écris pas de code avant d'avoir terminé cette phase.**

### 0.1 — Inspecte les fichiers suivants et documente ce que tu trouves

Pour chaque fichier, indique son contenu réel (pas ce que tu supposes) :

- `api_app/main.py` : comment les routers sont montés, quels middlewares sont déclarés, si Swagger est activé et protégé ou non.
- `api_app/routes/evaluation.py` : structure exacte de la route, comment `LLMService` et `RAGService` sont instanciés, comment `verifier_cle_api` est appliqué.
- `api_app/services/llm_service.py` : comment le client Mistral est initialisé, comment le prompt est construit, comment la réponse est parsée, comment les erreurs sont gérées.
- `api_app/services/rag_service.py` : comment le client Qdrant est initialisé, quelles collections sont utilisées, comment la recherche est effectuée.
- `api_app/security.py` : mécanisme exact de vérification de la clé API.
- `api_app/models/evaluation.py` : tous les modèles Pydantic définis, leurs champs, leurs validateurs.
- `requirements.txt` : dépendances déclarées et leurs versions.
- `.env.example` ou tout fichier de configuration : variables d'environnement attendues.
- `tests/` : framework de test utilisé, fixtures disponibles, couverture actuelle.

### 0.2 — Décisions à présenter avant d'implémenter

Sur la base de ton analyse, présente tes choix pour les points suivants et attends une validation :

**A — Persistance**

Le module oral nécessite une base de données (sujets, corrections, combinaisons). Présente les options envisageables compte tenu du stack Python/FastAPI existant. Options typiques :

- SQLAlchemy + Alembic (migrations) + PostgreSQL ou SQLite selon l'environnement
- SQLModel (Pydantic + SQLAlchemy unifié)
- Tortoise ORM

Justifie ton choix en fonction de ce que tu trouves dans le repository. Si une dépendance de base de données est déjà déclarée dans `requirements.txt`, utilise-la.

**B — Authentification admin**

Puisqu'il n'existe pas de système de rôle fonctionnel, présente comment tu vas protéger les endpoints d'administration. Options :

- Étendre le mécanisme `X-API-Key` existant avec une clé distincte pour l'admin (`X-Admin-Key`)
- Implémenter un JWT minimal avec un endpoint de login (compléter le `auth.py` mort)
- Autre approche cohérente avec le projet

Ne pas inventer un deuxième système parallèle. Choisir l'approche la plus simple compatible avec ce qui existe.

**C — Structure des nouveaux fichiers**

Propose l'arborescence exacte des fichiers que tu vas créer, en respectant la convention de nommage existante.

**D — Migration / initialisation de la base**

Comment les tables seront créées. Si Alembic est utilisé, comment les migrations seront générées.

**E — Risques identifiés**

Liste tout ce qui pourrait casser l'API Expression Écrite existante si tu l'appliques mal.

---

## Architecture métier du module oral

### Entités

#### OralTopic — Sujet oral

Représente un sujet brut, indépendant de sa correction.

| Champ | Type | Contraintes | Notes |
|---|---|---|---|
| `id` | UUID / String | PK | Selon convention choisie en Phase 0 |
| `task_type` | Enum `OralTaskType` | NOT NULL | `TASK_2` ou `TASK_3` |
| `task3_type` | Enum `OralTask3Type` \| NULL | Obligatoire si `task_type = TASK_3`, interdit si `TASK_2` | `DIALECTICAL` ou `ANALYTICAL` |
| `title` | String \| NULL | Optionnel | Libellé court pour l'admin |
| `content` | Text | NOT NULL | Texte brut du sujet |
| `status` | Enum `OralTopicStatus` | NOT NULL, DEFAULT `DRAFT` | |
| `is_archived` | Boolean | DEFAULT False | Suppression logique |
| `created_at` | DateTime | DEFAULT now() | |
| `updated_at` | DateTime | auto-update | |

**Règle de validation** : si `task_type = TASK_3` et `task3_type` est null → rejeter avec HTTP 422. Si `task_type = TASK_2` et `task3_type` est fourni → rejeter avec HTTP 422. Cette vérification est dans le service, pas uniquement dans Pydantic.

#### OralTopicCorrection — Correction pédagogique

Relation 1:1 avec `OralTopic`. Un sujet a au plus une correction active.

| Champ | Type | Contraintes | Notes |
|---|---|---|---|
| `id` | UUID / String | PK | |
| `topic_id` | FK → OralTopic | UNIQUE, NOT NULL | Contrainte UNIQUE en base |
| `status` | Enum `OralCorrectionStatus` | NOT NULL | |
| `ai_raw_output` | JSON | NOT NULL après génération | Sortie brute de l'IA — immuable après écriture |
| `content` | JSON | NOT NULL après génération | Copie de travail éditable par l'admin |
| `ai_model` | String | NULLABLE | ex : `mistral-large-latest` |
| `prompt_version` | String | NULLABLE | Identifiant de version du prompt utilisé |
| `ai_generated_at` | DateTime | NULLABLE | |
| `admin_notes` | Text | NULLABLE | Notes internes de l'administrateur |
| `validated_by` | String | NULLABLE | Identifiant de l'admin ayant validé |
| `validated_at` | DateTime | NULLABLE | |
| `generation_attempts` | Integer | DEFAULT 0 | |
| `created_at` | DateTime | DEFAULT now() | |
| `updated_at` | DateTime | auto-update | |

**Règle critique** : `ai_raw_output` n'est écrit qu'une seule fois, lors de la génération initiale ou d'une régénération explicite. Il n'est jamais exposé en écriture dans l'API PATCH. Lors d'une régénération, `ai_raw_output` est mis à jour, `content` est réinitialisé depuis le nouvel `ai_raw_output`, et `generation_attempts` est incrémenté.

#### OralCombination — Combinaison d'entraînement

| Champ | Type | Contraintes | Notes |
|---|---|---|---|
| `id` | UUID / String | PK | |
| `task2_topic_id` | FK → OralTopic | UNIQUE, NOT NULL | Contrainte UNIQUE en base |
| `task3_topic_id` | FK → OralTopic | UNIQUE, NOT NULL | Contrainte UNIQUE en base |
| `title` | String | NULLABLE | Titre donné par l'admin |
| `status` | Enum `OralCombinationStatus` | NOT NULL, DEFAULT `DRAFT` | |
| `published_at` | DateTime | NULLABLE | |
| `created_at` | DateTime | DEFAULT now() | |
| `updated_at` | DateTime | auto-update | |

### Enums

```python
class OralTaskType(str, Enum):
    TASK_2 = "TASK_2"
    TASK_3 = "TASK_3"

class OralTask3Type(str, Enum):
    DIALECTICAL = "DIALECTICAL"
    ANALYTICAL  = "ANALYTICAL"

class OralTopicStatus(str, Enum):
    DRAFT              = "DRAFT"
    CORRECTION_PENDING = "CORRECTION_PENDING"
    CORRECTION_READY   = "CORRECTION_READY"
    ASSIGNED           = "ASSIGNED"
    PUBLISHED          = "PUBLISHED"
    ARCHIVED           = "ARCHIVED"

class OralCorrectionStatus(str, Enum):
    AI_GENERATED  = "AI_GENERATED"
    ADMIN_REVIEW  = "ADMIN_REVIEW"
    APPROVED      = "APPROVED"
    REJECTED      = "REJECTED"

class OralCombinationStatus(str, Enum):
    DRAFT     = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED  = "ARCHIVED"
```

### Machine à états — OralCorrectionStatus

```
(aucune correction)
        │ génération déclenchée
        ▼
  AI_GENERATED  ←─────────────────────────────┐
        │                                      │
        ├── modification admin ──▶ ADMIN_REVIEW│
        │         │                            │
        │         ├── validation ──▶ APPROVED  │
        │         └── rejet ──▶ REJECTED ──────┘ (régénération)
        │                                      │
        ├── validation directe ──▶ APPROVED    │
        │                                      │
        └── rejet ──▶ REJECTED ────────────────┘ (régénération)

APPROVED ──▶ REJECTED (rejet post-validation) ──▶ régénération
```

**Transitions autorisées :**

| De | Vers | Action |
|---|---|---|
| — | `AI_GENERATED` | Génération initiale |
| `AI_GENERATED` | `ADMIN_REVIEW` | Modification admin |
| `AI_GENERATED` | `APPROVED` | Validation directe |
| `AI_GENERATED` | `REJECTED` | Rejet |
| `ADMIN_REVIEW` | `APPROVED` | Validation |
| `ADMIN_REVIEW` | `REJECTED` | Rejet |
| `APPROVED` | `REJECTED` | Rejet post-validation (rend le sujet indisponible) |
| `REJECTED` | `AI_GENERATED` | Régénération |

Toute transition non listée retourne HTTP 409 avec un message explicite.

---

## Structures de sortie IA attendues

Ces structures définissent le contenu du champ `content` (et initialement de `ai_raw_output`).

L'IA doit retourner du **JSON strict**. Le prompt doit explicitement interdire tout texte d'encadrement, balise Markdown ou commentaire autour du JSON.

### Structure TASK_2

```json
{
  "type": "TASK_2",
  "context": "Description de la situation d'interaction déduite du sujet.",
  "understanding": "Analyse de ce que le candidat doit comprendre de la situation.",
  "objective": "Ce que le candidat doit obtenir comme informations.",
  "expected_information": [
    { "category": "lieu", "detail": "Localisation de l'événement" },
    { "category": "date", "detail": "Date et heure de l'événement" }
  ],
  "suggested_questions": [
    { "question": "Où se déroulera l'événement ?", "category": "lieu" },
    { "question": "À quelle heure commence-t-il ?", "category": "heure" }
  ],
  "possible_interaction": [
    "Introduction : Bonjour, j'ai appris que [...], j'aimerais vous poser quelques questions.",
    "Transition : Je vous remercie pour ces informations, j'aurais également voulu savoir..."
  ],
  "useful_expressions": [
    "J'aimerais savoir si...",
    "Pourriez-vous me préciser...",
    "À quelle heure est-ce que..."
  ],
  "common_mistakes": [
    "Oublier la salutation initiale.",
    "Ne pas remercier en fin d'échange.",
    "Poser plusieurs questions d'un coup sans laisser l'interlocuteur répondre."
  ]
}
```

### Structure TASK_3 — Type DIALECTICAL

```json
{
  "type": "TASK_3",
  "detected_type": "DIALECTICAL",
  "subject_analysis": "Analyse du sujet et identification des enjeux centraux.",
  "problematic": "Quelle est la question centrale soulevée par ce sujet ?",
  "position_example": "Personnellement, je pense que [...] car [...].",
  "arguments": [
    {
      "connector": "Tout d'abord",
      "argument": "Énoncé de l'argument principal.",
      "explanation": "Développement et justification de l'argument.",
      "concrete_example": "Exemple concret issu de la vie réelle ou de l'actualité."
    },
    {
      "connector": "De plus",
      "argument": "Second argument.",
      "explanation": "Développement.",
      "concrete_example": "Exemple."
    }
  ],
  "counter_argument": "Nuance ou contre-argument éventuel pour équilibrer la position.",
  "conclusion_example": "En somme, [reformulation de la position + résumé des arguments + nuance].",
  "useful_expressions": [
    "À mon avis...",
    "Il me semble que...",
    "D'un côté [...], de l'autre [...]"
  ],
  "common_mistakes": [
    "Ne pas prendre position clairement.",
    "Rester sans s'exprimer en cas de blanc.",
    "Utiliser toujours le même connecteur."
  ]
}
```

### Structure TASK_3 — Type ANALYTICAL

```json
{
  "type": "TASK_3",
  "detected_type": "ANALYTICAL",
  "subject_analysis": "Analyse du sujet et identification des axes à traiter.",
  "problematic": "Quelle est la question centrale à développer ?",
  "development_axes": [
    {
      "connector": "Premièrement",
      "axis": "Premier axe de développement.",
      "explanation": "Développement factuel de cet axe.",
      "concrete_example": "Exemple concret illustrant cet axe."
    },
    {
      "connector": "Ensuite",
      "axis": "Deuxième axe.",
      "explanation": "Développement.",
      "concrete_example": "Exemple."
    }
  ],
  "conclusion_example": "En conclusion, [synthèse des axes + ouverture éventuelle].",
  "useful_expressions": [
    "Il convient de noter que...",
    "On peut observer que...",
    "À titre d'exemple..."
  ],
  "common_mistakes": [
    "Imposer une prise de position personnelle sur un sujet analytique.",
    "Ne pas structurer les axes de manière logique.",
    "Manquer d'exemples concrets."
  ]
}
```

**Important** : ne pas forcer un sujet `ANALYTICAL` à produire un `position_example`. Les deux structures ne sont pas interchangeables.

---

## Prompts IA — Spécifications complètes

Les prompts sont la pièce centrale du module. Ils doivent refléter fidèlement la méthodologie officielle Tamaro de l'Expression Orale TCF Canada. Les textes ci-dessous sont les prompts exacts à implémenter — ne pas les paraphraser, ne pas en réduire le contenu.

### Organisation des fichiers

Crée un répertoire `api_app/prompts/oral/` (ou l'équivalent selon les conventions trouvées en Phase 0). Chaque prompt est un fichier Python contenant une fonction qui construit et retourne la chaîne de prompt, et une constante `PROMPT_VERSION`.

Fichiers à créer :
- `api_app/prompts/oral/task2_prompt.py`
- `api_app/prompts/oral/task3_dialectical_prompt.py`
- `api_app/prompts/oral/task3_analytical_prompt.py`

### Exigences communes à tous les prompts oraux

1. La langue de sortie est le **français** — le préciser explicitement dans chaque prompt.
2. La sortie doit être du **JSON strict**, sans texte d'introduction, sans balise Markdown, sans commentaire.
3. Le schéma JSON attendu est décrit **champ par champ** dans le prompt.
4. Tous les champs obligatoires doivent être présents dans la réponse, même si leur valeur est une liste vide.
5. Ne jamais demander à l'IA d'expliquer son raisonnement en dehors du JSON.
6. Utiliser `response_format: {"type": "json_object"}` dans l'appel Mistral (cohérent avec le pattern existant de `llm_service.py`).

---

### Prompt TASK_2 — Texte complet

```
PROMPT_VERSION = "1.0.0"

SYSTEM_PROMPT = """Tu es un expert pédagogique certifié en préparation au TCF Canada (Test de Connaissance du Français), spécialisé dans l'épreuve d'Expression Orale.

Ta mission est d'analyser un sujet de la Tâche 2 et de produire une fiche pédagogique complète pour préparer un candidat à réussir cet exercice.

## CONTEXTE DE LA TÂCHE 2

La Tâche 2 est un exercice en interaction d'une durée totale de 5 minutes 30 :
- 2 minutes de préparation : le candidat lit le sujet et note ses mots-clés sur une feuille.
- 3 minutes 30 d'échange : le candidat dialogue avec l'examinateur pour obtenir des informations spécifiques.

Le candidat joue le rôle d'une personne qui pose des questions à l'examinateur. Le sujet précise le contexte et la relation (ami / inconnu). Le candidat doit obtenir des informations précises en posant des questions ciblées.

## STRUCTURE DU DIALOGUE (à enseigner au candidat)

Le dialogue suit ces 5 étapes dans l'ordre :
1. Salutation adaptée à la relation définie dans le sujet (tu / vous).
2. Introduction : annoncer la raison de la démarche, en respectant le registre.
3. Questionnement : poser des questions ciblées avec des mots interrogatifs variés.
4. Remerciement pour les informations et le temps accordé.
5. Formule de politesse pour conclure l'échange.

## REGISTRES DE LANGUE

- Si l'interlocuteur est un ami ou une relation familière → registre familier, pronom "tu".
- Si l'interlocuteur est un inconnu, un professionnel ou une relation formelle → registre formel, pronom "vous".

## MOTS INTERROGATIFS À MOBILISER

Où / Quel / Quelle / Quand / Qui / Combien / Est-ce que / As-tu / Avez-vous / Comment / Pourquoi

## CATÉGORIES D'INFORMATIONS FRÉQUENTES

Prix, Lieu, Date, Heure, Moyens de paiement, Remise, Couleur, Dimension, Animal de compagnie, Taille, Conditions, Modalités.

## ERREURS FRÉQUENTES À SIGNALER

- Oublier la salutation initiale.
- Ne pas annoncer le motif de l'appel/de la démarche.
- Poser plusieurs questions d'un coup sans laisser l'interlocuteur répondre.
- Réciter un texte appris par cœur (l'examinateur le détecte immédiatement).
- Oublier de remercier et de conclure l'échange.
- Confondre le registre tu/vous imposé par le sujet.
- Parler moins de 1 minute 50 (perte de points garantie).
- Ne pas varier les mots interrogatifs.

## FORMAT DE SORTIE

Réponds UNIQUEMENT avec le JSON ci-dessous. Aucun texte avant, aucun texte après, aucune balise Markdown. Tous les champs sont obligatoires. Les listes peuvent être vides si non applicables.

{
  "type": "TASK_2",
  "register": "tu" ou "vous" selon le sujet,
  "context": "Description précise de la situation d'interaction déduite du sujet : qui sont les personnages, quel est le contexte, quelle relation les unit.",
  "understanding": "Ce que le candidat doit comprendre de la situation pour réussir l'exercice.",
  "objective": "Ce que le candidat doit obtenir comme informations à la fin de l'échange.",
  "expected_information": [
    {"category": "catégorie parmi : lieu / date / heure / prix / moyens de paiement / remise / couleur / dimension / taille / conditions / autre", "detail": "Description précise de l'information à obtenir"}
  ],
  "suggested_questions": [
    {"question": "Question complète et naturelle que le candidat peut poser, dans le bon registre (tu/vous)", "category": "catégorie de l'information visée"}
  ],
  "dialogue_structure": [
    {"step": 1, "label": "Salutation", "example": "Exemple de phrase d'ouverture dans le bon registre"},
    {"step": 2, "label": "Introduction", "example": "Exemple d'annonce du motif de la démarche"},
    {"step": 3, "label": "Questionnement", "example": "Exemple de première question"},
    {"step": 4, "label": "Remerciement", "example": "Exemple de remerciement dans le bon registre"},
    {"step": 5, "label": "Formule de politesse", "example": "Exemple de formule de clôture"}
  ],
  "useful_expressions": [
    "Expression utile complète, dans le bon registre"
  ],
  "common_mistakes": [
    "Erreur fréquente spécifique à ce type de sujet, avec explication courte"
  ],
  "preparation_keywords": [
    "Mot-clé que le candidat devrait noter pendant les 2 minutes de préparation"
  ],
  "coaching_tip": "Conseil personnalisé de coaching spécifique à ce sujet précis, au-delà des conseils généraux."
}"""


def build_task2_prompt(topic_content: str) -> str:
    return f"{SYSTEM_PROMPT}\n\nSujet : {topic_content}"
```

---

### Prompt TASK_3 — Type DIALECTICAL — Texte complet

```
PROMPT_VERSION = "1.0.0"

SYSTEM_PROMPT = """Tu es un expert pédagogique certifié en préparation au TCF Canada (Test de Connaissance du Français), spécialisé dans l'épreuve d'Expression Orale.

Ta mission est d'analyser un sujet de la Tâche 3 de type DIALECTIQUE et de produire une fiche pédagogique complète pour préparer un candidat à réussir cet exercice.

## CONTEXTE DE LA TÂCHE 3

La Tâche 3 est une expression d'un point de vue sans temps de préparation, d'une durée de 4 minutes 30. Le candidat réagit à une question posée par l'examinateur.

Ce sujet est de type DIALECTIQUE : il soulève des points de vue divergents. Le candidat doit :
- prendre clairement position (pour, contre, ou position nuancée/mitigée) ;
- argumenter pour convaincre l'examinateur ;
- structurer son discours en trois phases : introduction, développement, conclusion.

## MÉTHODOLOGIE OBLIGATOIRE EN 3 PHASES

### Phase 1 — Introduction (3 éléments dans l'ordre)

1.1 Amener le sujet — Choisir l'une de ces 5 méthodes :
   A. Par définition : identifier le mot-clé du sujet et le définir clairement.
   B. Par contextualisation thématique : partir du général vers le particulier.
   C. Par contextualisation sociétale : présenter un constat général sur le sujet dans la société actuelle.
   D. Par citation : débuter par une citation pertinente liée à la thématique.
   E. Par contraste : souligner une opposition notable entre deux éléments ou deux époques.

1.2 Poser la problématique — Expliciter la question centrale soulevée par le sujet.

1.3 Prendre position — Donner clairement son point de vue dès l'introduction.
Expressions à utiliser : "Personnellement", "À mon avis", "Pour ma part", "À ce sujet", "En ce qui me concerne".

### Phase 2 — Développement (2 à 4 arguments)

Chaque argument suit cette structure obligatoire :
Connecteur logique + Argument principal + Explication brève + Exemple concret

Connecteurs à utiliser :
- Premier argument : "Tout d'abord", "Premièrement", "En premier lieu"
- Arguments suivants : "Ensuite", "Puis", "De plus", "En outre", "Par ailleurs", "De même", "En second lieu"
- Dernier argument : "Enfin", "D'une part... d'autre part"

Un contre-argument ou une nuance peut être ajouté pour enrichir le développement, notamment si la position est mitigée.

### Phase 3 — Conclusion (4 éléments dans l'ordre)

1. Rappeler le sujet (facultatif mais recommandé) : réintroduire brièvement la problématique.
2. Réaffirmer sa position : réitérer clairement son point de vue.
3. Résumer ses arguments : synthèse concise des points développés.
4. Nuance ou recommandation : apporter une ouverture ou une réserve.

## ERREURS FRÉQUENTES À SIGNALER

- Ne pas prendre position clairement dès l'introduction.
- Utiliser toujours le même connecteur logique.
- Donner uniquement des exemples personnels ou familiaux (manque de crédibilité).
- Rester silencieux en cas de blanc plutôt que de reformuler.
- Oublier de conclure l'exposé.
- Ne pas demander à l'examinateur de répéter le sujet avant de commencer (impossible après le début).
- Transformer involontairement un sujet dialectique en développement analytique (ne pas prendre position).

## FORMAT DE SORTIE

Réponds UNIQUEMENT avec le JSON ci-dessous. Aucun texte avant, aucun texte après, aucune balise Markdown. Tous les champs sont obligatoires. Les listes peuvent être vides si non applicables.

{
  "type": "TASK_3",
  "detected_type": "DIALECTICAL",
  "subject_analysis": "Analyse approfondie du sujet : enjeux, thèmes centraux, contexte de société pertinent.",
  "problematic": "Formulation précise de la problématique centrale soulevée par ce sujet.",
  "introduction_methods": [
    {
      "method": "A - Par définition" ou "B - Par contextualisation thématique" ou "C - Par contextualisation sociétale" ou "D - Par citation" ou "E - Par contraste",
      "example": "Exemple complet d'introduction rédigé avec cette méthode pour CE sujet précis."
    }
  ],
  "position_example": "Exemple de prise de position claire et naturelle pour ce sujet, avec une expression appropriée (Personnellement / À mon avis / etc.).",
  "arguments": [
    {
      "connector": "Connecteur logique à utiliser (ex: Tout d'abord)",
      "argument": "Énoncé clair de l'argument principal.",
      "explanation": "Développement et justification de l'argument.",
      "concrete_example": "Exemple concret issu de l'actualité, des études ou de la vie réelle (pas uniquement un exemple personnel)."
    }
  ],
  "counter_argument": "Nuance ou contre-argument pour enrichir le développement ou équilibrer une position mitigée. Peut être null si non pertinent.",
  "conclusion_example": "Exemple complet de conclusion structurée en 4 étapes : rappel du sujet + réaffirmation de position + résumé des arguments + nuance ou recommandation.",
  "useful_expressions": [
    "Expression utile complète pour ce type de sujet (prise de position, transition, nuance, conclusion)"
  ],
  "common_mistakes": [
    "Erreur fréquente spécifique à ce type de sujet dialectique, avec explication courte"
  ],
  "coaching_tip": "Conseil personnalisé de coaching spécifique à ce sujet précis, au-delà des conseils généraux."
}"""


def build_task3_dialectical_prompt(topic_content: str) -> str:
    return f"{SYSTEM_PROMPT}\n\nSujet : {topic_content}"
```

---

### Prompt TASK_3 — Type ANALYTICAL — Texte complet

```
PROMPT_VERSION = "1.0.0"

SYSTEM_PROMPT = """Tu es un expert pédagogique certifié en préparation au TCF Canada (Test de Connaissance du Français), spécialisé dans l'épreuve d'Expression Orale.

Ta mission est d'analyser un sujet de la Tâche 3 de type ANALYTIQUE et de produire une fiche pédagogique complète pour préparer un candidat à réussir cet exercice.

## CONTEXTE DE LA TÂCHE 3

La Tâche 3 est une expression d'un point de vue sans temps de préparation, d'une durée de 4 minutes 30. Le candidat réagit à une question posée par l'examinateur.

Ce sujet est de type ANALYTIQUE : il appelle un développement factuel, explicatif ou descriptif. Le candidat doit :
- développer le sujet de manière organisée et argumentée ;
- fournir des explications, des faits et des exemples concrets ;
- NE PAS être contraint à une prise de position personnelle tranchée.

IMPORTANT : Ne génère JAMAIS de champ "position_example" pour un sujet analytique. Ne pas transformer ce sujet en débat ou en prise de position personnelle imposée. L'introduction annonce un plan, pas une opinion.

## MÉTHODOLOGIE OBLIGATOIRE EN 3 PHASES

### Phase 1 — Introduction (3 éléments dans l'ordre)

1.1 Amener le sujet — Choisir l'une de ces 5 méthodes :
   A. Par définition : identifier le mot-clé du sujet et le définir clairement.
   B. Par contextualisation thématique : partir du général vers le particulier.
   C. Par contextualisation sociétale : présenter un constat général sur le sujet dans la société actuelle.
   D. Par citation : débuter par une citation pertinente liée à la thématique.
   E. Par contraste : souligner une opposition notable entre deux éléments ou deux époques.

1.2 Poser la problématique — Expliciter la question centrale à traiter.

1.3 Annoncer le plan — Pour un sujet analytique, la troisième partie de l'introduction annonce les axes de développement plutôt qu'une prise de position personnelle.
Exemple : "Je choisirai de m'attarder principalement sur trois aspects : [axe 1], [axe 2] et [axe 3]."

### Phase 2 — Développement (2 à 4 axes)

Chaque axe suit cette structure :
Connecteur logique + Axe de développement + Explication + Exemple concret

Connecteurs à utiliser :
- Premier axe : "Tout d'abord", "Premièrement", "En premier lieu"
- Axes suivants : "Ensuite", "Puis", "De plus", "En outre", "Par ailleurs", "En second lieu"
- Dernier axe : "Enfin"

### Phase 3 — Conclusion

1. Rappeler le sujet (facultatif) : réintroduire brièvement la problématique.
2. Synthétiser les axes développés.
3. Ouvrir sur une perspective ou une recommandation (sans imposer une prise de position personnelle si le sujet ne le requiert pas).

## ERREURS FRÉQUENTES À SIGNALER

- Transformer le sujet analytique en débat avec prise de position personnelle imposée.
- Ne pas structurer les axes de manière logique et progressive.
- Manquer d'exemples concrets et rester dans l'abstraction.
- Utiliser toujours le même connecteur logique.
- Rester silencieux en cas de blanc plutôt que de reformuler ou de reprendre un point déjà évoqué.
- Oublier de conclure l'exposé.
- Ne pas demander à l'examinateur de répéter le sujet avant de commencer.

## FORMAT DE SORTIE

Réponds UNIQUEMENT avec le JSON ci-dessous. Aucun texte avant, aucun texte après, aucune balise Markdown. Tous les champs sont obligatoires. Les listes peuvent être vides si non applicables. Ne génère PAS de champ "position_example".

{
  "type": "TASK_3",
  "detected_type": "ANALYTICAL",
  "subject_analysis": "Analyse approfondie du sujet : thèmes centraux, enjeux, contexte de société pertinent.",
  "problematic": "Formulation précise de la question centrale à traiter.",
  "introduction_methods": [
    {
      "method": "A - Par définition" ou "B - Par contextualisation thématique" ou "C - Par contextualisation sociétale" ou "D - Par citation" ou "E - Par contraste",
      "example": "Exemple complet d'introduction rédigé avec cette méthode pour CE sujet précis, se terminant par l'annonce du plan (pas une prise de position)."
    }
  ],
  "plan_announcement_example": "Exemple de phrase d'annonce du plan adaptée à ce sujet : 'Je choisirai de m'attarder sur [axe 1], [axe 2] et [axe 3].'",
  "development_axes": [
    {
      "connector": "Connecteur logique à utiliser (ex: Tout d'abord)",
      "axis": "Intitulé clair de l'axe de développement.",
      "explanation": "Développement factuel et explicatif de cet axe.",
      "concrete_example": "Exemple concret issu de l'actualité, des études ou de la vie réelle."
    }
  ],
  "conclusion_example": "Exemple complet de conclusion : synthèse des axes + ouverture ou recommandation (sans prise de position personnelle forcée).",
  "useful_expressions": [
    "Expression utile complète pour ce type de sujet analytique (introduction, transition, développement factuel, conclusion)"
  ],
  "common_mistakes": [
    "Erreur fréquente spécifique à ce type de sujet analytique, avec explication courte"
  ],
  "coaching_tip": "Conseil personnalisé de coaching spécifique à ce sujet précis, au-delà des conseils généraux."
}"""


def build_task3_analytical_prompt(topic_content: str) -> str:
    return f"{SYSTEM_PROMPT}\n\nSujet : {topic_content}"
```

---

### Versioning des prompts

Chaque fichier déclare une constante `PROMPT_VERSION = "1.0.0"` au niveau module. Cette valeur est stockée dans `OralTopicCorrection.prompt_version` lors de chaque génération. Elle permet de retracer quelle version du prompt a produit une correction donnée, et de décider si une régénération est nécessaire après mise à jour des prompts.

### Note sur les champs supplémentaires par rapport aux structures de base

Les prompts complets produisent quelques champs supplémentaires par rapport aux structures Pydantic définies dans la section précédente (`introduction_methods`, `dialogue_structure`, `plan_announcement_example`, `register`, `preparation_keywords`, `coaching_tip`). Ces champs enrichissent la correction pédagogique. **Ajoute ces champs aux modèles Pydantic de validation** définis en section "Validation de la sortie IA" :

```python
# Champs à ajouter à Task2CorrectionContent
register: Literal["tu", "vous"]
dialogue_structure: List[DialogueStep] = []   # {"step": int, "label": str, "example": str}
preparation_keywords: List[str] = []
coaching_tip: Optional[str] = None

# Champs à ajouter à Task3DialecticalContent
introduction_methods: List[IntroductionMethod] = []   # {"method": str, "example": str}
coaching_tip: Optional[str] = None

# Champs à ajouter à Task3AnalyticalContent
introduction_methods: List[IntroductionMethod] = []
plan_announcement_example: Optional[str] = None
coaching_tip: Optional[str] = None
```

---

## Validation de la sortie IA

La réponse de l'IA doit être validée avant toute insertion en base.

### Étapes obligatoires

1. **Parsing JSON** : `json.loads(response_text)`. En cas d'échec : logger l'erreur avec le topic_id et la réponse brute (tronquée à 500 caractères pour éviter de logguer des données sensibles). Ne pas faire remonter la réponse brute au client.

2. **Validation de schéma** : vérifier que les champs obligatoires sont présents et que leurs types sont corrects.
   - Si le projet utilise déjà Pydantic pour la validation (ce qui est le cas — c'est le framework principal), créer des modèles Pydantic pour chaque structure de sortie IA.
   - Ne pas introduire Zod, Joi ou une autre librairie. Pydantic est déjà disponible.

3. **Modèles Pydantic de validation à créer** :

```python
# api_app/models/oral_correction.py

class ExpectedInformation(BaseModel):
    category: str
    detail: str

class SuggestedQuestion(BaseModel):
    question: str
    category: str

class Task2CorrectionContent(BaseModel):
    type: Literal["TASK_2"]
    context: str
    understanding: str
    objective: str
    expected_information: List[ExpectedInformation] = []
    suggested_questions: List[SuggestedQuestion] = []
    possible_interaction: List[str] = []
    useful_expressions: List[str] = []
    common_mistakes: List[str] = []

class ArgumentItem(BaseModel):
    connector: str
    argument: str
    explanation: str
    concrete_example: str

class Task3DialecticalContent(BaseModel):
    type: Literal["TASK_3"]
    detected_type: Literal["DIALECTICAL"]
    subject_analysis: str
    problematic: str
    position_example: str
    arguments: List[ArgumentItem] = []
    counter_argument: Optional[str] = None
    conclusion_example: str
    useful_expressions: List[str] = []
    common_mistakes: List[str] = []

class DevelopmentAxis(BaseModel):
    connector: str
    axis: str
    explanation: str
    concrete_example: str

class Task3AnalyticalContent(BaseModel):
    type: Literal["TASK_3"]
    detected_type: Literal["ANALYTICAL"]
    subject_analysis: str
    problematic: str
    development_axes: List[DevelopmentAxis] = []
    conclusion_example: str
    useful_expressions: List[str] = []
    common_mistakes: List[str] = []
```

4. **Gestion des erreurs de validation** : si la validation Pydantic échoue, logger les erreurs de validation avec le topic_id. Ne pas insérer en base. Retourner le statut d'erreur pour ce sujet dans la réponse batch, sans interrompre le traitement des autres sujets.

---

## Référence API complète

Le préfixe de base est `/api/v1` selon la convention existante. Le sous-préfixe pour le module oral est `/oral`.

### Authentification

Tous les endpoints admin utilisent le mécanisme d'authentification retenu en Phase 0. Les endpoints publics (lecture des combinaisons publiées) ne requièrent pas d'authentification ou utilisent le même `X-API-Key` existant selon la décision prise.

### Endpoints — Sujets

#### `POST /api/v1/oral/topics`

Crée un nouveau sujet oral.

**Authentification** : admin  
**Body** :
```json
{
  "task_type": "TASK_2",
  "content": "Je suis votre voisin(e). Vous souhaitez organiser une fête...",
  "title": "Fête entre voisins (optionnel)"
}
```
```json
{
  "task_type": "TASK_3",
  "task3_type": "DIALECTICAL",
  "content": "Faut-il interdire les réseaux sociaux aux moins de 15 ans ?",
  "title": "Réseaux sociaux et mineurs (optionnel)"
}
```

**Validations backend** :
- `task_type = TASK_2` → `task3_type` doit être absent ou null → HTTP 422 sinon
- `task_type = TASK_3` → `task3_type` est obligatoire → HTTP 422 sinon
- `content` non vide → HTTP 422 sinon

**Réponse 201** :
```json
{
  "id": "uuid",
  "task_type": "TASK_3",
  "task3_type": "DIALECTICAL",
  "title": "Réseaux sociaux et mineurs",
  "content": "...",
  "status": "DRAFT",
  "correction": null,
  "created_at": "2026-09-12T10:00:00Z",
  "updated_at": "2026-09-12T10:00:00Z"
}
```

**Erreurs** : 400 (données invalides), 422 (contrainte métier violée)

---

#### `GET /api/v1/oral/topics`

Liste les sujets avec filtres.

**Authentification** : admin  
**Query params** :

| Paramètre | Type | Description |
|---|---|---|
| `task_type` | `TASK_2` \| `TASK_3` | Filtre par type |
| `task3_type` | `DIALECTICAL` \| `ANALYTICAL` | Filtre par sous-type (TASK_3 uniquement) |
| `status` | OralTopicStatus | Filtre par statut |
| `correction_status` | OralCorrectionStatus | Filtre par statut de correction |
| `has_correction` | boolean | `true` = a une correction, `false` = sans correction |
| `available_for_combination` | boolean | `true` = correction APPROVED + pas encore en combinaison |
| `include_archived` | boolean | DEFAULT false |
| `page` | int | Pagination |
| `page_size` | int | DEFAULT 20 |

**Réponse 200** : liste paginée de sujets avec leur correction (sans le champ `ai_raw_output`).

---

#### `GET /api/v1/oral/topics/:id`

Récupère un sujet avec sa correction complète.

**Authentification** : admin  
**Réponse 200** : sujet complet incluant `correction` avec tous ses champs sauf `ai_raw_output` (ce champ n'est jamais exposé dans l'API).  
**Erreurs** : 404 si introuvable ou archivé

---

#### `PATCH /api/v1/oral/topics/:id`

Modifie le texte ou le titre d'un sujet.

**Authentification** : admin  
**Contrainte** : modification interdite si la correction est `APPROVED`. Retourner HTTP 409 avec message `"Ce sujet possède une correction validée. Rejetez la correction avant de modifier le sujet."`.  
**Body** :
```json
{
  "content": "Nouveau texte du sujet",
  "title": "Nouveau titre"
}
```

**Réponse 200** : sujet mis à jour.

---

#### `POST /api/v1/oral/topics/:id/archive`

Archive logiquement un sujet (`is_archived = true`).

**Authentification** : admin  
**Contrainte** : impossible si le sujet est assigné à une combinaison publiée → HTTP 409.  
**Réponse 200** : sujet avec `status = ARCHIVED`.

---

### Endpoints — Génération des corrections

#### `POST /api/v1/oral/topics/generate-corrections`

Génère les corrections IA pour un ou plusieurs sujets.

**Authentification** : admin  
**Body** :
```json
{
  "topic_ids": ["uuid-1", "uuid-2", "uuid-3"]
}
```

**Comportement détaillé** :

1. Valider que `topic_ids` est une liste non vide (max 20 IDs par requête recommandé).
2. Récupérer tous les sujets en une seule requête base.
3. Pour chaque sujet :
   - Vérifier qu'il existe et n'est pas archivé. Si introuvable → enregistrer l'erreur pour ce sujet, continuer.
   - Vérifier que le statut de correction n'est pas `APPROVED`. Si APPROVED → retourner `status: "SKIPPED"` avec message `"Correction déjà validée. Utilisez /regenerate pour régénérer explicitement."`.
   - Construire le prompt adapté au type.
   - Appeler le service IA (réutiliser le client Mistral existant identifié en Phase 0).
   - Parser et valider la réponse JSON avec les modèles Pydantic.
   - Si une correction existe déjà (toute correction non-APPROVED) → mettre à jour l'enregistrement existant (ne pas créer un nouveau).
   - Si aucune correction n'existe → créer un nouvel enregistrement.
   - Initialiser `ai_raw_output` et `content` avec la réponse validée.
   - Mettre le statut à `AI_GENERATED`.
   - Incrémenter `generation_attempts`.
   - Stocker `ai_model` et `prompt_version`.
   - Mettre à jour `OralTopic.status` → `CORRECTION_READY`.
4. Retourner un résultat par sujet.

**Réponse 200** :
```json
{
  "results": [
    {
      "topic_id": "uuid-1",
      "status": "GENERATED",
      "correction_id": "uuid-corr-1",
      "generation_attempts": 1
    },
    {
      "topic_id": "uuid-2",
      "status": "SKIPPED",
      "reason": "Correction déjà validée."
    },
    {
      "topic_id": "uuid-3",
      "status": "ERROR",
      "error": "Échec du parsing JSON de la réponse IA."
    }
  ]
}
```

**Note sur les appels parallèles** : si le projet existant utilise `asyncio.gather()` pour les appels Mistral (ce qui est le cas d'après la documentation), appliquer le même pattern pour le batch oral. Cependant, ne pas partager le même executor ou le même event loop avec `llm_service.py` sans analyse préalable — présenter ton approche en Phase 0.

---

### Endpoints — Review et validation

#### `GET /api/v1/oral/topics/:id/correction`

Récupère la correction d'un sujet.

**Authentification** : admin  
**Réponse 200** :
```json
{
  "id": "uuid-corr",
  "topic_id": "uuid-topic",
  "status": "AI_GENERATED",
  "content": { ... },
  "ai_model": "mistral-large-latest",
  "prompt_version": "1.0.0",
  "ai_generated_at": "2026-09-12T10:05:00Z",
  "admin_notes": null,
  "validated_by": null,
  "validated_at": null,
  "generation_attempts": 1,
  "created_at": "...",
  "updated_at": "..."
}
```

Note : `ai_raw_output` n'est **jamais** retourné dans cette réponse ni dans aucune autre.

---

#### `PATCH /api/v1/oral/topics/:id/correction`

Modifie le contenu de la correction (champ `content`) et/ou les notes admin.

**Authentification** : admin  
**Contrainte** : impossible si statut est `APPROVED` → HTTP 409.  
**Body** :
```json
{
  "content": {
    "type": "TASK_2",
    "context": "Contenu modifié par l'admin...",
    ...
  },
  "admin_notes": "Ajout d'une question sur le budget."
}
```

**Comportement** : si le statut est `AI_GENERATED` et que le body modifie `content`, passer le statut à `ADMIN_REVIEW`.  
**Réponse 200** : correction mise à jour.

---

#### `POST /api/v1/oral/topics/:id/correction/approve`

Valide la correction.

**Authentification** : admin  
**Contraintes de transition** : statut doit être `AI_GENERATED` ou `ADMIN_REVIEW` → sinon HTTP 409.  
**Comportement** :
- Passer le statut à `APPROVED`.
- Enregistrer `validated_by` (identifiant de l'admin authentifié) et `validated_at`.
- Mettre à jour `OralTopic.status` → `CORRECTION_READY` (si ce n'est pas déjà le cas).

**Réponse 200** : correction avec statut mis à jour.

---

#### `POST /api/v1/oral/topics/:id/correction/reject`

Rejette la correction.

**Authentification** : admin  
**Contraintes de transition** : statut doit être `AI_GENERATED`, `ADMIN_REVIEW` ou `APPROVED`.  
**Body** (optionnel) :
```json
{
  "reason": "La correction ne correspond pas à la méthodologie TCF."
}
```

**Comportement** : passer le statut à `REJECTED`. Si `reason` est fourni, l'ajouter à `admin_notes`.  
**Réponse 200** : correction avec statut mis à jour.

---

#### `POST /api/v1/oral/topics/:id/correction/regenerate`

Régénère la correction via l'IA.

**Authentification** : admin  
**Comportement** :
- Si aucune correction n'existe : créer et générer (équivalent à `generate-corrections` pour un seul sujet).
- Si une correction existe avec statut `AI_GENERATED` ou `ADMIN_REVIEW` : régénérer (écraser `ai_raw_output`, réinitialiser `content`, incrémenter `generation_attempts`).
- Si statut `APPROVED` : demander confirmation explicite via un paramètre `force=true` dans la query string. Sans `force=true`, retourner HTTP 409 avec message `"Cette correction est validée. Passez force=true pour forcer la régénération."`.
- Si statut `REJECTED` : régénérer sans confirmation.

**Réponse 200** : correction régénérée.

---

### Endpoints — Combinaisons

#### `POST /api/v1/oral/combinations`

Crée une nouvelle combinaison.

**Authentification** : admin  
**Body** :
```json
{
  "task2_topic_id": "uuid-t2",
  "task3_topic_id": "uuid-t3",
  "title": "Combinaison septembre 2026 n°1"
}
```

**Vérifications dans le service (dans une transaction)** :
1. Vérifier que `task2_topic_id` référence un sujet de type `TASK_2` → HTTP 422 sinon.
2. Vérifier que `task3_topic_id` référence un sujet de type `TASK_3` → HTTP 422 sinon.
3. Vérifier que la correction du sujet T2 a le statut `APPROVED` → HTTP 422 sinon.
4. Vérifier que la correction du sujet T3 a le statut `APPROVED` → HTTP 422 sinon.
5. Vérifier que `task2_topic_id` n'est pas déjà utilisé dans une autre combinaison → HTTP 409 sinon.
6. Vérifier que `task3_topic_id` n'est pas déjà utilisé dans une autre combinaison → HTTP 409 sinon.
7. Créer la combinaison.
8. Mettre à jour `OralTopic.status` → `ASSIGNED` pour les deux sujets.

Toutes ces opérations doivent être dans une transaction. La contrainte UNIQUE en base de données est le filet de sécurité en cas de concurrence, mais la vérification applicative doit produire un message d'erreur lisible.

**Réponse 201** : combinaison créée avec les sujets inclus (sans leurs corrections).

---

#### `GET /api/v1/oral/combinations`

Liste les combinaisons.

**Authentification** : admin  
**Query params** : `status`, `page`, `page_size`

---

#### `GET /api/v1/oral/combinations/:id`

Récupère une combinaison avec ses deux sujets et leurs corrections (sans `ai_raw_output`).

**Authentification** : admin  
**Réponse 200** : combinaison complète.  
**Erreurs** : 404

---

#### `PATCH /api/v1/oral/combinations/:id`

Modifie le titre d'une combinaison.

**Authentification** : admin  
**Contrainte** : uniquement si statut `DRAFT`. HTTP 409 si `PUBLISHED` ou `ARCHIVED`.

---

#### `POST /api/v1/oral/combinations/:id/publish`

Publie une combinaison.

**Authentification** : admin  
**Contrainte** : statut doit être `DRAFT`.  
**Vérification** : re-vérifier que les deux corrections sont toujours `APPROVED` au moment de la publication (elles pourraient avoir été rejetées entre-temps).  
**Comportement** : passer statut à `PUBLISHED`, enregistrer `published_at`, mettre à jour `OralTopic.status` → `PUBLISHED` pour les deux sujets.

---

#### `POST /api/v1/oral/combinations/:id/archive`

Archive une combinaison.

**Authentification** : admin  
**Contrainte** : statut doit être `PUBLISHED` ou `DRAFT`.  
**Comportement** : passer statut à `ARCHIVED`. Les sujets associés redeviennent disponibles (`OralTopic.status` → `CORRECTION_READY`). La contrainte UNIQUE en base de données cesse de bloquer ces sujets uniquement si la ligne `OralCombination` est supprimée ou si la logique de disponibilité ignore les combinaisons archivées — choisis l'approche cohérente avec le schéma retenu et documente-la.

---

### Endpoints publics (utilisateur final)

Ces endpoints ne retournent que le contenu publié. Aucune donnée de correction non validée ne doit y apparaître.

#### `GET /api/v1/oral/combinations/public`

Liste les combinaisons publiées.

**Authentification** : `X-API-Key` existant (ou aucune selon décision Phase 0).  
**Réponse** : liste des combinaisons avec `status = PUBLISHED`, incluant les sujets mais **sans** les corrections détaillées (uniquement les métadonnées utiles pour le frontend).

#### `GET /api/v1/oral/combinations/:id/public`

Récupère une combinaison publiée avec le contenu des corrections validées.

**Authentification** : `X-API-Key`.  
**Contrainte** : retourner HTTP 404 si la combinaison n'est pas `PUBLISHED` (ne pas révéler l'existence des combinaisons non publiées).  
**Réponse** : combinaison complète avec le champ `content` des corrections (le contenu validé, jamais `ai_raw_output`).

---

## Organisation des fichiers à créer

Adapte cette structure à ce que tu trouves dans le repository. Respecte strictement les conventions existantes.

```
api_app/
├── models/
│   ├── evaluation.py          ← EXISTANT — ne pas modifier
│   └── oral/
│       ├── __init__.py        ← si le projet utilise des __init__.py
│       ├── topic.py           ← OralTopic, OralTopicCreate, OralTopicResponse
│       ├── correction.py      ← OralTopicCorrection + modèles de contenu IA
│       └── combination.py     ← OralCombination, OralCombinationCreate, etc.
│
├── routes/
│   ├── evaluation.py          ← EXISTANT — ne pas modifier
│   └── oral/
│       ├── topics.py          ← Router /oral/topics
│       ├── corrections.py     ← Router /oral/topics/:id/correction
│       └── combinations.py    ← Router /oral/combinations
│
├── services/
│   ├── llm_service.py         ← EXISTANT — ne pas modifier
│   ├── rag_service.py         ← EXISTANT — ne pas modifier
│   └── oral/
│       ├── topic_service.py   ← CRUD topics
│       ├── correction_service.py ← génération, review, validation
│       └── combination_service.py ← gestion des combinaisons
│
├── prompts/
│   └── oral/
│       ├── task2_prompt.py
│       ├── task3_dialectical_prompt.py
│       └── task3_analytical_prompt.py
│
├── db/
│   ├── database.py            ← configuration connexion DB + session
│   └── migrations/            ← si Alembic
│
└── main.py                    ← Ajouter le montage des nouveaux routers UNIQUEMENT
```

**Modification de `main.py`** : la seule modification autorisée sur les fichiers existants est l'ajout du montage des nouveaux routers oraux. Aucune autre ligne existante ne doit être modifiée.

---

## Réutilisation du client Mistral existant

Identifie dans `llm_service.py` comment le client Mistral est instancié et comment les appels sont effectués. Le service oral doit réutiliser le même client ou la même configuration, **sans dupliquer** la logique d'initialisation.

Si le client Mistral est instancié dans `__init__` de `LLMService`, deux options :
- Extraire l'initialisation du client dans un module partagé `api_app/services/mistral_client.py` et le réutiliser dans les deux services — **uniquement** si cette extraction ne modifie pas le comportement de `LLMService`.
- Instancier un second client Mistral dans le service oral avec la même configuration — moins élégant mais sans risque.

Présente ton choix en Phase 0 avant d'agir.

---

## Gestion des erreurs

Utilise le format de réponse d'erreur existant tel qu'identifié dans le repository. Si un format standard est déjà utilisé, reproduis-le pour les nouveaux endpoints.

Format minimal si aucune convention n'existe :

```json
{
  "error": {
    "code": "TOPIC_NOT_FOUND",
    "message": "Le sujet demandé n'existe pas.",
    "details": null
  }
}
```

Codes HTTP à utiliser :
- `400` : requête malformée
- `401` : non authentifié
- `403` : accès interdit (rôle insuffisant)
- `404` : ressource introuvable
- `409` : conflit (transition de statut invalide, sujet déjà en combinaison, etc.)
- `422` : validation métier échouée (type incohérent, correction non validée, etc.)
- `500` : erreur interne — ne jamais exposer `str(e)` au client (problème déjà documenté sur le projet existant)

---

## Tests

Respecte le framework de test identifié en Phase 0 (probablement `pytest` + `pytest-asyncio`).

Couvre au minimum les cas suivants :

**Sujets :**
- Création TASK_2 valide
- Création TASK_3 dialectique valide
- Création TASK_3 analytique valide
- Création TASK_2 avec `task3_type` fourni → HTTP 422
- Création TASK_3 sans `task3_type` → HTTP 422
- Modification d'un sujet avec correction APPROVED → HTTP 409
- Archive d'un sujet assigné à une combinaison publiée → HTTP 409

**Génération :**
- Génération d'une correction TASK_2
- Génération d'une correction TASK_3 dialectique
- Génération d'une correction TASK_3 analytique
- Génération batch (2 sujets valides + 1 sujet introuvable)
- Tentative de génération sur une correction APPROVED → SKIPPED
- Réponse IA invalide (JSON malformé) → ERROR sans crash des autres sujets
- Réponse IA incomplète (champ manquant) → ERROR

**Review / validation :**
- Modification d'une correction AI_GENERATED → passage à ADMIN_REVIEW
- Modification d'une correction APPROVED → HTTP 409
- Validation d'une correction AI_GENERATED → APPROVED
- Validation d'une correction ADMIN_REVIEW → APPROVED
- Rejet d'une correction APPROVED → REJECTED
- Régénération d'une correction REJECTED
- Régénération d'une correction APPROVED sans force=true → HTTP 409
- Régénération d'une correction APPROVED avec force=true → succès

**Combinaisons :**
- Création avec T2 non APPROVED → HTTP 422
- Création avec T3 non APPROVED → HTTP 422
- Création avec T2 déjà en combinaison → HTTP 409
- Création valide
- Publication d'une combinaison DRAFT
- Archivage d'une combinaison PUBLISHED
- Modification d'une combinaison PUBLISHED → HTTP 409

**Endpoints publics :**
- `GET /public` retourne uniquement les PUBLISHED
- `GET /:id/public` retourne 404 pour une combinaison DRAFT
- Les corrections non APPROVED n'apparaissent pas dans les endpoints publics
- `ai_raw_output` n'apparaît dans aucune réponse

---

## Documentation Swagger

Si le projet expose Swagger (vérifié en Phase 0 — probablement oui via FastAPI), chaque nouveau router et chaque endpoint doit inclure :

- `summary` et `description` dans le décorateur de route
- Tags : `oral-topics`, `oral-corrections`, `oral-combinations`, `oral-public`
- Modèles de réponse explicites avec `response_model`
- Codes de statut documentés avec `responses={409: ..., 422: ...}`

Ne crée pas une documentation parallèle. Intègre directement dans les décorateurs FastAPI.

---

## Contraintes absolues

1. **Ne jamais modifier** `llm_service.py`, `rag_service.py`, `evaluation.py` (route), `models/evaluation.py` au-delà du strict nécessaire (ajout du montage dans `main.py` uniquement).
2. **Ne jamais exposer** `ai_raw_output` dans une réponse API.
3. **Ne jamais écraser** `ai_raw_output` sans une action explicite de régénération.
4. **Ne jamais traiter** une correction non `APPROVED` comme utilisable dans une combinaison.
5. **Ne jamais permettre** à un sujet d'être dans plusieurs combinaisons — contrainte en base + vérification service.
6. **Ne jamais implémenter** les fonctionnalités hors périmètre listées en contexte (simulateur, STT, TTS, Tâche 1, audio, etc.).
7. **Ne pas exposer** `str(exception)` dans les réponses HTTP (problème documenté sur le projet actuel).

---

## Méthode de travail — Rappel

**Étape 1** : analyser tous les fichiers listés en Phase 0. Ne pas supposer le contenu — inspecter réellement.

**Étape 2** : présenter le rapport d'analyse + les décisions de Phase 0 (base de données, authentification, structure des fichiers, approche client Mistral).

**Étape 3** : attendre validation avant de toucher au code.

**Étape 4** : implémenter dans cet ordre strict :
1. Base de données + migrations
2. Modèles Pydantic
3. Services (topic, correction, combination)
4. Prompts
5. Routes
6. Montage dans `main.py`
7. Tests

**Étape 5** : pour chaque fichier modifié ou créé, annoncer explicitement ce que tu fais et pourquoi.

**Étape 6** : en fin d'implémentation, présenter la liste exhaustive des fichiers modifiés, créés et supprimés, avec les endpoints disponibles et leur méthode d'authentification.

---

## Critères d'acceptation

La phase API est considérée terminée lorsque tous les points suivants sont satisfaits :

- [ ] Les sujets TASK_2 et TASK_3 (dialectique et analytique) peuvent être créés, lus, modifiés et archivés.
- [ ] La validation des types est faite côté backend.
- [ ] Aucun champ "contexte" manuel n'est requis pour TASK_2.
- [ ] Aucun champ "consigne" séparé n'existe pour TASK_3.
- [ ] La génération IA produit des corrections structurées conformes aux schémas définis.
- [ ] `ai_raw_output` et `content` sont distincts et `ai_raw_output` est immuable via l'API.
- [ ] La machine à états des corrections est respectée.
- [ ] Les corrections peuvent être modifiées et validées par l'admin.
- [ ] Les combinaisons exigent deux corrections APPROVED.
- [ ] La contrainte d'unicité des sujets dans les combinaisons est appliquée en base de données ET dans le service.
- [ ] Les endpoints publics ne retournent que le contenu PUBLISHED.
- [ ] `ai_raw_output` n'apparaît dans aucune réponse API.
- [ ] `str(exception)` n'est exposé dans aucune réponse d'erreur.
- [ ] L'API Expression Écrite existante fonctionne exactement comme avant (vérifiable par les tests existants).
- [ ] Les nouveaux endpoints sont documentés dans Swagger.
- [ ] Les tests couvrent les cas nominaux et les cas d'erreur listés.

---

*TAMARO · Module Expression Orale · Instructions implémentation API · v1.0*
