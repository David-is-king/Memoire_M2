# =============================================================================
# src/inference/predictor.py
#
# Moteur d'inférence temps réel.
# Reçoit des features pré-calculées (issues du pipeline L3 ou du simulateur ESP32)
# et retourne une prédiction complète :
#   - Score de santé (0–100)
#   - Probabilité de panne (0.0–1.0)
#   - RUL estimé par le LSTM (jours restants)
#   - Statut : "healthy" / "warning" / "critical"
#   - Recommandation textuelle (pour l'affichage Flutter)
#   - Top-3 features contributrices (pour l'explication de l'anomalie)
#
# IMPORTANT : ce fichier charge exactement les mêmes fichiers que trainer.py sauvegarde.
#   trainer.py  → sauvegarde : scaler.pkl, isolation_forest.pkl, random_forest.pkl,
#                              feature_cols.pkl, lstm_final.pt, lstm_config.json,
#                              train_median.npy
#   predictor.py → charge    : exactement les mêmes noms
# =============================================================================

import json
import joblib
import numpy as np
import torch
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from loguru import logger
from datetime import datetime

# Import de l'architecture LSTM depuis le trainer (doit correspondre exactement)
from ..training.trainer import LSTMPredictor


# =============================================================================
# STRUCTURE DE SORTIE — Résultat d'une prédiction
# =============================================================================

@dataclass
class PredictionOutput:
    """
    Résultat complet d'une prédiction pour UN moteur à UN instant donné.
    Tous les champs sont envoyés à l'application Flutter via WebSocket.
    """
    motor_id:            str    # Identifiant unique du moteur
    timestamp:           datetime  # Moment de la prédiction
    health_score:        int    # Score de santé 0–100 (100 = parfait, 0 = critique)
    failure_probability: float  # Probabilité de panne imminente (0.0–1.0)
    rul_days:            float  # Remaining Useful Life prédit par le LSTM (jours)
    status:              str    # "healthy" | "warning" | "critical"
    anomaly_score:       float  # Score d'anomalie de l'Isolation Forest (0.0–1.0)
    class_probabilities: dict   # {0: prob_normal, 1: prob_imbalance, ..., 4: prob_bearing}
    anomaly_features:    list   # Top-3 features les plus contributives à l'anomalie
    recommendation:      str    # Message de maintenance pour l'opérateur
    confidence:          float  # Confiance de la prédiction (prob max du RF)


# =============================================================================
# PRÉDICTEUR PRINCIPAL
# =============================================================================

