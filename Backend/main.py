"""Point d'entree FastAPI de l'application backend.

Ce fichier assemble toute l'API :
- configuration globale de FastAPI,
- CORS pour autoriser Flutter,
- routers REST separes,
- router WebSocket pour le temps reel.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from Backend.core.config import settings
from Backend.routers import alerts, auth, motors, predictions, users, websocket


app = FastAPI(
    title=settings.app_name,
    description="API de maintenance predictive pour moteurs IoT.",
    version="1.0.0",
)

# CORS : indispensable pour que Flutter Web/Desktop puisse appeler le backend local.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tous les endpoints REST sont regroupes sous /api/v1 pour matcher ApiService.baseUrl.
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(users.router, prefix=settings.api_prefix)
app.include_router(motors.router, prefix=settings.api_prefix)
app.include_router(predictions.router, prefix=settings.api_prefix)
app.include_router(alerts.router, prefix=settings.api_prefix)

# Les WebSockets restent sous /ws parce que le front utilise ws://localhost:8000/ws/...
app.include_router(websocket.router)


@app.get("/")
def index() -> dict[str, str]:
    """Route de sante simple pour verifier que le serveur repond."""
    return {"status": "online", "message": "Backend FastAPI pret pour SmartPredict."}


@app.get("/health")
def health() -> dict[str, str]:
    """Route de healthcheck lisible par un navigateur, Docker ou un script."""
    return {"status": "ok"}


if __name__ == "__main__":
    # Commande equivalente : python -m Backend.main
    uvicorn.run("Backend.main:app", host=settings.host, port=settings.port, reload=True)
