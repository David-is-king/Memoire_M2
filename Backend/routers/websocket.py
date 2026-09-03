"""Routes WebSocket pour le temps reel Flutter."""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder

from Backend.database import get_db_connection
from Backend.repositories.alerts import AlertRepository
from Backend.repositories.motors import MotorRepository


router = APIRouter(tags=["WebSocket"])


async def _send_json_safe(websocket: WebSocket, payload: dict) -> None:
    """Envoie un message JSON au client WebSocket."""
    # jsonable_encoder transforme datetime/UUID en chaines JSON valides.
    await websocket.send_json(jsonable_encoder(payload))


@router.websocket("/ws/all")
async def websocket_all(websocket: WebSocket) -> None:
    """Flux global du dashboard : statuts moteurs + derniere alerte non lue."""
    await websocket.accept()

    try:
        while True:
            with get_db_connection() as conn:
                statuses = MotorRepository.list_statuses(conn)
                latest_alert = AlertRepository.get_latest_unread(conn)

            await _send_json_safe(websocket, {"type": "motor_status_update", "data": statuses})

            if latest_alert:
                await _send_json_safe(websocket, {"type": "alert", "data": dict(latest_alert)})

            await asyncio.sleep(5)
    except WebSocketDisconnect:
        return


@router.websocket("/ws/motors/{motor_id}")
async def websocket_motor(websocket: WebSocket, motor_id: str) -> None:
    """Flux temps reel d'un moteur : envoie sa derniere mesure capteur."""
    await websocket.accept()

    try:
        while True:
            with get_db_connection() as conn:
                reading = MotorRepository.get_latest_reading(conn, motor_id)

            if reading:
                await _send_json_safe(websocket, {"type": "sensor_reading", "data": dict(reading)})

            await asyncio.sleep(3)
    except WebSocketDisconnect:
        return
