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

# Déclaration des deux collections indispensables pour le RAG
COLL_COPIES = "tcf_copies_dataset"
COLL_METHODE = "tcf_methodologie"
DIMENSION_EMBEDDING = 1024

def initialiser_collections():
    """Crée les collections nécessaires et prépare les index d'agrégation future."""
    collections = [c.name for c in qdrant_client.get_collections().collections]
    
    # Initialisation Collection 1 : Copies
    if COLL_COPIES not in collections:
        print(f"[*] Création de la collection '{COLL_COPIES}'...")
        qdrant_client.create_collection(
            collection_name=COLL_COPIES,
            vectors_config=VectorParams(size=DIMENSION_EMBEDDING, distance=Distance.COSINE),
        )
        # Création immédiate de l'index pour optimiser le filtrage par tâche lors de l'agrégation ultérieure
        qdrant_client.create_payload_index(
            collection_name=COLL_COPIES,
            field_name="tache_id",
            field_schema=PayloadSchemaType.INTEGER,
        )
        print(f"[+] Collection '{COLL_COPIES}' et index 'tache_id' initialisés.")
    
    # Initialisation Collection 2 : Méthodologie
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

def generer_embedding(texte):
    try:
        response = mistral_client.embeddings.create(
            model="mistral-embed",
            inputs=[texte]
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"\n[-] Erreur embedding : {e}")
        return None

def ingerer_dataset():
    fichier_entree = chemin_racine / "data_pipeline" / "datasets" / "copies_evaluees.jsonl"
    if not fichier_entree.exists():
        print(f"[-] Fichier introuvable : {fichier_entree}")
        return

    # Initialisation sécurisée des bases
    initialiser_collections()

    with open(fichier_entree, "r", encoding="utf-8") as f:
        lignes = f.readlines()

    total = len(lignes)
    print(f"[*] Début de l'indexation de {total} copies dans Qdrant Cloud...")

    points_a_uploader = []
    
    for index, ligne in enumerate(lignes, 1):
        chaine = ligne.strip()
        if not chaine:
            continue
            
        donnees = json.loads(chaine)
        texte_candidat = donnees["texte_candidat"]
        point_id = generer_uuid_deterministe(texte_candidat)
        
        print(f"\r[{index}/{total}] Traitement de la copie {point_id[:8]}... ", end="", flush=True)
        
        vecteur = generer_embedding(texte_candidat)
        if vecteur is None:
            continue
            
        # 🛠️ FIX FIX FIX : Ajout explicite du texte_candidat requis pour le RAG !
        payload = {
            "tache_id": donnees["tache_id"],
            "texte_candidat": texte_candidat,  # <--- NE PAS OUBLIER
            "sujet_consigne": donnees["sujet_consigne"],
            "documents_contexte": donnees.get("documents_contexte", []),
            "metadata_candidat": donnees.get("metadata_candidat", {}),
            "evaluation_expert": donnees["evaluation_expert"]
        }
        
        points_a_uploader.append(PointStruct(id=point_id, vector=vecteur, payload=payload))
        
        if len(points_a_uploader) >= 25:
            qdrant_client.upsert(collection_name=COLL_COPIES, wait=True, points=points_a_uploader)
            points_a_uploader = []
            time.sleep(0.5)

    if points_a_uploader:
        qdrant_client.upsert(collection_name=COLL_COPIES, wait=True, points=points_a_uploader)

    print(f"\n\n[🎉 SUCCÈS] Vos {total} copies sont prêtes pour l'évaluation complète !")

if __name__ == "__main__":
    ingerer_dataset()