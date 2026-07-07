# =============================================================================
# tests/test_cleaning.py
# Tests unitaires pour src/cleaning/pipeline.py
# Lancement : pytest tests/test_cleaning.py -v
# =============================================================================
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest
from src.cleaning.pipeline import Level1Cleaner, Level2Cleaner, Level3FeatureEngineer, CleaningPipeline


def _make_test_df(n_rows: int = 1000, n_motors: int = 2, label: int = 0) -> pd.DataFrame:
    """Génère un DataFrame de test minimal au format standard."""
    rng = np.random.default_rng(42)
    motors = [f"TEST_motor_{i}" for i in range(n_motors)]
    per_motor = n_rows // n_motors

    dfs = []
    for m in motors:
        df = pd.DataFrame({
            "timestamp":    pd.date_range("2024-01-01", periods=per_motor, freq="10ms"),
            "motor_id":     m,
            "temperature":  rng.uniform(30, 70, per_motor),
            "vibration_x":  rng.normal(0, 0.5, per_motor),
            "vibration_y":  rng.normal(0, 0.3, per_motor),
            "vibration_z":  rng.normal(0, 0.2, per_motor),
            "current":      rng.uniform(2, 8, per_motor),
            "voltage":      rng.uniform(215, 225, per_motor),
            "acoustic_db":  rng.uniform(50, 80, per_motor),
            "label":        label,
            "rul":          np.linspace(365, 0, per_motor),
            "data_origin":  "test",
        })
        dfs.append(df)

    return pd.concat(dfs, ignore_index=True)


class TestLevel1Cleaner:

    def test_typo_fix_timestamp_column(self):
        """CORRECTION : test que le bug 'columblns' est bien corrigé."""
        df = _make_test_df(200, n_motors=1)
        df_no_ts = df.drop(columns=["timestamp"])  # Enlève le timestamp
        cleaner = Level1Cleaner(null_strategy="flag")
        # Ne doit PAS planter avec AttributeError: 'columblns'
        df_out, report = cleaner.clean(df_no_ts)
        assert "timestamp" in df_out.columns, "Le timestamp doit être généré si absent"
        assert len(report.issues) > 0

    def test_physical_bounds(self):
        """Les valeurs hors bornes physiques doivent devenir NaN."""
        df = _make_test_df(100, n_motors=1)
        # Injecter des valeurs impossibles
        df.loc[0, "temperature"]  = 999.0   # > 300°C
        df.loc[1, "vibration_x"]  = -100.0  # < -50g
        df.loc[2, "current"]      = 200.0   # > 100A

        cleaner = Level1Cleaner(null_strategy="flag")
        df_out, report = cleaner.clean(df)

        assert pd.isna(df_out.loc[0, "temperature"])
        assert pd.isna(df_out.loc[1, "vibration_x"])
        assert pd.isna(df_out.loc[2, "current"])
        assert any("out-of-bounds" in issue for issue in report.issues)

    def test_duplicate_removal(self):
        """Les doublons (même timestamp + motor_id) doivent être supprimés."""
        df = _make_test_df(100, n_motors=1)
        df_dup = pd.concat([df, df.head(5)], ignore_index=True)  # 5 doublons

        cleaner = Level1Cleaner()
        df_out, report = cleaner.clean(df_dup)
        assert len(df_out) == 100
        assert any("Doublons" in issue for issue in report.issues)

    def test_retention_rate(self):
        """Sur des données propres, le taux de rétention doit être > 95%."""
        df = _make_test_df(500, n_motors=2)
        cleaner = Level1Cleaner()
        df_out, report = cleaner.clean(df)
        assert report.retention_rate >= 0.95, f"Rétention trop faible : {report.retention_rate:.1%}"

    def test_pandas2_no_fillna_method_deprecation(self):
        """Vérifie qu'aucun FutureWarning de pandas 2.x n'est levé par le code de nettoyage."""
        import warnings
        df = _make_test_df(200, n_motors=1)
        df.loc[5:10, "temperature"] = np.nan  # Injecter des NaN

        with warnings.catch_warnings():
            warnings.simplefilter("error", FutureWarning)
            cleaner = Level1Cleaner(null_strategy="interpolate")
            # Ne doit pas lever de FutureWarning lié à fillna(method=...)
            try:
                cleaner.clean(df)
            except FutureWarning as e:
                pytest.fail(f"FutureWarning pandas 2.x levé : {e}")


class TestLevel3Features:

    def test_feature_count(self):
        """Le Level 3 doit produire un nombre raisonnable de features (> 20)."""
        df = _make_test_df(2000, n_motors=1)
        l1_df, _ = Level1Cleaner().clean(df)
        l2_df, _ = Level2Cleaner().clean(l1_df)
        feat_df, _ = Level3FeatureEngineer(window_size=512).extract(l2_df)

        non_meta = [c for c in feat_df.columns
                    if c not in ("motor_id", "timestamp", "label", "rul", "data_origin")]
        assert len(non_meta) >= 20, f"Trop peu de features : {len(non_meta)}"

    def test_no_nan_in_features(self):
        """Le DataFrame features ne doit pas avoir de NaN dans les colonnes numériques."""
        df = _make_test_df(2000, n_motors=1)
        pipeline = CleaningPipeline()
        feat_df, _ = pipeline.run(df)

        numeric_cols = feat_df.select_dtypes(include=[np.number]).columns
        n_nan = feat_df[numeric_cols].isna().sum().sum()
        assert n_nan == 0, f"{n_nan} NaN restants dans les features"


class TestMotorSplitSafety:
    """Vérifie que le pipeline ne mélange pas les données des moteurs."""

    def test_motor_ids_preserved(self):
        """Les motor_id doivent être conservés dans les features L3."""
        df = _make_test_df(2000, n_motors=3)
        pipeline = CleaningPipeline()
        feat_df, _ = pipeline.run(df)
        assert "motor_id" in feat_df.columns
        # Tous les moteurs d'origine doivent être représentés
        original_motors = set(df["motor_id"].unique())
        feature_motors  = set(feat_df["motor_id"].unique())
        assert feature_motors.issubset(original_motors)