class PredictiveMaintenancePredictor:
    """
    Charge les modèles entraînés et effectue les prédictions.
    Utilisé en mode batch (évaluation) et streaming (temps réel ESP32).
    """

    # Messages de recommandation par classe de défaut
    RECOMMENDATIONS = {
        0: "✅ Moteur en parfait état. Aucune action requise.",
        1: "⚠️ Déséquilibre de masse détecté. Planifier un rééquilibrage du rotor.",
        2: "⚠️ Désalignement horizontal détecté. Vérifier les fixations et le châssis.",
        3: "⚠️ Désalignement vertical détecté. Ajuster les cales du moteur.",
        4: "🚨 Défaut de roulement imminent ! Remplacement prioritaire requis.",
    }

    def __init__(self, artifacts_dir: str = "models/artifacts"):
        self.artifacts_dir = Path(artifacts_dir)

        # Artefacts (remplis par load_models)
        self.scaler:           Optional[object]       = None
        self.isolation_forest: Optional[object]       = None
        self.random_forest:    Optional[object]       = None
        self.lstm:             Optional[LSTMPredictor] = None
        self.feature_cols:     list                   = []
        self.train_median:     Optional[np.ndarray]   = None

        # Device PyTorch (CPU si pas de GPU)
        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else
            "mps"  if torch.backends.mps.is_available() else "cpu"
        )

        self.load_models()

    def load_models(self):
        """
        Charge tous les artefacts sauvegardés par trainer.py.
        
        ╔══════════════════════════════════════════════════════════════════╗
        ║  CORRECTION : noms de fichiers synchronisés avec trainer.py     ║
        ║                                                                  ║
        ║  AVANT (buggé)  : scaler.joblib, isolation_forest.joblib,       ║
        ║                   random_forest.joblib, feature_cols.json       ║
        ║                   (json.load pour feature_cols — incompatible)  ║
        ║                                                                  ║
        ║  APRÈS (corrigé): scaler.pkl, isolation_forest.pkl,             ║
        ║                   random_forest.pkl, feature_cols.pkl           ║
        ║                   (joblib.load pour tous — cohérent)            ║
        ╚══════════════════════════════════════════════════════════════════╝
        """
        try:
            # ── Modèles Scikit-Learn ──────────────────────────────────────────
            self.scaler           = joblib.load(self.artifacts_dir / "scaler.pkl")
            self.isolation_forest = joblib.load(self.artifacts_dir / "isolation_forest.pkl")
            self.random_forest    = joblib.load(self.artifacts_dir / "random_forest.pkl")

            # ── Liste ordonnée des features ────────────────────────────────────
            # Indispensable : les features doivent être dans le même ordre qu'à l'entraînement
            self.feature_cols = joblib.load(self.artifacts_dir / "feature_cols.pkl")  # ← CORRIGÉ

            # ── Médiane du train pour imputer les NaN à l'inférence ───────────
            median_path = self.artifacts_dir / "train_median.npy"
            if median_path.exists():
                self.train_median = np.load(str(median_path))

            logger.info("✓ Modèles sklearn chargés (scaler, IF, RF, feature_cols)")

        except Exception as e:
            logger.error(f"✗ Erreur chargement modèles sklearn : {e}")
            logger.error("  → Lancer d'abord l'entraînement : python scripts/run_pipeline.py --mode train")
            return

        # ── Chargement du LSTM ────────────────────────────────────────────────
        # CORRECTION : le LSTM est maintenant chargé ET utilisé pour le RUL
        # (dans la version bugguée, le LSTM était ignoré à l'inférence)
        lstm_config_path = self.artifacts_dir / "lstm_config.json"
        lstm_weights_path = self.artifacts_dir / "lstm_final.pt"

        if lstm_config_path.exists() and lstm_weights_path.exists():
            try:
                with open(lstm_config_path, "r") as f:
                    lstm_config = json.load(f)

                # Reconstruction de l'architecture avec les mêmes hyperparamètres
                self.lstm = LSTMPredictor(
                    input_size  = lstm_config["input_size"],
                    hidden_size = lstm_config["hidden_size"],
                    num_layers  = lstm_config["num_layers"],
                ).to(self.device)

                # Chargement des poids sauvegardés
                self.lstm.load_state_dict(
                    torch.load(lstm_weights_path, map_location=self.device)
                )
                self.lstm.eval()  # Mode évaluation (désactive le dropout)
                logger.info("✓ LSTM chargé et prêt pour la prédiction RUL")

            except Exception as e:
                logger.warning(f"⚠ LSTM non chargé : {e} → RUL calculé heuristiquement")
                self.lstm = None
        else:
            logger.warning("⚠ Fichiers LSTM absents → RUL calculé heuristiquement")
            self.lstm = None

    def predict_single(self, features_dict: dict, motor_id: str) -> PredictionOutput:
        """
        Effectue une prédiction pour UN moteur à partir de ses features.
        
        Args:
            features_dict: Dictionnaire {nom_feature: valeur} issu du pipeline L3
            motor_id:      Identifiant du moteur
        
        Returns:
            PredictionOutput complet
        """
        if self.scaler is None or self.random_forest is None:
            raise RuntimeError(
                "Modèles non chargés. Entraîner d'abord avec run_pipeline.py --mode train"
            )

        # ── Construction du vecteur de features (ordre exact de l'entraînement) ─
        # Les features absentes reçoivent la valeur médiane du train (ou 0.0 si absente)
        X_raw = np.array([[
            features_dict.get(col, float(self.train_median[i]) if self.train_median is not None else 0.0)
            for i, col in enumerate(self.feature_cols)
        ]])

        # Normalisation avec le même scaler qu'à l'entraînement
        X_scaled = self.scaler.transform(X_raw)

        # ── 1. Score d'anomalie (Isolation Forest) ────────────────────────────
        # decision_function : valeur positive = normal, négative = anomalie
        # On inverse et normalise avec une sigmoïde pour obtenir [0, 1]
        if_raw        = self.isolation_forest.decision_function(X_scaled)[0]
        anomaly_score = self._normalize_if_score(if_raw)

        # ── 2. Classification multi-classes (Random Forest) ───────────────────
        rf_probs      = self.random_forest.predict_proba(X_scaled)[0]   # Probabilités par classe
        class_probs   = {int(i): float(p) for i, p in enumerate(rf_probs)}
        prob_failure  = float(1.0 - class_probs.get(0, 0.0))            # 1 - prob(Normal)
        pred_label    = int(np.argmax(rf_probs))                         # Classe la plus probable

        # ── 3. Prédiction RUL (LSTM) ──────────────────────────────────────────
        # CORRECTION : on utilise vraiment le LSTM s'il est chargé
        # En mode streaming : on n'a qu'un seul vecteur → séquence de longueur 1
        rul_days = self._predict_rul(X_scaled, features_dict)

        # ── 4. Score de santé et statut ───────────────────────────────────────
        health_score = int(max(0, min(100, (1.0 - prob_failure) * 100)))
        status       = self._classify_status(prob_failure, pred_label)

        # ── 5. Recommandation ─────────────────────────────────────────────────
        reco = self.RECOMMENDATIONS.get(pred_label, "Inspection manuelle recommandée.")

        # ── 6. Explication de l'anomalie (Top-3 features) ────────────────────
        top_features = self._explain_anomaly(X_scaled)

        return PredictionOutput(
            motor_id            = motor_id,
            timestamp           = datetime.now(),
            health_score        = health_score,
            failure_probability = prob_failure,
            rul_days            = rul_days,
            status              = status,
            anomaly_score       = anomaly_score,
            class_probabilities = class_probs,
            anomaly_features    = top_features,
            recommendation      = reco,
            confidence          = float(np.max(rf_probs)),
        )

    def predict_batch(self, features_df: "pd.DataFrame") -> list:
        """
        Prédit pour un batch de fenêtres (une liste de PredictionOutput).
        Utile pour l'évaluation ou le traitement de fichiers historiques.
        """
        results = []
        for _, row in features_df.iterrows():
            motor_id = str(row.get("motor_id", "unknown"))
            features_dict = row.to_dict()
            try:
                pred = self.predict_single(features_dict, motor_id)
                results.append(pred)
            except Exception as e:
                logger.error(f"Prédiction échouée pour {motor_id} : {e}")
        return results

    def _predict_rul(self, X_scaled: np.ndarray, features_dict: dict) -> float:
        """
        Prédit le RUL avec le LSTM si disponible.
        
        En mode streaming, on n'a qu'une fenêtre → séquence de longueur 1.
        En mode batch, on pourrait fournir des séquences plus longues pour
        de meilleures prédictions (à implémenter côté StreamingPipeline avec buffer).
        
        Fallback si LSTM absent : heuristique basée sur la probabilité de panne.
        """
        if self.lstm is not None:
            # Séquence de longueur 1 : (1, 1, n_features)
            x_seq = torch.FloatTensor(X_scaled).unsqueeze(0).to(self.device)
            with torch.no_grad():
                rul = self.lstm(x_seq).cpu().item()
            return float(max(0.0, rul))

        # Fallback heuristique : RUL ∝ (1 - prob_failure)
        # Utilise aussi le RUL du dataset si présent dans les features
        rul_from_dataset = features_dict.get("rul", None)
        prob_failure     = 1.0 - float(
            self.random_forest.predict_proba(X_scaled)[0][0]
        ) if self.random_forest is not None else 0.0

        if rul_from_dataset is not None and rul_from_dataset > 0:
            return float(rul_from_dataset)
        return float(np.clip(365.0 * (1.0 - prob_failure), 0, 365))

    @staticmethod
    def _classify_status(failure_prob: float, pred_label: int) -> str:
        """
        Détermine le statut du moteur selon la probabilité de panne et la classe prédite.
        
        Seuils :
          healthy  : prob_failure < 0.25 ET label = Normal
          warning  : prob_failure < 0.60 OU défaut mineur (labels 1, 2, 3)
          critical : prob_failure ≥ 0.60 OU défaut roulement (label 4)
        """
        if failure_prob < 0.25 and pred_label == 0:
            return "healthy"
        elif failure_prob < 0.60 or pred_label in (1, 2, 3):
            return "warning"
        else:
            return "critical"

    @staticmethod
    def _normalize_if_score(raw_score: float) -> float:
        """
        Normalise le score brut de l'Isolation Forest avec une sigmoïde.
        decision_function() : valeurs négatives = anomalies, positives = normaux
        On inverse (×5) et applique σ pour obtenir 0 (normal) → 1 (anomalie).
        """
        return float(1.0 / (1.0 + np.exp(5.0 * raw_score)))

    def _explain_anomaly(self, X_scaled: np.ndarray) -> list:
        """
        Identifie les 3 features qui contribuent le plus à l'anomalie.
        
        Méthode : produit |valeur normalisée| × importance_RF
        Une feature avec une valeur extrême ET une haute importance RF
        sera identifiée comme principale cause de l'anomalie.
        """
        if self.random_forest is None or len(self.feature_cols) == 0:
            return []
        importances   = self.random_forest.feature_importances_
        contributions = np.abs(X_scaled[0]) * importances
        top_idx       = np.argsort(contributions)[::-1][:3]
        return [self.feature_cols[i] for i in top_idx if i < len(self.feature_cols)]
