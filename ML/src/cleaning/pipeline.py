"""
src/cleaning/pipeline.py

Pipeline nettoyage multi-niveau :
  Niveau 1 — Nettoyage brut (valeurs impossibles, doublons, nulls)
  Niveau 2 — Structuration (rééchantillonnage, interpolation, alignement)
  Niveau 3 — Feature engineering (domaine temporel, fréquentiel, cross-capteurs)
"""

import numpy as np
import pandas as pd
from scipy import signal, stats
from scipy.fft import fft, fftfreq
from typing import Optional
from loguru import logger
from dataclasses import dataclass, field


@dataclass
class CleaningReport:
    level: int
    input_rows: int
    output_rows: int
    dropped_rows: int = 0
    flagged_rows: int = 0
    interpolated_points: int = 0
    issues: list = field(default_factory=list)

    @property
    def retention_rate(self) -> float:
        return self.output_rows / max(self.input_rows, 1)


# ═══════════════════════════════════════════════════════════
# NIVEAU 1 — Nettoyage Brut
# ═══════════════════════════════════════════════════════════

class Level1Cleaner:
    """
    Nettoyage brut — données telles qu'elles arrivent (ESP32 ou CSV).
    
    Opérations :
    - Suppression doublons (timestamps identiques)
    - Rejet valeurs physiquement impossibles
    - Flaguer valeurs nulles / NaN
    - Validation format timestamps
    - Détection outliers statistiques extrêmes (>6σ)
    """

    PHYSICAL_BOUNDS = {
        "temperature":  (-20.0, 300.0),    # °C
        "vibration_x":  (-50.0, 50.0),     # g
        "vibration_y":  (-50.0, 50.0),     # g
        "vibration_z":  (-50.0, 50.0),     # g
        "current":      (-5.0,  100.0),    # A
        "voltage":      (0.0,   500.0),    # V
        "acoustic_db":  (0.0,   140.0),    # dB
    }

    SENSOR_COLS = list(PHYSICAL_BOUNDS.keys())

    def __init__(self, null_strategy: str = "flag"):
        """
        null_strategy: 'flag' | 'drop' | 'interpolate'
        """
        self.null_strategy = null_strategy

    def clean(self, df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
        report = CleaningReport(level=1, input_rows=len(df))
        df = df.copy()

        # 1.1 Forcer le type timestamp
        df = self._validate_timestamps(df, report)

        # 1.2 Supprimer doublons exacts
        before = len(df)
        df = df.drop_duplicates(subset=["timestamp", "motor_id"])
        dup_dropped = before - len(df)
        if dup_dropped > 0:
            report.issues.append(f"Duplicates dropped: {dup_dropped}")
            report.dropped_rows += dup_dropped

        # 1.3 Trier par timestamp
        df = df.sort_values(["motor_id", "timestamp"]).reset_index(drop=True)

        # 1.4 Rejeter valeurs physiquement impossibles
        df, phy_report = self._check_physical_bounds(df)
        report.issues.extend(phy_report)
        report.flagged_rows += df["_has_anomaly"].sum() if "_has_anomaly" in df else 0

        # 1.5 Gérer les NaN
        df, null_report = self._handle_nulls(df)
        report.issues.extend(null_report)

        # 1.6 Outliers statistiques extrêmes (>6σ) → flag seulement
        df = self._flag_statistical_outliers(df, sigma=6.0)

        report.output_rows = len(df)
        report.dropped_rows = report.input_rows - report.output_rows

        logger.info(
            f"[L1] {report.input_rows:,} → {report.output_rows:,} rows "
            f"({report.retention_rate:.1%} retention) | issues: {len(report.issues)}"
        )
        return df, report

    def _validate_timestamps(self, df: pd.DataFrame, report: CleaningReport) -> pd.DataFrame:
        if "timestamp" not in df.columns:
            df["timestamp"] = pd.date_range("2024-01-01", periods=len(df), freq="10ms")
            report.issues.append("Timestamp column missing — generated synthetic")
            return df
        try:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False, errors="coerce")
            invalid = df["timestamp"].isna().sum()
            if invalid > 0:
                df = df.dropna(subset=["timestamp"])
                report.issues.append(f"Invalid timestamps dropped: {invalid}")
        except Exception as e:
            report.issues.append(f"Timestamp parsing error: {e}")
        return df

    def _check_physical_bounds(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
        issues = []
        df["_out_of_bounds"] = False

        for col, (lo, hi) in self.PHYSICAL_BOUNDS.items():
            if col not in df.columns:
                continue
            mask = (df[col] < lo) | (df[col] > hi)
            n_bad = mask.sum()
            if n_bad > 0:
                df.loc[mask, col] = np.nan
                df.loc[mask, "_out_of_bounds"] = True
                issues.append(f"{col}: {n_bad} out-of-bounds → NaN")

        return df, issues

    def _handle_nulls(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
        issues = []
        null_counts = df[self.SENSOR_COLS].isna().sum()
        total_nulls = null_counts.sum()

        if total_nulls == 0:
            return df, issues

        issues.append(f"NaN found: {dict(null_counts[null_counts > 0])}")

        if self.null_strategy == "drop":
            before = len(df)
            df = df.dropna(subset=self.SENSOR_COLS)
            issues.append(f"Rows dropped (NaN): {before - len(df)}")

        elif self.null_strategy == "interpolate":
            for col in self.SENSOR_COLS:
                if col in df.columns:
                    df[col] = df[col].interpolate(method="linear", limit=10)
                    df[col] = df[col].fillna(method="bfill").fillna(method="ffill")

        elif self.null_strategy == "flag":
            df["_has_null"] = df[self.SENSOR_COLS].isna().any(axis=1)
            # Interpolation légère même en mode flag
            for col in self.SENSOR_COLS:
                if col in df.columns:
                    df[col] = df[col].interpolate(method="linear", limit=5)

        return df, issues

    def _flag_statistical_outliers(self, df: pd.DataFrame, sigma: float = 6.0) -> pd.DataFrame:
        df["_statistical_outlier"] = False
        for col in self.SENSOR_COLS:
            if col not in df.columns:
                continue
            mu, std = df[col].mean(), df[col].std()
            if std > 0:
                mask = (df[col] - mu).abs() > sigma * std
                df.loc[mask, "_statistical_outlier"] = True
        return df


# ═══════════════════════════════════════════════════════════
# NIVEAU 2 — Structuration
# ═══════════════════════════════════════════════════════════

class Level2Cleaner:
    """
    Structuration — rendre les données cohérentes et synchronisées.

    Opérations :
    - Rééchantillonnage uniforme (target Hz)
    - Interpolation des petits gaps temporels
    - Alignement temporel multi-capteurs
    - Normalisation des unités
    - Détection et marquage des gaps trop grands
    """

    SENSOR_COLS = Level1Cleaner.SENSOR_COLS

    def __init__(
        self,
        target_hz: int = 100,
        max_gap_seconds: float = 5.0,
        interp_method: str = "linear",
    ):
        self.target_hz = target_hz
        self.target_freq = f"{1/target_hz:.6f}s"
        self.max_gap_seconds = max_gap_seconds
        self.interp_method = interp_method

    def clean(self, df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
        report = CleaningReport(level=2, input_rows=len(df))
        results = []

        for motor_id, group in df.groupby("motor_id"):
            cleaned, n_interp = self._process_motor(group.copy())
            report.interpolated_points += n_interp
            results.append(cleaned)

        df_out = pd.concat(results, ignore_index=True) if results else df.copy()
        report.output_rows = len(df_out)

        logger.info(
            f"[L2] {report.input_rows:,} → {report.output_rows:,} rows | "
            f"interpolated: {report.interpolated_points:,}"
        )
        return df_out, report

    def _process_motor(self, df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
        df = df.sort_values("timestamp")
        n_interp = 0

        # Détecter les grands gaps → ne pas interpoler par-dessus
        time_diffs = df["timestamp"].diff().dt.total_seconds()
        large_gaps = time_diffs > self.max_gap_seconds
        df["_large_gap"] = large_gaps.fillna(False)

        # Rééchantillonner sur grille uniforme
        df = df.set_index("timestamp")

        # Garder les métadonnées non-numériques
        motor_id = df["motor_id"].iloc[0] if "motor_id" in df.columns else "unknown"
        label_col = df["label"] if "label" in df.columns else None
        rul_col   = df["rul"]   if "rul"   in df.columns else None

        # Interpoler colonnes numériques
        numeric_cols = [c for c in self.SENSOR_COLS if c in df.columns]
        df_num = df[numeric_cols].copy()

        # Rééchantillonnage
        df_resampled = df_num.resample(self.target_freq).mean()

        # Interpoler (seulement les petits gaps)
        n_before = df_resampled.isna().sum().sum()
        df_resampled = df_resampled.interpolate(method=self.interp_method, limit=int(self.target_hz * self.max_gap_seconds))
        n_interp = n_before - df_resampled.isna().sum().sum()

        # Forward/backward fill pour les bords
        df_resampled = df_resampled.fillna(method="bfill").fillna(method="ffill")

        df_resampled = df_resampled.reset_index()
        df_resampled.rename(columns={"index": "timestamp"}, inplace=True)
        df_resampled["motor_id"] = motor_id

        # Réintégrer label et RUL (interpolés séparément)
        if label_col is not None:
            df_resampled["label"] = (
                label_col.resample(self.target_freq).max()
                .fillna(method="ffill").fillna(0).astype(int).values[:len(df_resampled)]
            )
        if rul_col is not None:
            df_resampled["rul"] = (
                rul_col.resample(self.target_freq).mean()
                .interpolate().values[:len(df_resampled)]
            )

        return df_resampled, int(n_interp)


# ═══════════════════════════════════════════════════════════
# NIVEAU 3 — Feature Engineering
# ═══════════════════════════════════════════════════════════

class Level3FeatureEngineer:
    """
    Feature engineering — extraire les features ML depuis les signaux bruts.

    Features extraites :
    ┌─────────────────────────────────────────────────────┐
    │ Domaine temporel  : RMS, Kurtosis, Peak2Peak, ...   │
    │ Domaine fréquentiel: FFT, Spectral Centroid, THD... │
    │ Cross-capteurs    : Corrélation vib-courant, SNR... │
    │ Rolling stats     : mean/std sur 10s, 60s, 300s    │
    └─────────────────────────────────────────────────────┘
    """

    VIB_COLS = ["vibration_x", "vibration_y", "vibration_z"]

    def __init__(
        self,
        window_size: int = 512,      # ~5 secondes à 100 Hz
        overlap: float = 0.5,
        sampling_rate: int = 100,
        rolling_windows: list = None,
    ):
        self.window_size = window_size
        self.step = int(window_size * (1 - overlap))
        self.fs = sampling_rate
        self.rolling_windows = rolling_windows or [10, 60, 300]  # secondes

    def extract(self, df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
        report = CleaningReport(level=3, input_rows=len(df))
        results = []

        for motor_id, group in df.groupby("motor_id"):
            features = self._extract_motor_features(group.copy())
            if features is not None:
                results.append(features)

        df_feat = pd.concat(results, ignore_index=True) if results else pd.DataFrame()
        report.output_rows = len(df_feat)

        logger.info(
            f"[L3] {report.input_rows:,} samples → {report.output_rows:,} feature windows "
            f"({len(df_feat.columns) if not df_feat.empty else 0} features each)"
        )
        return df_feat, report

    def _extract_motor_features(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        if len(df) < self.window_size:
            return None

        windows = []
        n = len(df)

        for start in range(0, n - self.window_size + 1, self.step):
            end = start + self.window_size
            window = df.iloc[start:end]
            feats = self._extract_window(window)
            windows.append(feats)

        return pd.DataFrame(windows)

    def _extract_window(self, w: pd.DataFrame) -> dict:
        feats = {
            "motor_id":  w["motor_id"].iloc[0],
            "timestamp": w["timestamp"].iloc[self.window_size // 2],  # milieu de fenêtre
        }

        # ── Domaine temporel ──────────────────────────────────
        for col in self.VIB_COLS:
            if col in w.columns:
                x = w[col].values
                feats.update(self._time_domain_features(x, prefix=col))

        if "temperature" in w.columns:
            feats.update(self._temperature_features(w["temperature"].values))

        if "current" in w.columns:
            feats.update(self._current_features(w["current"].values))

        if "acoustic_db" in w.columns:
            feats.update(self._acoustic_features(w["acoustic_db"].values))

        # ── Domaine fréquentiel ───────────────────────────────
        for col in self.VIB_COLS:
            if col in w.columns:
                feats.update(self._freq_domain_features(w[col].values, prefix=col))

        if "current" in w.columns:
            feats.update(self._thd_feature(w["current"].values))

        # ── Cross-capteurs ────────────────────────────────────
        feats.update(self._cross_sensor_features(w))

        # ── Rolling stats ─────────────────────────────────────
        feats.update(self._rolling_features(w))

        # ── Labels ───────────────────────────────────────────
        if "label" in w.columns:
            feats["label"] = int(w["label"].mode()[0])
        if "rul" in w.columns:
            feats["rul"] = w["rul"].mean()

        return feats

    # ── Domaine temporel ──────────────────────────────────────
    def _time_domain_features(self, x: np.ndarray, prefix: str) -> dict:
        rms = np.sqrt(np.mean(x ** 2))
        peak = np.max(np.abs(x))
        mean_abs = np.mean(np.abs(x))
        std = np.std(x)
        eps = 1e-10

        return {
            f"{prefix}_rms":             rms,
            f"{prefix}_peak":            peak,
            f"{prefix}_peak_to_peak":    np.ptp(x),
            f"{prefix}_mean":            np.mean(x),
            f"{prefix}_std":             std,
            f"{prefix}_variance":        np.var(x),
            f"{prefix}_kurtosis":        stats.kurtosis(x),
            f"{prefix}_skewness":        stats.skew(x),
            f"{prefix}_crest_factor":    peak / (rms + eps),
            f"{prefix}_shape_factor":    rms / (mean_abs + eps),
            f"{prefix}_impulse_factor":  peak / (mean_abs + eps),
            f"{prefix}_zcr":             np.mean(np.diff(np.sign(x)) != 0),
        }

    def _temperature_features(self, temp: np.ndarray) -> dict:
        return {
            "temp_mean":      np.mean(temp),
            "temp_std":       np.std(temp),
            "temp_max":       np.max(temp),
            "temp_delta":     temp[-1] - temp[0],
            "temp_trend":     np.polyfit(np.arange(len(temp)), temp, 1)[0],
        }

    def _current_features(self, curr: np.ndarray) -> dict:
        rms = np.sqrt(np.mean(curr ** 2))
        return {
            "current_rms":    rms,
            "current_mean":   np.mean(curr),
            "current_std":    np.std(curr),
            "current_peak":   np.max(np.abs(curr)),
            "current_cf":     np.max(np.abs(curr)) / (rms + 1e-10),
        }

    def _acoustic_features(self, db: np.ndarray) -> dict:
        return {
            "acoustic_mean": np.mean(db),
            "acoustic_std":  np.std(db),
            "acoustic_max":  np.max(db),
            "acoustic_p95":  np.percentile(db, 95),
        }

    # ── Domaine fréquentiel ───────────────────────────────────
    def _freq_domain_features(self, x: np.ndarray, prefix: str) -> dict:
        n = len(x)
        freqs = fftfreq(n, d=1 / self.fs)[:n // 2]
        spectrum = np.abs(fft(x))[:n // 2]
        ps = spectrum ** 2  # power spectrum
        total_power = ps.sum() + 1e-10

        dominant_idx = np.argmax(spectrum)
        spectral_mean = np.sum(freqs * ps) / total_power

        # Bandes de fréquence
        def band_power(lo, hi):
            mask = (freqs >= lo) & (freqs < hi)
            return ps[mask].sum() / total_power

        return {
            f"{prefix}_dominant_freq":     freqs[dominant_idx],
            f"{prefix}_dominant_amp":      spectrum[dominant_idx],
            f"{prefix}_spectral_centroid": spectral_mean,
            f"{prefix}_spectral_spread":   np.sqrt(np.sum((freqs - spectral_mean) ** 2 * ps) / total_power),
            f"{prefix}_spectral_rolloff":  self._spectral_rolloff(freqs, ps, 0.85),
            f"{prefix}_spectral_flux":     np.sum(np.diff(spectrum) ** 2),
            f"{prefix}_bp_0_500":          band_power(0, 500),
            f"{prefix}_bp_500_2k":         band_power(500, 2000),
            f"{prefix}_bp_2k_5k":          band_power(2000, 5000),
        }

    def _thd_feature(self, current: np.ndarray) -> dict:
        """Total Harmonic Distortion du courant (indicateur de défaut électrique)."""
        n = len(current)
        freqs = fftfreq(n, d=1 / self.fs)[:n // 2]
        spectrum = np.abs(fft(current))[:n // 2]

        # Fondamentale à ~50 Hz
        f0_idx = np.argmin(np.abs(freqs - 50))
        f0_amp = spectrum[f0_idx]

        # Harmoniques 2→5
        harmonic_amps = []
        for h in range(2, 6):
            h_idx = np.argmin(np.abs(freqs - 50 * h))
            harmonic_amps.append(spectrum[h_idx])

        thd = np.sqrt(sum(a ** 2 for a in harmonic_amps)) / (f0_amp + 1e-10)
        return {"current_thd": thd}

    @staticmethod
    def _spectral_rolloff(freqs, power_spectrum, threshold=0.85) -> float:
        cumsum = np.cumsum(power_spectrum)
        rolloff_idx = np.searchsorted(cumsum, threshold * cumsum[-1])
        return freqs[min(rolloff_idx, len(freqs) - 1)]

    # ── Cross-capteurs ────────────────────────────────────────
    def _cross_sensor_features(self, w: pd.DataFrame) -> dict:
        feats = {}

        # Corrélation vibration – courant (signature de défaut)
        if "vibration_x" in w.columns and "current" in w.columns:
            feats["corr_vib_current"] = np.corrcoef(
                w["vibration_x"].values, w["current"].values
            )[0, 1]

        # RMS vibration total (3 axes)
        vib_cols_present = [c for c in self.VIB_COLS if c in w.columns]
        if vib_cols_present:
            vib_rms = np.sqrt(sum(
                np.mean(w[c].values ** 2) for c in vib_cols_present
            ))
            feats["vibration_total_rms"] = vib_rms

        # SNR acoustique estimé
        if "acoustic_db" in w.columns:
            db = w["acoustic_db"].values
            signal_power = np.mean(db)
            noise_floor = np.percentile(db, 10)
            feats["acoustic_snr"] = signal_power - noise_floor

        # Puissance apparente
        if "current" in w.columns and "voltage" in w.columns:
            feats["apparent_power"] = np.mean(w["current"].values) * np.mean(w["voltage"].values)

        return feats

    # ── Rolling stats ─────────────────────────────────────────
    def _rolling_features(self, w: pd.DataFrame) -> dict:
        feats = {}
        # Sur les colonnes clés seulement
        key_cols = {"vibration_x": "vib", "temperature": "temp", "current": "cur"}

        for col, short in key_cols.items():
            if col not in w.columns:
                continue
            arr = w[col].values
            for win_s in self.rolling_windows:
                win_pts = min(win_s * self.fs, len(arr))
                window_data = arr[-win_pts:]
                feats[f"{short}_roll_{win_s}s_mean"] = np.mean(window_data)
                feats[f"{short}_roll_{win_s}s_std"]  = np.std(window_data)
                feats[f"{short}_roll_{win_s}s_max"]  = np.max(window_data)

        return feats


# ═══════════════════════════════════════════════════════════
# Orchestrateur — 3 niveaux enchaînés
# ═══════════════════════════════════════════════════════════

class CleaningPipeline:
    """
    Orchestre les 3 niveaux de nettoyage.
    Peut être utilisé en mode batch (datasets) ou streaming (ESP32).
    """

    def __init__(self, config: dict = None):
        cfg = config or {}
        l1_cfg = cfg.get("level1", {})
        l2_cfg = cfg.get("level2", {})
        l3_cfg = cfg.get("level3", {})

        self.l1 = Level1Cleaner(null_strategy=l1_cfg.get("null_strategy", "flag"))
        self.l2 = Level2Cleaner(
            target_hz=l2_cfg.get("resample_hz", 100),
            max_gap_seconds=l2_cfg.get("max_gap_seconds", 5.0),
        )
        self.l3 = Level3FeatureEngineer(
            window_size=l3_cfg.get("window_size", 512),
            overlap=l3_cfg.get("overlap", 0.5),
            sampling_rate=l2_cfg.get("resample_hz", 100),
        )

    def run(self, df: pd.DataFrame, save_intermediates: bool = False, output_dir: str = None) -> tuple[pd.DataFrame, list]:
        """
        Exécute les 3 niveaux.
        Retourne (features_df, [report_l1, report_l2, report_l3])
        """
        logger.info(f"=== Cleaning Pipeline START: {len(df):,} rows ===")
        reports = []

        # Niveau 1
        df1, r1 = self.l1.clean(df)
        reports.append(r1)
        if save_intermediates and output_dir:
            df1.to_parquet(f"{output_dir}/level1_cleaned.parquet", index=False)

        # Niveau 2
        df2, r2 = self.l2.clean(df1)
        reports.append(r2)
        if save_intermediates and output_dir:
            df2.to_parquet(f"{output_dir}/level2_structured.parquet", index=False)

        # Niveau 3
        df3, r3 = self.l3.extract(df2)
        reports.append(r3)
        if save_intermediates and output_dir:
            df3.to_parquet(f"{output_dir}/level3_features.parquet", index=False)

        logger.info(f"=== Cleaning Pipeline END: {len(df3):,} feature windows ===")
        return df3, reports

    def run_single_window(self, window: pd.DataFrame) -> dict:
        """
        Mode streaming : traiter une seule fenêtre (données ESP32 en temps réel).
        Retourne un dict de features (pas de DataFrame).
        """
        _, _ = self.l1.clean(window)
        cleaned, _ = self.l2._process_motor(window)
        if len(cleaned) < self.l3.window_size:
            cleaned = pd.concat([cleaned] * (self.l3.window_size // len(cleaned) + 1))
            cleaned = cleaned.iloc[:self.l3.window_size]
        return self.l3._extract_window(cleaned)
