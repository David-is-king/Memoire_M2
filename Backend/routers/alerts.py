"""Routes alertes."""

from fastapi import APIRouter, Depends, Query
from typing import Any

from Backend.controllers.alerts import AlertController
from Backend.database import get_db
from Backend.schemas.alerts import AlertModel, MarkReadResponse


router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("", response_model=list[AlertModel])
def list_alerts(
    unread: bool = Query(default=False),
    conn: Any = Depends(get_db),
) -> list[dict]:
    """Liste les alertes pour app_flutter/lib/alerts_screen.dart."""
    return AlertController.list_alerts(conn, unread_only=unread)


@router.patch("/{alert_id}/read", response_model=MarkReadResponse)
def mark_alert_read(alert_id: str, conn: Any = Depends(get_db)) -> dict:
    """Marque une alerte comme lue quand l'utilisateur la consulte."""
    return AlertController.mark_read(conn, alert_id)


@router.post("/mark-all-read", response_model=MarkReadResponse)
def mark_all_alerts_read(conn: Any = Depends(get_db)) -> dict:
    """Marque toutes les alertes comme lues."""
    return AlertController.mark_all_read(conn)
