"""
src/api/main.py

FastAPI backend complet :
- REST API pour l'app Flutter (moteurs, prédictions, alertes)
- WebSocket temps réel (push vers Flutter)
- Endpoint MQTT/WebSocket pour recevoir les données ESP32
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from ..inference.predictor import PredictiveMaintenancePredictor, PredictionOutput
from ..cleaning.pipeline import CleaningPipeline
from ..simulator.esp32_simulator import SensorReading, StreamingPipeline
from loguru import logger


# ── In-memory store (remplacer par PostgreSQL en prod) ─────
_motor_states: dict  = {}
_alerts:       list  = []
_ws_clients:   set   = set()


# ── Pydantic Schemas ──────────────────────────────────────

class MotorResponse(BaseModel):
    id: str
    name: str
    location: str
    status: str
    health_score: int
    failure_prob: float
    rul_days: float
    last_seen: str
    is_active: bool
    last_reading: Optional[dict] = None

class AlertResponse(BaseModel):
    id: str
    device_id: str
    device_name: str
    severity: str
    title: str
    message: str
    created_at: str
    is_read: bool

class PredictionResponse(BaseModel):
    device_id: str
    predicted_at: str
    failure_prob: float
    rul_days: float
    recommendation: str
    anomalies: list[str]
    suggested_status: str
    health_score: int
    confidence: float

class SensorReadingRequest(BaseModel):
    motor_id: str
    temperature: float
    vibration_x: float
    vibration_y: float
    vibration_z: float
    current: float
    voltage: float
    acoustic_db: float


# ── App initialization ────────────────────────────────────

predictor: Optional[PredictiveMaintenancePredictor] = None
cleaner:   Optional[CleaningPipeline] = None
streaming: Optional[StreamingPipeline] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global predictor, cleaner, streaming
    logger.info("Starting Predictive Maintenance API...")

    try:
        predictor = PredictiveMaintenancePredictor(artifacts_dir="models/artifacts")
        cleaner   = CleaningPipeline()
        streaming = StreamingPipeline(
            predictor=predictor,
            cleaning_pipeline=cleaner,
            on_prediction=_broadcast_prediction,
        )
        logger.info("✓ Models loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load models: {e}")
        logger.warning("API starting without ML models — ingest endpoints will be disabled")

    yield   # App runs here

    logger.info("Shutting down API...")


app = FastAPI(
    title="Predictive Maintenance API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════
# REST Endpoints
# ═══════════════════════════════════════════════════════════

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "models_loaded": predictor is not None,
        "motors": len(_motor_states),
        "active_ws_clients": len(_ws_clients),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Devices ───────────────────────────────────────────────

@app.get("/api/v1/devices", response_model=list[MotorResponse])
def get_devices():
    return [_motor_to_response(m) for m in _motor_states.values()]


@app.get("/api/v1/devices/{device_id}", response_model=MotorResponse)
def get_device(device_id: str):
    if device_id not in _motor_states:
        raise HTTPException(status_code=404, detail="Device not found")
    return _motor_to_response(_motor_states[device_id])


# ── Predictions ────────────────────────────────────────────

@app.get("/api/v1/predictions/{device_id}", response_model=PredictionResponse)
def get_prediction(device_id: str):
    """Retourne la dernière prédiction connue pour un moteur."""
    state = _motor_states.get(device_id)
    if not state or "last_prediction" not in state:
        raise HTTPException(status_code=404, detail="No prediction available for this device")
    return _prediction_to_response(state["last_prediction"])


@app.post("/api/v1/predictions/{device_id}/trigger")
async def trigger_prediction(device_id: str, background_tasks: BackgroundTasks):
    """Force une nouvelle prédiction avec les dernières données disponibles."""
    state = _motor_states.get(device_id)
    if not state or "last_features" not in state:
        raise HTTPException(status_code=400, detail="No sensor data available for prediction")

    background_tasks.add_task(_run_prediction_task, device_id, state["last_features"])
    return {"status": "prediction_triggered", "device_id": device_id}


# ── Sensor data ingestion (depuis ESP32 ou simulateur) ─────

@app.post("/api/v1/ingest")
async def ingest_sensor_data(reading: SensorReadingRequest):
    """
    Endpoint principal de réception des données capteurs.
    Appelé par l'ESP32 (ou le simulateur) à chaque lecture.
    """
    if streaming is None:
        raise HTTPException(status_code=503, detail="ML pipeline not initialized")

    sensor = SensorReading(
        motor_id=reading.motor_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        temperature=reading.temperature,
        vibration_x=reading.vibration_x,
        vibration_y=reading.vibration_y,
        vibration_z=reading.vibration_z,
        current=reading.current,
        voltage=reading.voltage,
        acoustic_db=reading.acoustic_db,
        source="esp32",
    )

    # Mettre à jour le dernier reading connu
    if reading.motor_id not in _motor_states:
        _motor_states[reading.motor_id] = {
            "id": reading.motor_id,
            "name": f"Motor {reading.motor_id}",
            "location": "Unknown",
            "status": "healthy",
            "health_score": 100,
            "failure_prob": 0.0,
            "rul_days": 365.0,
            "is_active": True,
            "last_seen": datetime.now(timezone.utc).isoformat(),
        }

    _motor_states[reading.motor_id]["last_reading"] = reading.dict()
    _motor_states[reading.motor_id]["last_seen"] = datetime.now(timezone.utc).isoformat()

    # Ajouter au pipeline streaming (prédiction si buffer plein)
    await streaming.ingest(sensor)

    return {"status": "accepted", "motor_id": reading.motor_id}


# ── Alerts ────────────────────────────────────────────────

@app.get("/api/v1/alerts", response_model=list[AlertResponse])
def get_alerts(unread: bool = False):
    alerts = _alerts if not unread else [a for a in _alerts if not a["is_read"]]
    return [AlertResponse(**a) for a in sorted(alerts, key=lambda x: x["created_at"], reverse=True)]


@app.patch("/api/v1/alerts/{alert_id}/read")
def mark_alert_read(alert_id: str):
    for a in _alerts:
        if a["id"] == alert_id:
            a["is_read"] = True
            return {"status": "ok"}
    raise HTTPException(status_code=404, detail="Alert not found")


@app.post("/api/v1/alerts/mark-all-read")
def mark_all_read():
    for a in _alerts:
        a["is_read"] = True
    return {"status": "ok", "count": len(_alerts)}


# ═══════════════════════════════════════════════════════════
# WebSocket (temps réel vers Flutter)
# ═══════════════════════════════════════════════════════════

@app.websocket("/ws/all")
async def ws_all(websocket: WebSocket):
    """WebSocket principal — reçoit toutes les mises à jour en temps réel."""
    await websocket.accept()
    _ws_clients.add(websocket)
    logger.info(f"WS client connected: {websocket.client}")
    try:
        # Envoyer l'état actuel dès la connexion
        await websocket.send_json({
            "type": "initial_state",
            "data": {
                "motors":  [_motor_to_response(m) for m in _motor_states.values()],
                "alerts":  [dict(a) for a in _alerts[-20:]],
            }
        })
        # Garder la connexion ouverte
        while True:
            msg = await websocket.receive_text()
            data = json.loads(msg)
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        _ws_clients.discard(websocket)
        logger.info(f"WS client disconnected: {websocket.client}")


@app.websocket("/ws/devices/{device_id}")
async def ws_device(websocket: WebSocket, device_id: str):
    """WebSocket dédié à un moteur spécifique."""
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        while True:
            await asyncio.sleep(1)
            if device_id in _motor_states:
                state = _motor_states[device_id]
                await websocket.send_json({
                    "type": "device_update",
                    "data": _motor_to_response(state),
                })
    except WebSocketDisconnect:
        _ws_clients.discard(websocket)


# ═══════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════

async def _broadcast_prediction(prediction: PredictionOutput):
    """Appelé par le StreamingPipeline après chaque prédiction."""
    motor_id = prediction.motor_id

    # Mettre à jour l'état du moteur
    if motor_id not in _motor_states:
        _motor_states[motor_id] = {
            "id": motor_id, "name": f"Motor {motor_id}",
            "location": "Production Line", "is_active": True,
        }

    _motor_states[motor_id].update({
        "status":        prediction.status,
        "health_score":  prediction.health_score,
        "failure_prob":  prediction.failure_probability,
        "rul_days":      prediction.rul_days,
        "last_seen":     prediction.timestamp.isoformat(),
        "last_prediction": prediction,
    })

    # Créer une alerte si nécessaire
    if prediction.status in ("warning", "critical"):
        await _create_alert(prediction)

    # Broadcaster à tous les clients WebSocket Flutter
    msg = {
        "type": "prediction_update",
        "data": {
            "motor_id":    motor_id,
            "status":      prediction.status,
            "health_score": prediction.health_score,
            "failure_prob": prediction.failure_probability,
            "rul_days":    prediction.rul_days,
            "timestamp":   prediction.timestamp.isoformat(),
        }
    }

    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send_json(msg)
        except Exception:
            dead.add(ws)
    _ws_clients -= dead


async def _create_alert(prediction: PredictionOutput):
    """Crée une alerte et la broadcast aux clients Flutter."""
    import uuid
    severity = "critical" if prediction.status == "critical" else "warning"
    title = {
        "critical": "Panne imminente détectée",
        "warning":  "Dégradation détectée",
    }[severity]

    alert = {
        "id":          str(uuid.uuid4()),
        "device_id":   prediction.motor_id,
        "device_name": _motor_states.get(prediction.motor_id, {}).get("name", prediction.motor_id),
        "severity":    severity,
        "title":       title,
        "message":     prediction.recommendation,
        "created_at":  datetime.now(timezone.utc).isoformat(),
        "is_read":     False,
    }
    _alerts.insert(0, alert)
    if len(_alerts) > 500:
        _alerts.pop()

    # Broadcaster l'alerte
    alert_msg = {"type": "alert", "data": alert}
    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send_json(alert_msg)
        except Exception:
            dead.add(ws)
    _ws_clients -= dead


async def _run_prediction_task(device_id: str, features: dict):
    if predictor is None:
        return
    prediction = predictor.predict_single(features, device_id)
    await _broadcast_prediction(prediction)


def _motor_to_response(state: dict) -> dict:
    pred = state.get("last_prediction")
    return {
        "id":            state.get("id", "?"),
        "name":          state.get("name", "Unknown"),
        "location":      state.get("location", "?"),
        "status":        state.get("status", "healthy"),
        "health_score":  state.get("health_score", 100),
        "failure_prob":  state.get("failure_prob", 0.0),
        "rul_days":      state.get("rul_days", 365.0),
        "last_seen":     state.get("last_seen", datetime.now(timezone.utc).isoformat()),
        "is_active":     state.get("is_active", True),
        "last_reading":  state.get("last_reading"),
    }


def _prediction_to_response(pred: PredictionOutput) -> dict:
    return {
        "device_id":       pred.motor_id,
        "predicted_at":    pred.timestamp.isoformat(),
        "failure_prob":    pred.failure_probability,
        "rul_days":        pred.rul_days,
        "recommendation":  pred.recommendation,
        "anomalies":       pred.anomaly_features,
        "suggested_status": pred.status,
        "health_score":    pred.health_score,
        "confidence":      pred.confidence,
    }


# ── Run ───────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=False, workers=1)
