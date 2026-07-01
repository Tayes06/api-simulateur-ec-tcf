import os
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
    """Lit un fichier PDF et extrait le texte de chaque page."""
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
    """Découpe le texte en blocs sémantiques qui se chevauchent légèrement."""
    chunks = []
    start = 0
    while start < len(texte):
        end = start + taille_chunk
        chunks.append(texte[start:end])
        start += taille_chunk - chevauchement
    return chunks

def generer_embedding(texte):
    try:
        response = mistral_client.embeddings.create(
            model="mistral-embed",
            inputs=[texte]
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"[-] Erreur embedding : {e}")
        return None

def ingerer_documents_methodologie():
    dossier_docs = chemin_racine / "data_pipeline" / "methodology_docs"
    if not dossier_docs.exists():
        print(f"[-] Dossier introuvable. Crée-le ici : {dossier_docs}")
        return

    initialiser_collection()
    points_a_uploader = []

    # On cherche les fichiers .pdf (et on garde les .txt au cas où)
    fichiers_a_traiter = list(dossier_docs.glob("*.pdf")) + list(dossier_docs.glob("*.txt"))

    if not fichiers_a_traiter:
        print(f"[-] Aucun fichier PDF ou TXT trouvé dans {dossier_docs.name}.")
        return

    print(f"[*] Analyse et découpage de {len(fichiers_a_traiter)} document(s) méthodologique(s)...")
    
    for fichier in fichiers_a_traiter:
        print(f"    -> Lecture de : {fichier.name}")
        
        if fichier.suffix.lower() == ".pdf":
            contenu = extraire_texte_pdf(fichier)
        else:
            with open(fichier, "r", encoding="utf-8") as f:
                contenu = f.read()
        
        if not contenu.strip():
            print(f"    [⚠️] Texte vide extrait de {fichier.name}. Passage au suivant.")
            continue

        morceaux = decouper_texte(contenu)
        print(f"    [+] {len(morceaux)} morceaux générés pour ce document.")
        
        for i, morceau in enumerate(morceaux):
            # Agrégation & Idempotence : ID unique et stable basé sur le contenu du morceau
            hash_chunk = hashlib.md5(morceau.encode('utf-8')).hexdigest()
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, hash_chunk))
            
            vecteur = generer_embedding(morceau)
            if TYPE_CHECK := (vecteur is None):
                continue
                
            payload = {
                "source_document": fichier.name,
                "index_chunk": i,
                "contenu_regle": morceau
            }
            
            points_a_uploader.append(PointStruct(id=point_id, vector=vecteur, payload=payload))

    if points_a_uploader:
        print(f"[*] Upload de {len(points_a_uploader)} blocs de règles dans Qdrant Cloud...")
        qdrant_client.upsert(collection_name=NOM_COLLECTION_METHODOLOGIE, wait=True, points=points_a_uploader)
        print(f"\n[🎉 SUCCÈS] Ta méthodologie PDF est indexée avec succès dans '{NOM_COLLECTION_METHODOLOGIE}' !")
    else:
        print("[-] Aucun point valide n'a pu être généré.")

if __name__ == "__main__":
    ingerer_documents_methodologie()