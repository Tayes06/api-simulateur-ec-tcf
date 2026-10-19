import os
import json
import time
import hashlib
import uuid
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, PayloadSchemaType
from mistralai.client import Mistral
from dotenv import load_dotenv

# 1. Chargement de l'environnement
chemin_script = Path(__file__).resolve()
chemin_racine = chemin_script.parent.parent.parent
load_dotenv(dotenv_path=chemin_racine / ".env")

QDRANT_URL = os.environ.get("QDRANT_URL")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")

if not all([QDRANT_URL, QDRANT_API_KEY, MISTRAL_API_KEY]):
    raise ValueError("Une ou plusieurs clés (QDRANT ou MISTRAL) sont manquantes.")

qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
mistral_client = Mistral(api_key=MISTRAL_API_KEY)

COLL_COPIES = "tcf_copies_dataset"
COLL_METHODE = "tcf_methodologie"
DIMENSION_EMBEDDING = 1024

def initialiser_collections():
    """Crée les collections nécessaires et prépare les index d'agrégation."""
    collections = [c.name for c in qdrant_client.get_collections().collections]
    
    if COLL_COPIES not in collections:
        print(f"[*] Création de la collection '{COLL_COPIES}'...")
        qdrant_client.create_collection(
            collection_name=COLL_COPIES,
            vectors_config=VectorParams(size=DIMENSION_EMBEDDING, distance=Distance.COSINE),
        )
        qdrant_client.create_payload_index(
            collection_name=COLL_COPIES,
            field_name="tache_id",
            field_schema=PayloadSchemaType.INTEGER,
        )
        print(f"[+] Collection '{COLL_COPIES}' et index 'tache_id' initialisés.")
    
    if COLL_METHODE not in collections:
        print(f"[*] Création de la collection '{COLL_METHODE}'...")
        qdrant_client.create_collection(
            collection_name=COLL_METHODE,
            vectors_config=VectorParams(size=DIMENSION_EMBEDDING, distance=Distance.COSINE),
        )
        print(f"[+] Collection '{COLL_METHODE}' initialisée.")

def generer_uuid_deterministe(texte):
    hash_texte = hashlib.md5(texte.encode('utf-8')).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, hash_texte))

def generer_embeddings_batch(liste_textes, max_retries=5):
    """Génère les embeddings par lot avec retry automatique sur erreur 429."""
    for attempt in range(max_retries):
        try:
            response = mistral_client.embeddings.create(
                model="mistral-embed",
                inputs=liste_textes
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                temps_attente = (attempt + 1) * 3
                print(f"\n[⚠️ Rate Limit] Pause de {temps_attente}s (essai {attempt + 1}/{max_retries})...")
                time.sleep(temps_attente)
            else:
                print(f"\n[-] Erreur embedding batch : {e}")
                return None

def ingerer_dataset():
    fichier_entree = chemin_racine / "data_pipeline" / "datasets" / "copies_evaluees.jsonl"
    if not fichier_entree.exists():
        print(f"[-] Fichier introuvable : {fichier_entree}")
        return

    initialiser_collections()

    with open(fichier_entree, "r", encoding="utf-8") as f:
        lignes = [l.strip() for l in f if l.strip()]

    total = len(lignes)
    print(f"[*] Début de l'indexation de {total} copies par lots dans Qdrant Cloud...")

    # Taille de lot de 15 copies par requête d'embedding pour respecter les quotas
    BATCH_SIZE = 15
    
    for idx_batch in range(0, total, BATCH_SIZE):
        batch_lignes = lignes[idx_batch : idx_batch + BATCH_SIZE]
        batch_donnees = [json.loads(l) for l in batch_lignes]
        
        textes_candidats = [d["texte_candidat"] for d in batch_donnees]
        
        embeddings = generer_embeddings_batch(textes_candidats)
        if not embeddings:
            print(f"\n[-] Échec du lot {idx_batch} à {idx_batch + len(batch_lignes)}, passage au suivant.")
            continue

        points_a_uploader = []
        for donnees, vecteur in zip(batch_donnees, embeddings):
            texte_candidat = donnees["texte_candidat"]
            point_id = generer_uuid_deterministe(texte_candidat)

            payload = {
                "tache_id": donnees["tache_id"],
                "texte_candidat": texte_candidat,
                "sujet_consigne": donnees["sujet_consigne"],
                "documents_contexte": donnees.get("documents_contexte", []),
                "metadata_candidat": donnees.get("metadata_candidat", {}),
                "evaluation_expert": donnees["evaluation_expert"]
            }
            points_a_uploader.append(PointStruct(id=point_id, vector=vecteur, payload=payload))

        if points_a_uploader:
            qdrant_client.upsert(collection_name=COLL_COPIES, wait=True, points=points_a_uploader)
            print(f"\r[{min(idx_batch + BATCH_SIZE, total)}/{total}] Copies indexées avec succès...", end="", flush=True)

        # Pause de 0.8 seconde entre chaque lot pour éviter d'asphyxier l'API
        time.sleep(0.8)

    print(f"\n\n[🎉 SUCCÈS] L'ensemble des {total} copies a été indexé avec succès dans '{COLL_COPIES}' !")

if __name__ == "__main__":
    ingerer_dataset()