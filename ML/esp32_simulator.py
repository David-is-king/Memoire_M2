"""
src/simulator/esp32_simulator.py

Simule l'ESP32 en rejouant les datasets comme si c'était
des capteurs réels en temps réel (MQTT + WebSocket).

Quand l'ESP32 sera prêt : même interface, on change juste la source.
─────────────────────────────────────────────────────────────────────
MODE MAINTENANT  : Dataset CSV  → Simulator → Pipeline → API
MODE PLUS TARD   : ESP32 WiFi   → MQTT/WS   → Pipeline → API
                                    (même code ici)
"""

import asyncio
import json
import time
import numpy as np
import pandas as pd
import websockets
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Optional
from loguru import logger
from dataclasses import dataclass, asdict

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False


@dataclass
class SensorReading:
    """Lecture capteur — identique à ce qu'enverrait l'ESP32."""
    motor_id: str
    timestamp: str          # ISO 8601
    temperature: float      # °C
    vibration_x: float      # g
    vibration_y: float      # g
    vibration_z: float      # g
    current: float          # A
    voltage: float          # V
    acoustic_db: float      # dB
    # Métadonnées simulateur
    source: str = "simulator"
    sequence_number: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    def to_dict(self) -> dict:
        return asdict(self)


class ESP32Simulator:
    """
    Rejoue les données d'un dataset à la vitesse choisie.
    Publie via WebSocket ET/OU MQTT (même protocole que l'ESP32 réel).
    """

    def __init__(
        self,
        data: pd.DataFrame,
        speedup: float = 100.0,     # 100x = 100 secondes de données par seconde réelle
        ws_port: int = 8765,
        mqtt_broker: str = "localhost",
        mqtt_port: int = 1883,
        mqtt_topic_prefix: str = "sensors/motor",
        noise_factor: float = 0.01,   # bruit réaliste ajouté
    ):
        self.data = data.sort_values(["motor_id", "timestamp"]).reset_index(drop=True)
        self.speedup = speedup
        self.ws_port = ws_port
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.mqtt_topic_prefix = mqtt_topic_prefix
        self.noise_factor = noise_factor

        self._ws_clients: set = set()
        self._running = False
        self._seq_counter: dict = {}
        self._mqtt_client: Optional[object] = None

        logger.info(f"ESP32 Simulator initialized:")
        logger.info(f"  Motors: {self.data['motor_id'].nunique()}")
        logger.info(f"  Samples: {len(self.data):,}")
        logger.info(f"  Speedup: {speedup}x")

    # ── Main entry point ──────────────────────────────────────
    async def run(self, mode: str = "websocket"):
        """
        mode: 'websocket' | 'mqtt' | 'both' | 'callback'
        """
        self._running = True

        if mode in ("mqtt", "both") and MQTT_AVAILABLE:
            self._connect_mqtt()

        if mode in ("websocket", "both"):
            ws_server = await websockets.serve(
                self._ws_handler,
                "0.0.0.0",
                self.ws_port,
                ping_interval=20,
            )
            logger.info(f"WebSocket server started on ws://localhost:{self.ws_port}")

        logger.info(f"Simulator running in '{mode}' mode...")
        await self._stream_data(mode)

    async def stream_to_callback(self, callback) -> None:
        """
        Mode callback : pour intégration directe avec le pipeline.
        await simulator.stream_to_callback(pipeline.process)
        """
        self._running = True
        async for reading in self._generate_readings():
            await callback(reading)

    # ── Data streaming ────────────────────────────────────────
    async def _stream_data(self, mode: str):
        """Lit le dataset et publie les lectures au rythme configuré."""
        motors = self.data["motor_id"].unique()
        motor_dfs = {m: self.data[self.data["motor_id"] == m].reset_index(drop=True) for m in motors}
        motor_indices = {m: 0 for m in motors}

        base_time = datetime.now(timezone.utc)
        total_sent = 0

        while self._running:
            batch_readings = []

            for motor_id in motors:
                df = motor_dfs[motor_id]
                idx = motor_indices[motor_id]

                if idx >= len(df):
                    # Boucle infinie : recommencer le dataset
                    motor_indices[motor_id] = 0
                    idx = 0
                    logger.debug(f"  {motor_id}: dataset loop restart")

                row = df.iloc[idx]
                reading = self._row_to_reading(row, motor_id)
                batch_readings.append(reading)
                motor_indices[motor_id] = idx + 1

            # Publier toutes les lectures
            for reading in batch_readings:
                await self._publish(reading, mode)
                total_sent += 1

            if total_sent % 1000 == 0:
                logger.info(f"  Simulator: {total_sent:,} readings sent")

            # Contrôle de la vitesse
            await asyncio.sleep(1.0 / self.speedup)

    async def _generate_readings(self) -> AsyncIterator[SensorReading]:
        """Générateur async de lectures (pour mode callback)."""
        motors = self.data["motor_id"].unique()
        motor_dfs = {m: self.data[self.data["motor_id"] == m].reset_index(drop=True) for m in motors}
        indices = {m: 0 for m in motors}

        while self._running:
            for motor_id in motors:
                df = motor_dfs[motor_id]
                idx = indices[motor_id] % len(df)
                row = df.iloc[idx]
                yield self._row_to_reading(row, motor_id)
                indices[motor_id] += 1
            await asyncio.sleep(1.0 / self.speedup)

    def _row_to_reading(self, row: pd.Series, motor_id: str) -> SensorReading:
        """Convertit une ligne du dataset en SensorReading avec bruit réaliste."""
        seq = self._seq_counter.get(motor_id, 0) + 1
        self._seq_counter[motor_id] = seq

        def add_noise(val: float, scale: float = 1.0) -> float:
            return float(val + np.random.normal(0, abs(val) * self.noise_factor * scale + 1e-6))

        return SensorReading(
            motor_id=motor_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            temperature=round(add_noise(float(row.get("temperature", 45.0))), 2),
            vibration_x=round(add_noise(float(row.get("vibration_x", 0.1))), 4),
            vibration_y=round(add_noise(float(row.get("vibration_y", 0.08))), 4),
            vibration_z=round(add_noise(float(row.get("vibration_z", 0.05))), 4),
            current=round(add_noise(float(row.get("current", 10.0))), 3),
            voltage=round(add_noise(float(row.get("voltage", 220.0)), 0.1), 2),
            acoustic_db=round(add_noise(float(row.get("acoustic_db", 65.0))), 1),
            source="simulator",
            sequence_number=seq,
        )

    # ── WebSocket ─────────────────────────────────────────────
    async def _ws_handler(self, websocket, path=None):
        self._ws_clients.add(websocket)
        logger.info(f"  WS client connected: {websocket.remote_address}")
        try:
            await websocket.wait_closed()
        finally:
            self._ws_clients.discard(websocket)

    async def _publish_ws(self, reading: SensorReading):
        if not self._ws_clients:
            return
        msg = reading.to_json()
        dead = set()
        for ws in self._ws_clients:
            try:
                await ws.send(msg)
            except websockets.ConnectionClosed:
                dead.add(ws)
        self._ws_clients -= dead

    # ── MQTT ──────────────────────────────────────────────────
    def _connect_mqtt(self):
        if not MQTT_AVAILABLE:
            return
        self._mqtt_client = mqtt.Client()
        try:
            self._mqtt_client.connect(self.mqtt_broker, self.mqtt_port, keepalive=60)
            self._mqtt_client.loop_start()
            logger.info(f"  MQTT connected: {self.mqtt_broker}:{self.mqtt_port}")
        except Exception as e:
            logger.warning(f"  MQTT connection failed: {e}")
            self._mqtt_client = None

    def _publish_mqtt(self, reading: SensorReading):
        if self._mqtt_client is None:
            return
        topic = f"{self.mqtt_topic_prefix}/{reading.motor_id}/readings"
        self._mqtt_client.publish(topic, reading.to_json(), qos=0)

    async def _publish(self, reading: SensorReading, mode: str):
        if mode in ("websocket", "both"):
            await self._publish_ws(reading)
        if mode in ("mqtt", "both"):
            self._publish_mqtt(reading)

    def stop(self):
        self._running = False
        if self._mqtt_client:
            self._mqtt_client.loop_stop()
            self._mqtt_client.disconnect()


