"""Routes moteurs et historique capteur."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from Backend.controllers.motors import MotorController
from Backend.database import get_db
from Backend.schemas.motors import MotorDevice, SensorReading


router = APIRouter(prefix="/motors", tags=["Motors"])


@router.get("", response_model=list[MotorDevice])
def list_motors(conn: Any = Depends(get_db)) -> list[dict]:
    """Endpoint utilise par le dashboard Flutter."""
    return MotorController.list_motors(conn)


@router.get("/{motor_id}", response_model=MotorDevice)
def get_motor(motor_id: str, conn: Any = Depends(get_db)) -> dict:
    """Endpoint utilise par l'ecran detail moteur."""
    return MotorController.get_motor(conn, motor_id)


@router.get("/{motor_id}/readings", response_model=list[SensorReading])
def get_motor_readings(
    motor_id: str,
    since: datetime | None = Query(default=None),
    conn: Any = Depends(get_db),
) -> list[dict]:
    """Retourne les mesures capteurs depuis la date `since` envoyee par Flutter."""
    return MotorController.get_readings(conn, motor_id, since)
