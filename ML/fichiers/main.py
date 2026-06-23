"""
src/api/main.py  — VERSION CORRIGÉE

Corrections apportées :
1. engine importé depuis database.py (n'était pas défini ici avant)
2. Login utilise la session SQLAlchemy proprement
3. Prédictions ET alertes sauvegardées en PostgreSQL automatiquement
4. Machines synchronisées dans la table machine à chaque prédiction
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from loguru import logger
from sqlalchemy import text

# ── Import BD centralisée ─────────────────────────────────
from ..database import (
    engine,
    test_connection,
    create_tables,
    save_prediction_to_db,
    save_alert_to_db,
    upsert_machine,
    SessionLocal,
)

from ..inference.predictor import PredictiveMaintenancePredictor, PredictionOutput
from ..cleaning.pipeline import CleaningPipeline
from ..simulator.esp32_simulator import SensorReading, StreamingPipeline


# ── In-memory cache (état courant des moteurs) ────────────
_motor_states: dict = {}
_alerts:       list = []
_ws_clients:   set  = set()


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

class LoginRequest(BaseModel):
    email: str
    password: str


# ── App initialization ────────────────────────────────────

predictor: Optional[PredictiveMaintenancePredictor] = None
cleaner:   Optional[CleaningPipeline] = None
streaming: Optional[StreamingPipeline] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global predictor, cleaner, streaming

    # Test connexion PostgreSQL au démarrage
    if not test_connection():
        logger.warning("⚠ PostgreSQL non disponible — l'API démarre quand même")
    else:
        create_tables()   # s'assure que les tables existent

    # Charger les modèles ML
    try:
        predictor = PredictiveMaintenancePredictor(artifacts_dir="models/artifacts")
        cleaner   = CleaningPipeline()
        streaming = StreamingPipeline(
            predictor=predictor,
            cleaning_pipeline=cleaner,
            on_prediction=_broadcast_prediction,
        )
        logger.info("✓ Modèles ML chargés")
    except Exception as e:
        logger.error(f"✗ Chargement modèles échoué : {e}")
        logger.warning("API sans ML — /ingest désactivé jusqu'au chargement des modèles")

    yield
    logger.info("API arrêtée.")


app = FastAPI(
    title="Predictive Maintenance API",
    description="Maintenance prédictive moteurs électriques — ESP32 + ML",
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
# AUTH
# ═══════════════════════════════════════════════════════════

@app.post("/api/v1/auth/login")
async def login(req: LoginRequest):
    """Authentification utilisateur depuis la table UserProfil."""
    try:
        query = text("""
            SELECT id, email, firstname, lastname, poste, "superAdmin"
            FROM "UserProfil"
            WHERE email = :email AND password = :password
        """)
        with engine.connect() as conn:
            result = conn.execute(query, {"email": req.email, "password": req.password}).fetchone()

        if result:
            return {
                "status": "success",
                "user": {
                    "id":        str(result[0]),
                    "email":     result[1],
                    "firstname": result[2],
                    "lastname":  result[3],
                    "name":      f"{result[2]} {result[3]}",
                    "poste":     result[4],
                    "superAdmin": result[5],
                }
            }
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")


# ═══════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════

@app.get("/health")
def health_check():
    db_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    return {
        "status":           "ok",
        "database":         "connected" if db_ok else "disconnected",
        "models_loaded":    predictor is not None,
        "motors_active":    len(_motor_states),
        "ws_clients":       len(_ws_clients),
        "timestamp":        datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════
# DEVICES (table machine)
# ═══════════════════════════════════════════════════════════

@app.get("/api/v1/devices", response_model=list[MotorResponse])
def get_devices():
    """Liste tous les moteurs (mémoire + BD)."""
    # Essayer de charger depuis la BD d'abord
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM machine WHERE is_active = true")).fetchall()
        for row in rows:
            mid = str(row[0])
            if mid not in _motor_states:
                _motor_states[mid] = {
                    "id": mid, "name": row[1], "location": row[2],
                    "status": row[3], "health_score": row[4],
                    "is_active": row[5],
                    "last_seen": datetime.now(timezone.utc).isoformat(),
                    "failure_prob": 0.0, "rul_days": 365.0,
                }
    except Exception as e:
        logger.warning(f"DB read error (using memory): {e}")

    return [_motor_to_response(m) for m in _motor_states.values()]


@app.get("/api/v1/devices/{device_id}", response_model=MotorResponse)
def get_device(device_id: str):
    if device_id not in _motor_states:
        raise HTTPException(status_code=404, detail="Device not found")
    return _motor_to_response(_motor_states[device_id])


# ═══════════════════════════════════════════════════════════
# PREDICTIONS (table prediction)
# ═══════════════════════════════════════════════════════════

@app.get("/api/v1/predictions/{device_id}", response_model=PredictionResponse)
def get_prediction(device_id: str):
    """Retourne la dernière prédiction pour un moteur (depuis BD ou mémoire)."""
    # Essayer BD d'abord
    try:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT motor_id, predicted_at, failure_probability, rul_days,
                       recommendation, status, health_score, confidence
                FROM prediction
                WHERE motor_id = :mid
                ORDER BY predicted_at DESC LIMIT 1
            """), {"mid": device_id}).fetchone()
        if row:
            return {
                "device_id":        row[0],
                "predicted_at":     row[1].isoformat(),
                "failure_prob":     row[2] or 0.0,
                "rul_days":         row[3] or 365.0,
                "recommendation":   row[4] or "",
                "anomalies":        [],
                "suggested_status": row[5] or "healthy",
                "health_score":     row[6] or 100,
                "confidence":       row[7] or 0.5,
            }
    except Exception as e:
        logger.warning(f"BD prediction read error: {e}")

    # Fallback mémoire
    state = _motor_states.get(device_id)
    if state and "last_prediction" in state:
        return _prediction_to_response(state["last_prediction"])

    raise HTTPException(status_code=404, detail="Aucune prédiction disponible pour ce device")


