import os
import time
import hashlib
import uuid
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from mistralai.client import Mistral
from pypdf import PdfReader
from dotenv import load_dotenv

# Configuration de l'environnement
chemin_script = Path(__file__).resolve()
chemin_racine = chemin_script.parent.parent.parent
load_dotenv(dotenv_path=chemin_racine / ".env")

QDRANT_URL = os.environ.get("QDRANT_URL")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")

qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
mistral_client = Mistral(api_key=MISTRAL_API_KEY)

NOM_COLLECTION_METHODOLOGIE = "tcf_methodologie"
DIMENSION_EMBEDDING = 1024

def initialiser_collection():
    collections = qdrant_client.get_collections()
    nom_collections = [c.name for c in collections.collections]
    
    if NOM_COLLECTION_METHODOLOGIE not in nom_collections:
        print(f"[*] Création de la collection '{NOM_COLLECTION_METHODOLOGIE}'...")
        qdrant_client.create_collection(
            collection_name=NOM_COLLECTION_METHODOLOGIE,
            vectors_config=VectorParams(size=DIMENSION_EMBEDDING, distance=Distance.COSINE),
        )
        print(f"[+] Collection '{NOM_COLLECTION_METHODOLOGIE}' créée.")

def extraire_texte_pdf(chemin_pdf):
    texte_complet = ""
    try:
        reader = PdfReader(chemin_pdf)
        for num_page, page in enumerate(reader.pages, 1):
            texte_page = page.extract_text()
            if texte_page:
                texte_complet += f"\n--- [Page {num_page}] ---\n" + texte_page
    except Exception as e:
        print(f"[-] Erreur lors de la lecture du PDF {chemin_pdf.name} : {e}")
    return texte_complet

def decouper_texte(texte, taille_chunk=800, chevauchement=150):
    chunks = []
    start = 0
    while start < len(texte):
        end = start + taille_chunk
        chunks.append(texte[start:end])
        start += taille_chunk - chevauchement
    return chunks

def generer_embeddings_batch(liste_textes, max_retries=3):
    """Génère les embeddings par batch avec retry en cas de rate-limit (429)."""
    for attempt in range(max_retries):
        try:
            response = mistral_client.embeddings.create(
                model="mistral-embed",
                inputs=liste_textes
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                print(f" [⚠️ Rate Limit] Pause de 5 secondes avant réessai ({attempt + 1}/{max_retries})...")
                time.sleep(5)
            else:
                print(f"[-] Erreur embedding batch : {e}")
                return None

def ingerer_documents_methodologie():
    dossier_docs = chemin_racine / "data_pipeline" / "methodology_docs"
    if not dossier_docs.exists():
        print(f"[-] Dossier introuvable : {dossier_docs}")
        return

    initialiser_collection()
    
    fichiers_a_traiter = list(dossier_docs.glob("*.pdf")) + list(dossier_docs.glob("*.txt"))
    if not fichiers_a_traiter:
        print(f"[-] Aucun fichier PDF ou TXT trouvé dans {dossier_docs.name}.")
        return

    print(f"[*] Analyse et découpage de {len(fichiers_a_traiter)} document(s) méthodologique(s)...")
    
    tous_les_morceaux = []
    
    for fichier in fichiers_a_traiter:
        print(f"    -> Lecture de : {fichier.name}")
        contenu = extraire_texte_pdf(fichier) if fichier.suffix.lower() == ".pdf" else fichier.read_text(encoding="utf-8")
        
        if not contenu.strip():
            continue

        morceaux = decouper_texte(contenu)
        print(f"    [+] {len(morceaux)} morceaux générés pour {fichier.name}.")
        
        for i, m in enumerate(morceaux):
            tous_les_morceaux.append({
                "source": fichier.name,
                "index": i,
                "texte": m
            })

    # Traitement par paquets de 10 morceaux pour respecter le Rate Limit Mistral
    BATCH_SIZE = 10
    points_a_uploader = []
    total_morceaux = len(tous_les_morceaux)
    
    print(f"[*] Traitement par lots de {BATCH_SIZE} morceaux...")
    
    for i in range(0, total_morceaux, BATCH_SIZE):
        batch = tous_les_morceaux[i:i + BATCH_SIZE]
        textes_batch = [item["texte"] for item in batch]
        
        embeddings = generer_embeddings_batch(textes_batch)
        if not embeddings:
            print(f"[-] Échec du lot {i} à {i+BATCH_SIZE}, passage au suivant.")
            continue

        for item, vecteur in zip(batch, embeddings):
            hash_chunk = hashlib.md5(item["texte"].encode('utf-8')).hexdigest()
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, hash_chunk))
            
            payload = {
                "source_document": item["source"],
                "index_chunk": item["index"],
                "contenu_regle": item["texte"]
            }
            points_a_uploader.append(PointStruct(id=point_id, vector=vecteur, payload=payload))
            
        # Pause de 1 seconde entre chaque batch pour éviter le 429
        time.sleep(1)

    if points_a_uploader:
        print(f"[*] Upload de {len(points_a_uploader)}/ {total_morceaux} blocs de règles dans Qdrant Cloud...")
        qdrant_client.upsert(collection_name=NOM_COLLECTION_METHODOLOGIE, wait=True, points=points_a_uploader)
        print(f"\n[🎉 SUCCÈS] Indexation complète terminée avec succès dans '{NOM_COLLECTION_METHODOLOGIE}' !")

if __name__ == "__main__":
    ingerer_documents_methodologie()