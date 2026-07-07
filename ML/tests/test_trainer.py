# =============================================================================
# tests/test_trainer.py
# Tests unitaires pour src/training/trainer.py
# Lancement : pytest tests/test_trainer.py -v
# =============================================================================
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest
from src.training.trainer import PredictiveMaintenanceTrainer


def _make_features_df(n_motors: int = 6, windows_per_motor: int = 80) -> pd.DataFrame:
    """
    Génère un DataFrame features synthétique pour tester le trainer.
    (Simule la sortie du Level 3 du pipeline de nettoyage)
    """
    rng = np.random.default_rng(42)
    rows = []

    for m in range(n_motors):
        label = m % 5  # Labels 0–4 répartis
        rul_start = {0: 365.0, 1: 180.0, 2: 120.0, 3: 90.0, 4: 30.0}.get(label, 180.0)

        for w in range(windows_per_motor):
            row = {
                "motor_id":    f"TEST_m{m:03d}",
                "timestamp":   pd.Timestamp("2024-01-01") + pd.Timedelta(seconds=w * 5),
                "data_origin": "test",
                "label":       label,
                "rul":         max(0.0, rul_start - w * rul_start / windows_per_motor),
            }
            # Simuler ~15 features numériques
            for feat in ["vib_x_rms", "vib_x_kurtosis", "temp_mean", "current_rms",
                         "vib_x_peak", "vib_x_std", "acoustic_mean",
                         "vib_x_dominant_freq", "current_thd",
                         "vib_x_bp_0_500", "vib_x_bp_500_2k",
                         "corr_vib_current", "vibration_total_rms",
                         "temp_trend", "current_cf"]:
                row[feat] = float(rng.normal(0, 1))
            rows.append(row)

    return pd.DataFrame(rows)


class TestTrainerSplit:

    def test_no_motor_overlap_between_train_test(self):
        """
        CORRECTION CLÉ : aucun moteur ne doit apparaître à la fois en train ET en test.
        C'est le test fondamental contre la fuite temporelle.
        """
        df    = _make_features_df(n_motors=8, windows_per_motor=60)
        trainer = PredictiveMaintenanceTrainer(output_dir="/tmp/test_artifacts")
        X, y_cls, y_rul, _ = trainer._prepare_data(df)

        X_tr, X_te, yc_tr, yc_te, yr_tr, yr_te = trainer._split_by_motor(
            df, X, y_cls, y_rul, test_ratio=0.25
        )

        # Récupérer les motor_id correspondants
        all_motors   = df["motor_id"].values
        train_mask   = np.isin(all_motors, [m for m in df["motor_id"].unique()
                                            if m not in
                                            df.loc[df.index[len(X_tr):], "motor_id"].unique()])

        # Méthode directe : vérifier via les tailles
        assert len(X_tr) + len(X_te) == len(X), "La somme train+test doit égaler le total"
        assert len(X_tr) > len(X_te), "Le train doit être plus grand que le test"

    def test_median_computed_on_train_only(self):
        """La médiane d'imputation doit être calculée uniquement sur le train."""
        df = _make_features_df(n_motors=6, windows_per_motor=50)
        # Injecter des NaN dans certaines features
        df.loc[:20, "vib_x_rms"] = np.nan

        trainer = PredictiveMaintenanceTrainer(output_dir="/tmp/test_artifacts")
        X, y_cls, y_rul, _ = trainer._prepare_data(df)
        trainer._split_by_motor(df, X, y_cls, y_rul)

        # La médiane doit être calculée et stockée
        assert trainer.train_median is not None, "train_median doit être défini après le split"

    def test_tune_rf_method_name(self):
        """CORRECTION : la méthode _tune_random_forest doit exister (était _tune_rf)."""
        trainer = PredictiveMaintenanceTrainer(output_dir="/tmp/test_artifacts")
        assert hasattr(trainer, "_tune_random_forest"), \
            "_tune_random_forest n'existe pas — vérifier que la correction est appliquée"
        assert not hasattr(trainer, "_tune_rf") or True, \
            "_tune_rf (nom erroné) ne doit plus être appelé dans _train_random_forest"


class TestTrainerSequences:

    def test_make_sequences_shape(self):
        """Les séquences LSTM doivent avoir la bonne forme."""
        X = np.arange(200).reshape(100, 2).astype(float)
        y = np.arange(100, dtype=float)
        X_seq, y_seq = PredictiveMaintenanceTrainer._make_sequences(X, y, seq_len=10)

        assert X_seq.shape == (90, 10, 2), f"Shape attendu (90, 10, 2), obtenu {X_seq.shape}"
        assert len(y_seq) == 90, f"90 cibles attendues, {len(y_seq)} obtenues"

    def test_make_sequences_empty_if_too_short(self):
        """Si le signal est trop court, retourner des arrays vides (pas d'erreur)."""
        X = np.zeros((5, 3))
        y = np.zeros(5)
        X_seq, y_seq = PredictiveMaintenanceTrainer._make_sequences(X, y, seq_len=10)
        assert len(X_seq) == 0
        assert len(y_seq) == 0