# ═══════════════════════════════════════════════════════════
# INGEST — données ESP32 / simulateur
# ═══════════════════════════════════════════════════════════

@app.post("/api/v1/ingest")
async def ingest_sensor_data(reading: SensorReadingRequest):
    """
    Reçoit les données de l'ESP32 (ou du simulateur).
    Sauvegarde dans sensor_data + déclenche la prédiction ML.
    """
    if streaming is None:
        raise HTTPException(status_code=503, detail="ML pipeline non initialisé — lancer l'entraînement d'abord")

    now = datetime.now(timezone.utc)

    # Sauvegarder en BD
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO sensor_data
                    (motor_id, timestamp, temperature, vibration_x, vibration_y,
                     vibration_z, current, voltage, acoustic_db, source)
                VALUES
                    (:motor_id, :ts, :temp, :vx, :vy, :vz, :cur, :volt, :db, 'esp32')
            """), {
                "motor_id": reading.motor_id, "ts": now,
                "temp": reading.temperature, "vx": reading.vibration_x,
                "vy": reading.vibration_y,   "vz": reading.vibration_z,
                "cur": reading.current,       "volt": reading.voltage,
                "db": reading.acoustic_db,
            })
            conn.commit()
    except Exception as e:
        logger.warning(f"sensor_data insert failed: {e}")

    # Init état moteur si nouveau
    if reading.motor_id not in _motor_states:
        _motor_states[reading.motor_id] = {
            "id": reading.motor_id, "name": f"Motor {reading.motor_id}",
            "location": "Production Line", "status": "healthy",
            "health_score": 100, "failure_prob": 0.0, "rul_days": 365.0,
            "is_active": True, "last_seen": now.isoformat(),
        }
        upsert_machine(reading.motor_id)

    _motor_states[reading.motor_id]["last_reading"] = reading.dict()
    _motor_states[reading.motor_id]["last_seen"] = now.isoformat()

    # Envoyer au pipeline streaming → prédiction si buffer plein
    sensor = SensorReading(
        motor_id=reading.motor_id, timestamp=now.isoformat(),
        temperature=reading.temperature, vibration_x=reading.vibration_x,
        vibration_y=reading.vibration_y, vibration_z=reading.vibration_z,
        current=reading.current, voltage=reading.voltage,
        acoustic_db=reading.acoustic_db, source="esp32",
    )
    await streaming.ingest(sensor)

    return {"status": "accepted", "motor_id": reading.motor_id}


# ═══════════════════════════════════════════════════════════
# ALERTS (table alerts)
# ═══════════════════════════════════════════════════════════

@app.get("/api/v1/alerts", response_model=list[AlertResponse])
def get_alerts(unread: bool = False):
    """Retourne les alertes depuis la BD."""
    try:
        query = "SELECT id, device_id, device_name, severity, title, message, created_at, is_read FROM alerts"
        if unread:
            query += " WHERE is_read = false"
        query += " ORDER BY created_at DESC LIMIT 100"
        with engine.connect() as conn:
            rows = conn.execute(text(query)).fetchall()
        return [AlertResponse(
            id=str(r[0]), device_id=r[1], device_name=r[2] or r[1],
            severity=r[3], title=r[4], message=r[5],
            created_at=r[6].isoformat() if hasattr(r[6], 'isoformat') else str(r[6]),
            is_read=bool(r[7]),
        ) for r in rows]
    except Exception as e:
        logger.warning(f"Alerts BD error: {e}")
        alerts = _alerts if not unread else [a for a in _alerts if not a["is_read"]]
        return [AlertResponse(**a) for a in sorted(alerts, key=lambda x: x["created_at"], reverse=True)]


@app.patch("/api/v1/alerts/{alert_id}/read")
def mark_alert_read(alert_id: str):
    try:
        with engine.connect() as conn:
            conn.execute(text("UPDATE alerts SET is_read = true WHERE id = :id"), {"id": alert_id})
            conn.commit()
    except Exception as e:
        logger.warning(f"mark_read BD error: {e}")
    for a in _alerts:
        if a["id"] == alert_id:
            a["is_read"] = True
    return {"status": "ok"}


@app.post("/api/v1/alerts/mark-all-read")
def mark_all_read():
    try:
        with engine.connect() as conn:
            conn.execute(text("UPDATE alerts SET is_read = true"))
            conn.commit()
    except Exception as e:
        logger.warning(f"mark_all_read BD error: {e}")
    for a in _alerts:
        a["is_read"] = True
    return {"status": "ok", "count": len(_alerts)}


# ═══════════════════════════════════════════════════════════
# WEBSOCKET
# ═══════════════════════════════════════════════════════════

@app.websocket("/ws/all")
async def ws_all(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.add(websocket)
    logger.info(f"WS client connecté: {websocket.client}")
    try:
        await websocket.send_json({
            "type": "initial_state",
            "data": {
                "motors": [_motor_to_response(m) for m in _motor_states.values()],
                "alerts": _alerts[-20:],
            }
        })
        while True:
            msg = await websocket.receive_text()
            data = json.loads(msg)
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        _ws_clients.discard(websocket)
        logger.info(f"WS client déconnecté")


@app.websocket("/ws/devices/{device_id}")
async def ws_device(websocket: WebSocket, device_id: str):
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        while True:
            await asyncio.sleep(2)
            if device_id in _motor_states:
                await websocket.send_json({
                    "type": "device_update",
                    "data": _motor_to_response(_motor_states[device_id]),
                })
    except WebSocketDisconnect:
        _ws_clients.discard(websocket)


# ═══════════════════════════════════════════════════════════
# HELPERS INTERNES
# ═══════════════════════════════════════════════════════════

async def _broadcast_prediction(prediction: PredictionOutput):
    """Appelé par le StreamingPipeline après chaque prédiction ML."""
    mid = prediction.motor_id

    # Mettre à jour mémoire
    if mid not in _motor_states:
        _motor_states[mid] = {
            "id": mid, "name": f"Motor {mid}",
            "location": "Production Line", "is_active": True,
        }
    _motor_states[mid].update({
        "status":          prediction.status,
        "health_score":    prediction.health_score,
        "failure_prob":    prediction.failure_probability,
        "rul_days":        prediction.rul_days,
        "last_seen":       prediction.timestamp.isoformat(),
        "last_prediction": prediction,
    })

    # ← Sauvegarder en BD
    try:
        save_prediction_to_db(prediction)
        upsert_machine(mid, status=prediction.status, health_score=prediction.health_score)
    except Exception as e:
        logger.warning(f"BD save error: {e}")

    # Créer alerte si dégradé
    if prediction.status in ("warning", "critical"):
        await _create_alert(prediction)

    # Broadcaster WebSocket
    msg = {
        "type": "prediction_update",
        "data": {
            "motor_id":     mid,
            "status":       prediction.status,
            "health_score": prediction.health_score,
            "failure_prob": prediction.failure_probability,
            "rul_days":     prediction.rul_days,
            "timestamp":    prediction.timestamp.isoformat(),
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
    titles = {"critical": "Panne imminente détectée", "warning": "Dégradation détectée"}
    alert = {
        "id":          str(uuid.uuid4()),
        "device_id":   prediction.motor_id,
        "device_name": _motor_states.get(prediction.motor_id, {}).get("name", prediction.motor_id),
        "severity":    prediction.status,
        "title":       titles.get(prediction.status, "Alerte"),
        "message":     prediction.recommendation,
        "created_at":  datetime.now(timezone.utc).isoformat(),
        "is_read":     False,
    }
    _alerts.insert(0, alert)
    if len(_alerts) > 500:
        _alerts.pop()

    # ← Sauvegarder en BD
    try:
        save_alert_to_db(alert)
    except Exception as e:
        logger.warning(f"alert BD save error: {e}")

    # Broadcaster WebSocket
    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send_json({"type": "alert", "data": alert})
        except Exception:
            dead.add(ws)
    _ws_clients -= dead


def _motor_to_response(state: dict) -> dict:
    return {
        "id":           state.get("id", "?"),
        "name":         state.get("name", "Unknown"),
        "location":     state.get("location", "?"),
        "status":       state.get("status", "healthy"),
        "health_score": state.get("health_score", 100),
        "failure_prob": state.get("failure_prob", 0.0),
        "rul_days":     state.get("rul_days", 365.0),
        "last_seen":    state.get("last_seen", datetime.now(timezone.utc).isoformat()),
        "is_active":    state.get("is_active", True),
        "last_reading": state.get("last_reading"),
    }


def _prediction_to_response(pred: PredictionOutput) -> dict:
    return {
        "device_id":        pred.motor_id,
        "predicted_at":     pred.timestamp.isoformat(),
        "failure_prob":     pred.failure_probability,
        "rul_days":         pred.rul_days,
        "recommendation":   pred.recommendation,
        "anomalies":        pred.anomaly_features,
        "suggested_status": pred.status,
        "health_score":     pred.health_score,
        "confidence":       pred.confidence,
    }


if __name__ == "__main__":
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=False, workers=1)