# ── Streaming Pipeline (connecte Simulator → Pipeline → Predictor) ────

class StreamingPipeline:
    """
    Orchestrateur temps réel :
    Simulator/ESP32 → CleaningPipeline (L3) → Predictor → API callback

    Ce même code fonctionnera avec le vrai ESP32 via MQTT.
    """

    def __init__(self, predictor, cleaning_pipeline, buffer_size: int = 512, on_prediction=None):
        from collections import deque
        self.predictor = predictor
        self.cleaner   = cleaning_pipeline
        self.buffer_size = buffer_size
        self.on_prediction = on_prediction  # callback async vers l'API

        self._buffers: dict = {}   # motor_id → deque de SensorReading

    async def ingest(self, reading: SensorReading):
        """Reçoit une lecture, remplit le buffer, lance la prédiction si prêt."""
        mid = reading.motor_id

        if mid not in self._buffers:
            from collections import deque
            self._buffers[mid] = deque(maxlen=self.buffer_size)

        self._buffers[mid].append(reading)

        # Déclencher la prédiction quand on a assez de données
        if len(self._buffers[mid]) >= self.buffer_size:
            await self._run_prediction(mid)

    async def _run_prediction(self, motor_id: str):
        """Nettoie la fenêtre courante et génère une prédiction."""
        readings = list(self._buffers[motor_id])

        # Convertir en DataFrame
        df = pd.DataFrame([r.to_dict() for r in readings])
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        # Nettoyage L1 + L2 + L3 sur la fenêtre
        features_dict = self.cleaner.run_single_window(df)

        # Prédiction
        prediction = self.predictor.predict_single(features_dict, motor_id)

        logger.info(
            f"  [{motor_id}] {prediction.status.upper():8s} | "
            f"Health: {prediction.health_score:3d}% | "
            f"RUL: {prediction.rul_days:.0f}d | "
            f"FailProb: {prediction.failure_probability:.1%}"
        )

        # Callback vers l'API (WebSocket aux clients Flutter)
        if self.on_prediction:
            await self.on_prediction(prediction)

        # Vider la moitié du buffer (fenêtre glissante avec overlap 50%)
        keep = self.buffer_size // 2
        buffer_list = list(self._buffers[motor_id])
        self._buffers[motor_id].clear()
        for r in buffer_list[-keep:]:
            self._buffers[motor_id].append(r)
