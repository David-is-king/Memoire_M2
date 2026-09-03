"""
src/api/main.py
Serveur FastAPI — Point de contact central de l'architecture. Envoie les alertes à l'APK Flutter.
"""

import asyncio
from datetime import datetime, timezone
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from loguru import logger

from ..database import (
    engine,
    create_tables,
    save_prediction_to_db,
    save_alert_to_db,
    upsert_machine
)
from ..inference.predictor import PredictiveMaintenancePredictor, PredictionOutput

app = FastAPI(title="Edge Predictive Maintenance API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_ws_clients = set()

@app.on_event("startup")
def startup_event():
    logger.info("Démarrage du serveur et synchronisation PostgreSQL...")
    create_tables()

@app.websocket("/ws/monitor")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.add(websocket)
    logger.info(f"📱 APK Mobile connectée au flux temps réel. Total clients : {len(_ws_clients)}")
    try:
        while True:
            # Maintien de la connexion active
            await websocket.receive_text()
    except WebSocketDisconnect:
        _ws_clients.remove(websocket)
        logger.info("📱 APK Mobile déconnectée.")

async def broadcast_prediction(pred: PredictionOutput):
    """Sauvegarde en base de données PostgreSQL et pousse l'analyse vers le Mobile."""
    # 1. Enregistrement asynchrone PostgreSQL
    try:
        save_prediction_to_db(pred)
        upsert_machine(
            motor_id=pred.motor_id,
            status=pred.status,
            health_score=pred.health_score
        )
    except Exception as e:
        logger.error(f"Erreur d'écriture PostgreSQL : {e}")

    # 2. Payload formaté pour l'application Mobile (APK)
    payload = {
        "motor_id": pred.motor_id,
        "timestamp": pred.timestamp.isoformat(),
        "health_score": pred.health_score,
        "failure_probability": pred.failure_probability,
        "rul_days": round(pred.rul_days, 1),
        "status": pred.status,
        "recommendation": pred.recommendation,
        "confidence": round(pred.confidence, 2),
        "class_probabilities": pred.class_probabilities
    }

    # 3. Émission vers les abonnés WebSockets (Flutter UI)
    if _ws_clients:
        tasks = [ws.send_json({"type": "prediction", "data": payload}) for ws in _ws_clients]
        await asyncio.gather(*tasks, return_exceptions=True)