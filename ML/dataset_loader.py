"""
src/ingestion/dataset_loader.py

Télécharge et charge les datasets publics :
- CWRU Bearing Dataset
- NASA IMS Bearing
- MAFAULDA
"""

import os
import io
import zipfile
import requests
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional
from loguru import logger
from scipy.io import loadmat
from tqdm import tqdm


class DatasetLoader:
    """
    Charge les datasets publics et les convertit au format
    standard attendu par le pipeline (même colonnes que l'ESP32).

    Colonnes de sortie standard :
        timestamp, motor_id, temperature, vibration_x, vibration_y,
        vibration_z, current, voltage, acoustic_db, label, rul
    """

    STANDARD_COLS = [
        "timestamp", "motor_id", "temperature", "vibration_x",
        "vibration_y", "vibration_z", "current", "voltage",
        "acoustic_db", "label", "rul"
    ]

    def __init__(self, raw_dir: str = "data/raw"):
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    # ── CWRU Bearing Dataset ─────────────────────────────────
    def load_cwru(self, fault_type: str = "all") -> pd.DataFrame:
        """
        CWRU Bearing Dataset — vibrations uniquement.
        On synthétise température + courant pour compléter.
        fault_type: 'normal' | 'ball' | 'inner_race' | 'outer_race' | 'all'
        """
        logger.info("Loading CWRU Bearing Dataset...")

        # URLs des fichiers .mat CWRU
        cwru_files = {
            "normal":     "https://engineering.case.edu/sites/default/files/97.mat",
            "ball":       "https://engineering.case.edu/sites/default/files/105.mat",
            "inner_race": "https://engineering.case.edu/sites/default/files/109.mat",
            "outer_race": "https://engineering.case.edu/sites/default/files/130.mat",
        }

        label_map = {"normal": 0, "ball": 1, "inner_race": 2, "outer_race": 3}
        dfs = []

        targets = cwru_files if fault_type == "all" else {fault_type: cwru_files[fault_type]}

        for name, url in targets.items():
            cache_path = self.raw_dir / f"cwru_{name}.mat"

            if not cache_path.exists():
                logger.info(f"  Downloading {name}...")
                self._download(url, cache_path)

            try:
                mat = loadmat(str(cache_path))
                # Chercher la clé de vibration drive-end
                vib_key = [k for k in mat.keys() if "DE_time" in k]
                if not vib_key:
                    vib_key = [k for k in mat.keys() if not k.startswith("_")]

                vib = mat[vib_key[0]].flatten()
                n = len(vib)
                sr = 12000  # Hz CWRU

                df = pd.DataFrame({
                    "timestamp":   pd.date_range("2024-01-01", periods=n, freq=f"{1/sr:.6f}s"),
                    "motor_id":    f"cwru_{name}",
                    "vibration_x": vib,
                    "vibration_y": self._add_noise(vib, scale=0.05),
                    "vibration_z": self._add_noise(vib, scale=0.03),
                    "temperature": self._simulate_temperature(n, label=label_map[name]),
                    "current":     self._simulate_current(vib, label=label_map[name]),
                    "voltage":     np.full(n, 220.0) + np.random.normal(0, 0.5, n),
                    "acoustic_db": self._simulate_acoustic(vib, label=label_map[name]),
                    "label":       label_map[name],
                    "rul":         self._compute_rul(n, label=label_map[name]),
                })
                dfs.append(df)
                logger.info(f"  ✓ {name}: {n:,} samples")

            except Exception as e:
                logger.warning(f"  ✗ {name}: {e} — using synthetic fallback")
                dfs.append(self._generate_synthetic(name, label_map[name]))

        return pd.concat(dfs, ignore_index=True)

    # ── NASA IMS Bearing ─────────────────────────────────────
    def load_nasa_ims(self, test_set: int = 1) -> pd.DataFrame:
        """
        NASA IMS Bearing — 4 roulements, vibrations + température.
        test_set: 1 | 2 | 3 (3 run-to-failure experiments)
        """
        logger.info(f"Loading NASA IMS Dataset (test set {test_set})...")

        cache_dir = self.raw_dir / "nasa_ims"
        cache_dir.mkdir(exist_ok=True)

        # NASA IMS est dans un zip — utiliser données synthétiques réalistes si absent
        zip_path = cache_dir / f"IMS_test{test_set}.zip"

        if zip_path.exists():
            return self._parse_nasa_ims(zip_path, test_set)
        else:
            logger.info("  NASA IMS not downloaded — generating realistic run-to-failure data")
            return self._generate_run_to_failure(
                motor_id=f"nasa_ims_t{test_set}",
                duration_hours=160,
                n_bearings=4
            )

    # ── MAFAULDA ─────────────────────────────────────────────
    def load_mafaulda(self) -> pd.DataFrame:
        """
        MAFAULDA — vibration 3 axes + acoustique + courant.
        Dataset le plus complet pour nos capteurs ESP32.
        """
        logger.info("Loading MAFAULDA Dataset...")
        cache_dir = self.raw_dir / "mafaulda"

        if cache_dir.exists() and any(cache_dir.glob("*.csv")):
            return self._parse_mafaulda(cache_dir)
        else:
            logger.info("  MAFAULDA not downloaded — generating realistic multi-sensor data")
            return self._generate_mafaulda_like()

    # ── Synthetic Generator (fallback + augmentation) ─────────
    def generate_synthetic(
        self,
        n_motors: int = 10,
        duration_hours: int = 500,
        fault_rate: float = 0.15,
    ) -> pd.DataFrame:
        """
        Génère des données synthétiques réalistes pour tous les capteurs ESP32.
        Reproduit la physique des pannes moteur : vibration croissante,
        température élevée, courant anormal.
        """
        logger.info(f"Generating synthetic dataset: {n_motors} motors, {duration_hours}h each")
        dfs = []

        for motor_i in range(n_motors):
            motor_id = f"motor_{motor_i:03d}"
            will_fail = np.random.random() < fault_rate
            fault_type = np.random.choice(["bearing", "imbalance", "misalignment", "electrical"])

            df = self._generate_motor_lifetime(
                motor_id=motor_id,
                duration_hours=duration_hours,
                will_fail=will_fail,
                fault_type=fault_type,
            )
            dfs.append(df)
            logger.debug(f"  {motor_id}: {'FAIL→' + fault_type:20s} {len(df):,} pts")

        result = pd.concat(dfs, ignore_index=True)
        logger.info(f"  ✓ Synthetic: {len(result):,} total samples, {n_motors} motors")
        return result

    def _generate_motor_lifetime(
        self,
        motor_id: str,
        duration_hours: int,
        will_fail: bool,
        fault_type: str,
        sr_hz: int = 100,       # 100 Hz comme l'ESP32
    ) -> pd.DataFrame:
        """Génère la vie complète d'un moteur avec dégradation progressive."""

        n = duration_hours * 3600 * sr_hz
        t = np.linspace(0, duration_hours * 3600, n)
        timestamps = pd.date_range("2024-01-01", periods=n, freq=f"{1/sr_hz:.4f}s")

        # ── Dégradation progressive ───────────────────────────
        if will_fail:
            # Courbe de dégradation sigmoïde (dégradation accélère vers la fin)
            fail_point = np.random.uniform(0.6, 0.95)  # défaillance entre 60-95% du cycle
            degrad = self._sigmoid_degradation(t / t[-1], fail_point)
        else:
            degrad = np.zeros(n) + np.random.uniform(0, 0.15)

        noise = lambda scale: np.random.normal(0, scale, n)

        # ── Température ───────────────────────────────────────
        base_temp = np.random.uniform(35, 55)
        temp_fault_factor = {
            "bearing": 0.8, "imbalance": 0.5,
            "misalignment": 0.6, "electrical": 1.2,
        }.get(fault_type, 0.7)

        temperature = (
            base_temp
            + degrad * 40 * temp_fault_factor   # montée progressive
            + 5 * np.sin(2 * np.pi * t / 3600)  # cycle thermique horaire
            + noise(0.3)
        )

        # ── Vibration ─────────────────────────────────────────
        base_vib = np.random.uniform(0.1, 0.5)
        freq_motor = np.random.uniform(48, 52)  # ~50 Hz moteur

        vib_fault_factor = {
            "bearing": 1.5, "imbalance": 2.0,
            "misalignment": 1.8, "electrical": 0.8,
        }.get(fault_type, 1.0)

        vib_x = (
            base_vib * np.sin(2 * np.pi * freq_motor * t)
            + degrad * 8 * vib_fault_factor * (1 + 0.3 * np.random.randn(n))
            + noise(0.05)
        )
        vib_y = vib_x * 0.7 + noise(0.03)
        vib_z = vib_x * 0.4 + noise(0.02)

        # ── Courant ───────────────────────────────────────────
        base_current = np.random.uniform(8, 15)
        current = (
            base_current
            + degrad * 6
            + 0.5 * np.sin(2 * np.pi * 50 * t)   # harmonique 50Hz
            + noise(0.1)
        )
        current = np.clip(current, 0, 30)

        # ── Tension ───────────────────────────────────────────
        voltage = 220 + noise(1.5)

        # ── Acoustique ────────────────────────────────────────
        base_db = np.random.uniform(55, 70)
        acoustic_db = (
            base_db
            + degrad * 25
            + noise(1.0)
        )
        acoustic_db = np.clip(acoustic_db, 30, 130)

        # ── Labels ────────────────────────────────────────────
        if will_fail:
            fail_idx = int(fail_point * n)
            labels = np.zeros(n, dtype=int)
            labels[int(0.80 * fail_idx):fail_idx] = 1   # warning
            labels[fail_idx:] = 2                         # critical
            rul = np.maximum(0, (fail_idx - np.arange(n)) / (sr_hz * 3600 * 24))
        else:
            labels = np.zeros(n, dtype=int)
            rul = np.full(n, duration_hours / 24 * 2)    # RUL très grand

        return pd.DataFrame({
            "timestamp":   timestamps,
            "motor_id":    motor_id,
            "temperature": temperature.round(2),
            "vibration_x": vib_x.round(4),
            "vibration_y": vib_y.round(4),
            "vibration_z": vib_z.round(4),
            "current":     current.round(3),
            "voltage":     voltage.round(2),
            "acoustic_db": acoustic_db.round(1),
            "label":       labels,          # 0=normal, 1=warning, 2=critical
            "rul":         rul.round(2),    # jours restants
        })

    # ── Helpers ───────────────────────────────────────────────
    @staticmethod
    def _sigmoid_degradation(x: np.ndarray, inflection: float) -> np.ndarray:
        """Courbe sigmoïde centrée sur inflection."""
        k = 12
        return 1 / (1 + np.exp(-k * (x - inflection)))

    @staticmethod
    def _simulate_temperature(n: int, label: int) -> np.ndarray:
        base = {0: 45, 1: 62, 2: 74, 3: 58}[label]
        return np.clip(base + np.random.normal(0, 1.5, n), -10, 200)

    @staticmethod
    def _simulate_current(vib: np.ndarray, label: int) -> np.ndarray:
        base = {0: 10, 1: 12, 2: 14, 3: 13}[label]
        return np.clip(base + 0.3 * np.abs(vib) + np.random.normal(0, 0.2, len(vib)), 0, 30)

    @staticmethod
    def _simulate_acoustic(vib: np.ndarray, label: int) -> np.ndarray:
        base = {0: 60, 1: 72, 2: 80, 3: 75}[label]
        return np.clip(base + 5 * np.abs(vib) + np.random.normal(0, 1, len(vib)), 30, 130)

    @staticmethod
    def _compute_rul(n: int, label: int) -> np.ndarray:
        """RUL en jours — normal a RUL très grand."""
        if label == 0:
            return np.full(n, 365.0)
        max_rul = {1: 30, 2: 15, 3: 20}[label]
        return np.linspace(max_rul, 0, n)

    @staticmethod
    def _add_noise(signal: np.ndarray, scale: float = 0.05) -> np.ndarray:
        return signal + np.random.normal(0, scale * np.std(signal), len(signal))

    def _generate_run_to_failure(self, motor_id: str, duration_hours: int, n_bearings: int) -> pd.DataFrame:
        return self._generate_motor_lifetime(
            motor_id=motor_id, duration_hours=duration_hours,
            will_fail=True, fault_type="bearing"
        )

    def _generate_synthetic(self, name: str, label: int) -> pd.DataFrame:
        n = 50000
        sr = 12000
        vib = np.random.normal(0, 0.5 * (1 + label), n)
        return pd.DataFrame({
            "timestamp":   pd.date_range("2024-01-01", periods=n, freq=f"{1/sr:.6f}s"),
            "motor_id":    f"cwru_{name}_synth",
            "vibration_x": vib,
            "vibration_y": self._add_noise(vib, 0.05),
            "vibration_z": self._add_noise(vib, 0.03),
            "temperature": self._simulate_temperature(n, label),
            "current":     self._simulate_current(vib, label),
            "voltage":     np.full(n, 220.0),
            "acoustic_db": self._simulate_acoustic(vib, label),
            "label":       label,
            "rul":         self._compute_rul(n, label),
        })

    def _generate_mafaulda_like(self) -> pd.DataFrame:
        return self.generate_synthetic(n_motors=5, duration_hours=200)

    def _parse_mafaulda(self, cache_dir: Path) -> pd.DataFrame:
        dfs = []
        for csv_file in sorted(cache_dir.glob("*.csv")):
            df = pd.read_csv(csv_file, header=None,
                names=["vibration_x", "vibration_y", "vibration_z",
                       "acoustic_db", "current", "extra"])
            label = 0 if "normal" in csv_file.name else 1
            df["motor_id"] = csv_file.stem
            df["label"] = label
            dfs.append(df)
        return pd.concat(dfs, ignore_index=True)

    def _parse_nasa_ims(self, zip_path: Path, test_set: int) -> pd.DataFrame:
        dfs = []
        with zipfile.ZipFile(zip_path) as z:
            for fname in sorted(z.namelist()):
                with z.open(fname) as f:
                    arr = np.frombuffer(f.read(), dtype=np.float64).reshape(-1, 8)
                    df = pd.DataFrame(arr, columns=[f"ch_{i}" for i in range(8)])
                    dfs.append(df)
        return pd.concat(dfs, ignore_index=True)

    @staticmethod
    def _download(url: str, dest: Path) -> None:
        try:
            r = requests.get(url, stream=True, timeout=30)
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            with open(dest, "wb") as f, tqdm(total=total, unit="B", unit_scale=True) as bar:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
                    bar.update(len(chunk))
        except Exception as e:
            logger.warning(f"Download failed: {e}")
            dest.unlink(missing_ok=True)
