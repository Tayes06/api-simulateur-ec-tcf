from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from api_app.routes import evaluation, oral_correction

# Charger le fichier .env depuis la racine du projet
chemin_racine = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=chemin_racine / ".env")

app = FastAPI(
    title="API Simulateur TCF Canada",
    description="API pour la génération de corrections pédagogiques pour le TCF Canada (Expression Orale et Écrite)",
    version="1.0.0"
)

# Inclusion de l'ensemble des routeurs avec le préfixe d'API
app.include_router(evaluation.router, prefix="/api/v1")
app.include_router(oral_correction.router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {"status": "online"}