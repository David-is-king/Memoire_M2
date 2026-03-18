"""
src/monitoring/drift_monitor.py

Détection de drift (PSI + KS test) + déclenchement auto-retrain.
Fonctionne en continu sur les nouvelles données qui arrivent.
"""

import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from loguru import logger
from scipy import stats


@dataclass
class DriftReport:
    timestamp: str
    feature: str
    psi: float              # Population Stability Index
    ks_statistic: float
    ks_p_value: float
    is_drifted: bool
    severity: str           # "none" | "minor" | "major"


class DriftMonitor:
    """
    Surveille le drift entre données d'entraînement (référence) et nouvelles données.
    
    PSI < 0.10  → pas de drift
    PSI 0.10-0.25 → drift mineur
    PSI > 0.25  → drift majeur → trigger retrain
    """

    PSI_MINOR = 0.10
    PSI_MAJOR = 0.25
    N_BINS = 10

    def __init__(
        self,
        reference_data: Optional[pd.DataFrame] = None,
        artifacts_dir: str = "models/artifacts",
        auto_retrain_threshold: float = 0.25,
    ):
        self.artifacts_dir = Path(artifacts_dir)
        self.auto_retrain_threshold = auto_retrain_threshold
        self._reference_stats: dict = {}
        self._new_data_buffer: list = []
        self._retrain_triggered = False

        if reference_data is not None:
            self.fit_reference(reference_data)
        else:
            self._load_reference()

    def fit_reference(self, df: pd.DataFrame):
        """Calcule les statistiques de référence sur les données d'entraînement."""
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            if col in ("label", "rul"):
                continue
            series = df[col].dropna()
            if len(series) < 10:
                continue
            hist, bin_edges = np.histogram(series, bins=self.N_BINS)
            self._reference_stats[col] = {
                "hist":      hist,
                "bin_edges": bin_edges,
                "mean":      float(series.mean()),
                "std":       float(series.std()),
                "min":       float(series.min()),
                "max":       float(series.max()),
                "samples":   series.tolist()[:1000],  # gardé pour KS test
            }
        joblib.dump(self._reference_stats, self.artifacts_dir / "reference_stats.pkl")
        logger.info(f"✓ Reference stats computed for {len(self._reference_stats)} features")

    def _load_reference(self):
        ref_path = self.artifacts_dir / "reference_stats.pkl"
        if ref_path.exists():
            self._reference_stats = joblib.load(ref_path)
            logger.info(f"✓ Reference stats loaded ({len(self._reference_stats)} features)")

    def check_drift(self, new_data: pd.DataFrame) -> tuple[list[DriftReport], bool]:
        """
        Vérifie le drift sur un nouveau batch de données.
        Retourne (reports, should_retrain).
        """
        if not self._reference_stats:
            logger.warning("No reference stats — cannot check drift")
            return [], False

        reports = []
        n_drifted = 0

        for col, ref_stats in self._reference_stats.items():
            if col not in new_data.columns:
                continue
            new_series = new_data[col].dropna()
            if len(new_series) < 30:
                continue

            psi   = self._compute_psi(new_series.values, ref_stats["bin_edges"], ref_stats["hist"])
            ks    = stats.ks_2samp(ref_stats["samples"], new_series.tolist()[:1000])
            drift = psi > self.PSI_MINOR or ks.pvalue < 0.01

            severity = "none"
            if psi > self.PSI_MAJOR:
                severity = "major"
            elif psi > self.PSI_MINOR:
                severity = "minor"

            report = DriftReport(
                timestamp=pd.Timestamp.now().isoformat(),
                feature=col, psi=round(psi, 4),
                ks_statistic=round(float(ks.statistic), 4),
                ks_p_value=round(float(ks.pvalue), 4),
                is_drifted=drift, severity=severity,
            )
            reports.append(report)
            if severity == "major":
                n_drifted += 1

        should_retrain = n_drifted >= max(1, len(reports) * 0.2)  # >20% des features en drift majeur

        if should_retrain and not self._retrain_triggered:
            logger.warning(f"🚨 DRIFT ALERT: {n_drifted} features in major drift → triggering retrain")
            self._retrain_triggered = True

        drift_summary = {
            "total_features": len(reports),
            "drifted_major": sum(1 for r in reports if r.severity == "major"),
            "drifted_minor": sum(1 for r in reports if r.severity == "minor"),
        }
        logger.info(f"Drift check: {drift_summary}")

        return reports, should_retrain

    def _compute_psi(self, new_values: np.ndarray, bin_edges: np.ndarray, ref_hist: np.ndarray) -> float:
        """Population Stability Index."""
        new_hist, _ = np.histogram(new_values, bins=bin_edges)
        ref_pct = ref_hist / (ref_hist.sum() + 1e-10)
        new_pct = new_hist / (new_hist.sum() + 1e-10)

        # Éviter log(0)
        ref_pct = np.where(ref_pct == 0, 1e-6, ref_pct)
        new_pct = np.where(new_pct == 0, 1e-6, new_pct)

        psi = np.sum((new_pct - ref_pct) * np.log(new_pct / ref_pct))
        return float(psi)

    def add_new_samples(self, df: pd.DataFrame, retrain_threshold: int = 1000):
        """Accumule de nouvelles données et déclenche le drift check si seuil atteint."""
        self._new_data_buffer.append(df)
        total = sum(len(d) for d in self._new_data_buffer)

        if total >= retrain_threshold:
            combined = pd.concat(self._new_data_buffer, ignore_index=True)
            self._new_data_buffer.clear()
            self._retrain_triggered = False
            return self.check_drift(combined)

        return [], False
