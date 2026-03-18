"""
src/inference/predictor.py

Moteur de prédiction temps réel.
Reçoit des features (depuis ESP32 ou datasets) → retourne HealthScore + RUL + Status.
Fonctionne identiquement en mode batch (dataset) et streaming (ESP32).
"""

import json
import joblib
import numpy as np
import torch
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from loguru import logger
from datetime import datetime

from ..training.trainer import LSTMPredictor


@dataclass
class PredictionOutput:
    motor_id: str
    timestamp: datetime

    # Scores
    health_score: int           # 0–100
    failure_probability: float  # 0.0–1.0
    rul_days: float             # Remaining Useful Life (jours)

    # Classification
    status: str                 # "healthy" | "warning" | "critical"
    anomaly_score: float        # Score Isolation Forest (plus bas = plus anormal)

    # Détails
    class_probabilities: dict   # {0: 0.8, 1: 0.15, 2: 0.05}
    anomaly_features: list      # features qui ont le plus contribué à l'anomalie
    recommendation: str
    confidence: float           # 0.0–1.0


class PredictiveMaintenancePredictor:
    """
    Charge les modèles entraînés et effectue les prédictions.
    Compatible batch ET streaming (même interface).
    """

    STATUS_THRESHOLDS = {
        "healthy":  {"max_failure_prob": 0.30},
        "warning":  {"max_failure_prob": 0.65},
        "critical": {"min_failure_prob": 0.65},
    }

    RECOMMENDATIONS = {
        "healthy":  "Système nominal. Prochaine maintenance planifiée selon le calendrier.",
        "warning":  "Dégradation détectée. Planifier une inspection dans les {rul} jours.",
        "critical": "Intervention URGENTE requise. Risque de panne dans moins de {rul} jours.",
    }

    def __init__(self, artifacts_dir: str = "models/artifacts", sequence_length: int = 50):
        self.artifacts_dir = Path(artifacts_dir)
        self.sequence_length = sequence_length
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self._load_artifacts()
        self._sequence_buffer: dict = {}   # motor_id → buffer de features pour LSTM

    def _load_artifacts(self):
        """Charge tous les modèles depuis le disque."""
        try:
            self.scaler           = joblib.load(self.artifacts_dir / "scaler.pkl")
            self.isolation_forest = joblib.load(self.artifacts_dir / "isolation_forest.pkl")
            self.random_forest    = joblib.load(self.artifacts_dir / "random_forest.pkl")
            self.feature_cols     = joblib.load(self.artifacts_dir / "feature_cols.pkl")

            # LSTM (optionnel)
            lstm_config_path = self.artifacts_dir / "lstm_config.json"
            lstm_weights_path = self.artifacts_dir / "lstm_final.pt"
            if lstm_config_path.exists() and lstm_weights_path.exists():
                with open(lstm_config_path) as f:
                    cfg = json.load(f)
                self.lstm = LSTMPredictor(**cfg).to(self.device)
                self.lstm.load_state_dict(torch.load(lstm_weights_path, map_location=self.device))
                self.lstm.eval()
            else:
                self.lstm = None
                logger.warning("LSTM weights not found — RUL from RF only")

            logger.info(f"✓ Models loaded from {self.artifacts_dir}")
            logger.info(f"  Features: {len(self.feature_cols)} | LSTM: {'yes' if self.lstm else 'no'}")

        except FileNotFoundError as e:
            raise RuntimeError(f"Models not found at {self.artifacts_dir}. Run training first. ({e})")

    # ── Prédiction unique (streaming ESP32) ───────────────────
    def predict_single(self, features: dict, motor_id: str = "motor_001") -> PredictionOutput:
        """
        Prédit l'état d'un moteur à partir d'un dict de features.
        Appelé en temps réel pour chaque fenêtre de données ESP32.
        """
        # Construire le vecteur de features dans le bon ordre
        X = np.array([[features.get(col, 0.0) for col in self.feature_cols]])

        # Gérer les NaN
        X = np.nan_to_num(X, nan=0.0)

        return self._predict_from_array(X, motor_id, datetime.now())

    # ── Prédiction batch (dataset) ────────────────────────────
    def predict_batch(self, features_df) -> list[PredictionOutput]:
        """
        Prédit l'état pour un DataFrame de features.
        Utilisé pour évaluation sur datasets historiques.
        """
        import pandas as pd
        results = []
        for _, row in features_df.iterrows():
            motor_id  = str(row.get("motor_id", "unknown"))
            timestamp = row.get("timestamp", datetime.now())
            X = np.array([[row.get(col, 0.0) for col in self.feature_cols]])
            X = np.nan_to_num(X, nan=0.0)
            pred = self._predict_from_array(X, motor_id, timestamp)
            results.append(pred)
        return results

    # ── Core prediction ───────────────────────────────────────
    def _predict_from_array(self, X: np.ndarray, motor_id: str, timestamp: datetime) -> PredictionOutput:
        X_scaled = self.scaler.transform(X)

        # ── Isolation Forest ──────────────────────────────────
        if_score     = self.isolation_forest.decision_function(X_scaled)[0]
        if_pred      = self.isolation_forest.predict(X_scaled)[0]  # 1=normal, -1=anomaly
        anomaly_norm = self._normalize_if_score(if_score)

        # ── Random Forest ─────────────────────────────────────
        rf_proba = self.random_forest.predict_proba(X_scaled)[0]
        rf_pred  = int(np.argmax(rf_proba))
        class_proba = {i: float(p) for i, p in enumerate(rf_proba)}

        # ── LSTM (RUL) ────────────────────────────────────────
        rul_days = self._predict_rul_lstm(X_scaled, motor_id)

        # ── Ensemble ──────────────────────────────────────────
        failure_prob = self._compute_failure_probability(rf_proba, anomaly_norm)
        health_score = self._compute_health_score(failure_prob, rul_days)
        status       = self._classify_status(failure_prob)

        # ── Anomaly explanation ───────────────────────────────
        anomaly_features = self._explain_anomaly(X, X_scaled)

        # ── Recommandation ────────────────────────────────────
        recommendation = self.RECOMMENDATIONS[status].format(rul=max(1, int(rul_days)))

        return PredictionOutput(
            motor_id=motor_id,
            timestamp=timestamp,
            health_score=health_score,
            failure_probability=failure_prob,
            rul_days=rul_days,
            status=status,
            anomaly_score=float(if_score),
            class_probabilities=class_proba,
            anomaly_features=anomaly_features,
            recommendation=recommendation,
            confidence=self._compute_confidence(rf_proba),
        )

    def _predict_rul_lstm(self, X_scaled: np.ndarray, motor_id: str) -> float:
        """Utilise le buffer de séquences pour la prédiction LSTM."""
        if self.lstm is None:
            # Fallback : estimer le RUL depuis la proba RF
            return self._rul_from_rf_fallback()

        # Mettre à jour le buffer de séquences
        if motor_id not in self._sequence_buffer:
            self._sequence_buffer[motor_id] = []

        self._sequence_buffer[motor_id].append(X_scaled[0])

        # Garder seulement les sequence_length dernières entrées
        if len(self._sequence_buffer[motor_id]) > self.sequence_length:
            self._sequence_buffer[motor_id].pop(0)

        buf = self._sequence_buffer[motor_id]
        if len(buf) < self.sequence_length:
            # Pas assez d'historique → compléter par padding
            padding = [buf[0]] * (self.sequence_length - len(buf))
            seq = np.array(padding + buf)
        else:
            seq = np.array(buf)

        with torch.no_grad():
            seq_t = torch.FloatTensor(seq).unsqueeze(0).to(self.device)
            rul = float(self.lstm(seq_t).item())

        return max(0.0, rul)

    def _rul_from_rf_fallback(self) -> float:
        """Estimation RUL quand LSTM indisponible."""
        return 365.0   # placeholder

    def _compute_failure_probability(self, rf_proba: np.ndarray, anomaly_score: float) -> float:
        """Combine RF proba et Isolation Forest pour un score de risque robuste."""
        n_classes = len(rf_proba)
        if n_classes == 1:
            rf_failure = 0.0
        elif n_classes == 2:
            rf_failure = float(rf_proba[1])
        else:
            # Classes 1=warning, 2=critical → pondération
            rf_failure = float(rf_proba[1] * 0.5 + rf_proba[2] * 1.0)
            rf_failure = min(1.0, rf_failure)

        # Ensemble : 60% RF, 40% Isolation Forest
        failure_prob = 0.60 * rf_failure + 0.40 * anomaly_score
        return float(np.clip(failure_prob, 0.0, 1.0))

    @staticmethod
    def _compute_health_score(failure_prob: float, rul_days: float) -> int:
        """HealthScore 0–100 : inverse de la probabilité de panne, modulé par RUL."""
        base_score = (1 - failure_prob) * 100
        # Bonus/malus selon RUL
        if rul_days > 90:
            rul_factor = 1.0
        elif rul_days > 30:
            rul_factor = 0.9
        elif rul_days > 7:
            rul_factor = 0.75
        else:
            rul_factor = 0.5
        return max(0, min(100, int(base_score * rul_factor)))

    @staticmethod
    def _classify_status(failure_prob: float) -> str:
        if failure_prob < 0.30:
            return "healthy"
        elif failure_prob < 0.65:
            return "warning"
        else:
            return "critical"

    @staticmethod
    def _normalize_if_score(score: float) -> float:
        """Normalise le score IF (decision_function) vers [0, 1] où 1 = très anormal."""
        # Scores typiques IF: négatifs = anomalies, positifs = normaux
        normalized = 1 / (1 + np.exp(5 * score))
        return float(np.clip(normalized, 0.0, 1.0))

    def _explain_anomaly(self, X_raw: np.ndarray, X_scaled: np.ndarray) -> list[str]:
        """Identifie les features qui contribuent le plus à l'anomalie (top 5)."""
        if self.random_forest is None:
            return []
        importances = self.random_forest.feature_importances_
        anomaly_contributions = np.abs(X_scaled[0]) * importances
        top_idx = np.argsort(anomaly_contributions)[::-1][:5]
        return [
            f"{self.feature_cols[i]}: {X_raw[0, i]:.3f}"
            for i in top_idx
        ]

    @staticmethod
    def _compute_confidence(rf_proba: np.ndarray) -> float:
        """Confiance = écart entre la meilleure classe et la 2e meilleure."""
        sorted_proba = np.sort(rf_proba)[::-1]
        if len(sorted_proba) >= 2:
            return float(sorted_proba[0] - sorted_proba[1])
        return float(sorted_proba[0])
