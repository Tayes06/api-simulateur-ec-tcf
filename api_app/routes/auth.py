from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from api_app.core.security import creer_access_token, verifier_mot_de_passe

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

# Simule l'utilisateur unique pour tes tests
FAKE_USERS_DB = {
    "admin_tcf": {
        "username": "admin_tcf",
        # Hash SHA-256 pur de "tcf_password_2026"
        "hashed_password": "426bc0b957608f6b1fc94cb3ef1993fc57112ea0cc1d596632607f2ef8c7bb80", 
        "disabled": False,
    }
}

@router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = FAKE_USERS_DB.get(form_data.username)
    if not user or not verifier_mot_de_passe(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiant ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = creer_access_token(data={"sub": user["username"]})
    return {"access_token": access_token, "token_type": "bearer"}