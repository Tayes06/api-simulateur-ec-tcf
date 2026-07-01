from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from api_app.routes import evaluation

# Charger le .env
chemin_racine = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=chemin_racine / ".env")

app = FastAPI(
    title="API Simulateur TCF Canada",
    version="1.0.0"
)

# On inclut uniquement ton routeur d'évaluation
app.include_router(evaluation.router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {"status": "online"}