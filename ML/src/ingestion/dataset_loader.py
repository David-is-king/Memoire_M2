# =============================================================================
# src/ingestion/dataset_loader.py
#
# Rôle : Charger les datasets bruts (CWRU .mat, MAFAULDA .csv, données synthétiques)
#        et les convertir au FORMAT STANDARD du projet, identique à ce qu'enverrait
#        un capteur ESP32 réel : même noms de colonnes, mêmes unités, même structure.
#
# Ce format unique permet que le même pipeline de nettoyage (pipeline.py) fonctionne
# indifféremment sur des données historiques et sur des données ESP32 temps réel.
#
# Format standard cible :
#   timestamp    : datetime (horodatage)
#   motor_id     : str      (identifiant unique du moteur)
#   temperature  : float    (°C)
#   vibration_x  : float    (g, axe X de l'accéléromètre)
#   vibration_y  : float    (g, axe Y)
#   vibration_z  : float    (g, axe Z)
#   current      : float    (Ampères)
#   voltage      : float    (Volts)
#   acoustic_db  : float    (décibels)
#   label        : int      (0=Normal, 1=Déséquilibre, 2=DésalignH, 3=DésalignV, 4=Roulement)
#   rul          : float    (Remaining Useful Life en jours)
#   data_origin  : str      (traçabilité : "CWRU", "MAFAULDA", "synthetic")
# =============================================================================

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional
from loguru import logger
from scipy.io import loadmat


class DatasetLoader:
    """Charge et standardise les datasets publics vers le format ESP32."""

    # ─── Colonnes du format standard ──────────────────────────────────────────
    STANDARD_COLS = [
        "timestamp", "motor_id", "temperature", "vibration_x",
        "vibration_y", "vibration_z", "current", "voltage",
        "acoustic_db", "label", "rul", "data_origin"
    ]

    # ─── Correspondance dossiers MAFAULDA → étiquettes du projet ──────────────
    # Le dataset MAFAULDA brut (UFRJ) est distribué comme une arborescence de
    # dossiers, un par condition de défaut, contenant chacun des CSV bruts
    # (1 fichier = 1 essai de ~5s à 50kHz). Le nom du dossier de tête encode
    # le défaut ; "overhang" et "underhang" désignent l'emplacement du
    # roulement défectueux (bout libre / bout accouplé), pas un défaut
    # différent → tous deux mappés vers la classe 4 (Roulement).
    MAFAULDA_FOLDER_LABEL_MAP = {
        "normal":                  0,   # Normal
        "imbalance":                1,   # Déséquilibre de masse
        "horizontal-misalignment":  2,   # Désalignement H
        "vertical-misalignment":    3,   # Désalignement V
        "overhang":                 4,   # Roulement (bout libre)
        "underhang":                4,   # Roulement (bout accouplé)
    }

    # Ordre réel des colonnes du CSV brut MAFAULDA (pas d'en-tête dans le fichier).
    # Référence : documentation officielle UFRJ (8 voies, échantillonnées à 50kHz).
    MAFAULDA_COLUMNS = [
        "tachometer",
        "underhang_axial", "underhang_radial", "underhang_tangential",
        "overhang_axial",  "overhang_radial",  "overhang_tangential",
        "microphone",
    ]
    MAFAULDA_SAMPLING_RATE_HZ = 50_000

    # RUL indicatif par défaut (en jours) selon la gravité du défaut
    # En production, le LSTM calculera un RUL précis ; ici c'est un proxy initial.
    DEFAULT_RUL = {0: 365.0, 1: 180.0, 2: 120.0, 3: 90.0, 4: 30.0}

    def __init__(self, raw_dir: str = "data/raw"):
        self.raw_dir = Path(raw_dir)

    # =========================================================================
    # CHARGEMENT CWRU (Case Western Reserve University Bearing Dataset)
    # Fichiers .mat contenant des signaux vibratoires haute fréquence (12 kHz)
    # mesurés sur roulements avec défauts artificiellement créés.
    # =========================================================================

    def load_cwru_file(self, file_name: str) -> pd.DataFrame:
        """
        Charge un fichier .mat CWRU et le convertit au format standard.

        Règle importante : seules les colonnes RÉELLEMENT mesurées dans le fichier
        sont remplies. Les colonnes manquantes (temperature, current...) sont mises
        à NaN — elles seront interpolées ou estimées au niveau L2/L3 du pipeline,
        mais JAMAIS corrélées artificiellement avec le label (pas de bruit biaisé).

        Args:
            file_name: Nom du fichier .mat (ex: "97.mat", "105.mat")

        Returns:
            DataFrame au format standard
        """
        path = self.raw_dir / "cwru" / file_name
        if not path.exists():
            raise FileNotFoundError(f"Fichier CWRU introuvable : {path}")

        logger.info(f"[CWRU] Chargement : {file_name}")

        # Chargement du fichier MATLAB
        mat = loadmat(str(path))

        # ── Extraction des signaux vibratoires ────────────────────────────────
        # CWRU nomme ses clés : X{rpm}_DE_time (Drive End), X{rpm}_FE_time (Fan End)
        # DE = côté commande (plus proche du défaut), FE = côté ventilateur
        de_key = [k for k in mat.keys() if "DE_time" in k]
        fe_key = [k for k in mat.keys() if "FE_time" in k]
        ba_key = [k for k in mat.keys() if "BA_time" in k]  # Base Accelerometer (rare)

        if not de_key:
            raise ValueError(f"Pas de signal Drive End (DE_time) dans {file_name}")

        # Signal vibratoire principal : axe X = Drive End
        v_x = mat[de_key[0]].ravel()
        n_samples = len(v_x)

        # Signal axe Y = Fan End si disponible, sinon zéro (PAS de bruit biaisé !)
        v_y = mat[fe_key[0]].ravel() if fe_key else np.zeros(n_samples)
        # Axe Z = Base si disponible, sinon zéro
        v_z = mat[ba_key[0]].ravel() if ba_key else np.zeros(n_samples)

        # Aligner les longueurs si les axes ont des tailles différentes
        n = min(len(v_x), len(v_y), len(v_z))
        v_x, v_y, v_z = v_x[:n], v_y[:n], v_z[:n]

        # ── Détermination du label (type de défaut) ───────────────────────────
        # CWRU ne contient que des défauts de roulement (piste intérieure,
        # bille, piste extérieure) → tous mappés vers la classe 4 (Roulement),
        # seuls 97-100 sont la référence saine (voir _infer_cwru_label).
        label_val = self._infer_cwru_label(file_name)

        # RUL initial selon le type de défaut
        rul_val = self.DEFAULT_RUL.get(label_val, 180.0)

        # ── Construction du DataFrame standardisé ─────────────────────────────
        df = pd.DataFrame({
            "motor_id":    f"CWRU_{file_name.replace('.mat', '')}",
            "vibration_x": v_x,
            "vibration_y": v_y,
            "vibration_z": v_z,
            # Colonnes non disponibles dans CWRU → NaN (jamais de valeurs inventées !)
            "temperature": np.nan,
            "current":     np.nan,
            "voltage":     np.nan,
            "acoustic_db": np.nan,
            "label":       label_val,
            "rul":         rul_val,
            "data_origin": "CWRU",
        })

        # Timestamps à 12 kHz (fréquence d'échantillonnage réelle de CWRU)
        # "83U" = période de ~83 microsecondes = ~12 kHz
        df["timestamp"] = pd.date_range(
            start=pd.Timestamp("2024-01-01"),
            periods=n,
            freq="83us"   # ~12 kHz
        )

        logger.info(
            f"[CWRU] {file_name} → {n:,} échantillons | "
            f"label={label_val} | v_x=[{v_x.min():.3f}, {v_x.max():.3f}]"
        )
        return df

    # Fichiers de référence saine (baseline) du Bearing Data Center CWRU : 4 charges
    # (0/1/2/3 hp), aucun défaut. Tout le reste du dataset (piste intérieure, bille,
    # piste extérieure, quelle que soit la taille du défaut ou la fréquence
    # d'échantillonnage) est un défaut de roulement.
    CWRU_NORMAL_FILES = {"97", "98", "99", "100"}

    @staticmethod
    def _infer_cwru_label(file_name: str) -> int:
        """
        Détermine le type de défaut depuis le nom de fichier CWRU.

        CORRECTION : la version précédente répartissait les défauts CWRU (piste
        intérieure / bille / piste extérieure) sur les classes 1 (Déséquilibre)
        et 2 (Désalignement H) du projet — en plus d'inverser piste
        intérieure/bille par rapport à la convention réelle CWRU (105-108 =
        piste intérieure, 118-121 = bille, pas l'inverse). Cette répartition
        était un proxy artificiel : CWRU ne contient AUCUN défaut de
        déséquilibre ou de désalignement, uniquement des défauts de roulement
        sous 3 formes. Les faire passer pour du déséquilibre/désalignement
        aurait pollué ces classes avec des signatures de roulement mal
        étiquetées, alors que MAFAULDA fournit déjà de vrais échantillons
        déséquilibre/désalignement. Ici, tout défaut CWRU (quel qu'il soit)
        → classe 4 (Roulement), la seule où CWRU est réellement pertinent.

        Retourne : 0=Normal, 4=Roulement (piste intérieure, bille ou piste extérieure)
        """
        name = file_name.lower().replace(".mat", "")
        if "normal" in name or name in DatasetLoader.CWRU_NORMAL_FILES:
            return 0   # Normal
        return 4   # Tout défaut CWRU → Roulement (seule classe pertinente pour ce dataset)

    # =========================================================================
    # CHARGEMENT MAFAULDA (Machinery Fault Database - UFRJ Brésil)
    #
    # Format réel du dataset brut : une arborescence de dossiers par condition
    # (data/raw/mafaulda/<defaut>/[<severite>/]*.csv), chaque CSV étant un essai
    # de ~5s à 50kHz, 8 colonnes SANS en-tête (voir MAFAULDA_COLUMNS).
    # 1 fichier = 1 essai = 1 "moteur" au sens du split _split_by_motor du trainer
    # (chaque essai est indépendant → aucune fuite entre fichiers train/test).
    # =========================================================================

    def iter_mafaulda_files(self, max_files_per_class: Optional[int] = None) -> list[tuple[Path, int]]:
        """
        Parcourt l'arborescence MAFAULDA et associe chaque CSV à son label.

        Args:
            max_files_per_class: Si fourni, plafonne le nombre de fichiers
                conservés PAR CLASSE FINALE (0-4), pas par dossier. Comme
                "overhang" et "underhang" partagent la classe 4, la limite
                s'applique à leur total combiné (évite un déséquilibre encore
                pire que celui déjà présent dans le dataset).

        Returns:
            Liste de tuples (chemin_csv, label) triée pour être reproductible.
        """
        mafaulda_dir = self.raw_dir / "mafaulda"
        if not mafaulda_dir.exists():
            raise FileNotFoundError(f"Dossier MAFAULDA introuvable : {mafaulda_dir}")

        files_by_label: dict[int, list[Path]] = {}
        for folder_name, label in self.MAFAULDA_FOLDER_LABEL_MAP.items():
            folder = mafaulda_dir / folder_name
            if not folder.exists():
                continue
            files_by_label.setdefault(label, []).extend(sorted(folder.rglob("*.csv")))

        selected: list[tuple[Path, int]] = []
        for label, paths in sorted(files_by_label.items()):
            if max_files_per_class is not None:
                paths = paths[:max_files_per_class]
            selected.extend((p, label) for p in paths)

        if not selected:
            raise FileNotFoundError(
                f"Aucun CSV MAFAULDA trouvé sous {mafaulda_dir} "
                f"(dossiers attendus : {list(self.MAFAULDA_FOLDER_LABEL_MAP)})"
            )
        return selected

    def load_mafaulda_files(
        self,
        max_files_per_class: Optional[int] = None,
        max_seconds: Optional[float] = None,
    ):
        """
        Charge les essais MAFAULDA un par un et les convertit au format standard.

        Args:
            max_files_per_class: Voir iter_mafaulda_files (contrôle le volume total —
                chaque fichier fait ~250 000 lignes brutes, le dataset complet
                (~1 950 fichiers) représente ~490M lignes avant nettoyage).
            max_seconds: Si fourni, tronque chaque essai aux N premières secondes
                (utile pour réduire encore le volume ; les essais durent 5s réel).

        Yields:
            DataFrame au format standard (un essai à la fois).
        """
        for csv_path, label in self.iter_mafaulda_files(max_files_per_class):
            yield self._load_mafaulda_file(csv_path, label, max_seconds)

    def _load_mafaulda_file(self, csv_path: Path, label: int, max_seconds: Optional[float] = None) -> pd.DataFrame:
        """Charge et standardise UN essai MAFAULDA (1 CSV brut sans en-tête)."""
        nrows = int(max_seconds * self.MAFAULDA_SAMPLING_RATE_HZ) if max_seconds else None
        raw = pd.read_csv(csv_path, header=None, names=self.MAFAULDA_COLUMNS, nrows=nrows)
        n = len(raw)

        # Identifiant unique = chemin relatif (préserve la traçabilité défaut/sévérité)
        rel = csv_path.relative_to(self.raw_dir / "mafaulda").with_suffix("")
        motor_id = f"MAFAULDA_{'_'.join(rel.parts)}"

        rul_val = self.DEFAULT_RUL.get(label, 180.0)

        # ── Choix des axes de vibration ────────────────────────────────────────
        # MAFAULDA fournit 2 accéléromètres 3 axes (underhang + overhang) alors
        # que le format standard n'a que 3 axes (comme l'ESP32 réel). On retient
        # l'accéléromètre "overhang" (bout libre, le plus proche de l'arbre moteur)
        # pour les 3 axes, de façon cohérente sur tout le dataset — y compris les
        # essais "underhang" où le défaut est physiquement sur l'autre roulement
        # (signal encore mesurable, juste transmis à travers la structure, comme
        # ce serait le cas avec un unique accéléromètre ESP32 monté à un endroit fixe).
        df = pd.DataFrame({
            "motor_id":    motor_id,
            "vibration_x": raw["overhang_axial"].values,
            "vibration_y": raw["overhang_radial"].values,
            "vibration_z": raw["overhang_tangential"].values,
            "temperature": np.nan,   # Non mesuré par MAFAULDA
            "current":     np.nan,   # Non mesuré par MAFAULDA
            "voltage":     np.nan,   # Non mesuré par MAFAULDA
            # Microphone MAFAULDA = amplitude brute (V), pas du dB calibré ;
            # conservé tel quel comme seul proxy acoustique disponible.
            "acoustic_db": raw["microphone"].values,
            "label":       label,
            "rul":         rul_val,
            "data_origin": "MAFAULDA",
        })

        df["timestamp"] = pd.date_range(
            start=pd.Timestamp("2024-01-01"),
            periods=n,
            freq=pd.Timedelta(seconds=1 / self.MAFAULDA_SAMPLING_RATE_HZ),
        )

        logger.debug(f"[MAFAULDA] {motor_id} → {n:,} échantillons | label={label}")
        return df

    # =========================================================================
    # DONNÉES SYNTHÉTIQUES (utilisées comme fallback si les datasets réels
    # sont absents, ou pour valider le pipeline sans données externes)
    # =========================================================================

    def generate_synthetic(
        self,
        n_motors: int = 5,
        duration_hours: float = 2.0,
        sampling_rate_hz: int = 100,
    ) -> pd.DataFrame:
        """
        Génère des données de moteurs simulés avec une dégradation progressive.

        Modèle physique simplifié :
        - La vibration augmente progressivement à mesure que le moteur se dégrade
        - La température monte légèrement avec la dégradation
        - Le courant augmente quand le moteur force

        Args:
            n_motors: Nombre de moteurs à simuler
            duration_hours: Durée simulée par moteur (en heures)
            sampling_rate_hz: Fréquence d'échantillonnage (Hz)

        Returns:
            DataFrame au format standard
        """
        logger.info(f"[SYNTHETIC] Génération : {n_motors} moteurs × {duration_hours}h @ {sampling_rate_hz}Hz")

        n_samples = int(duration_hours * 3600 * sampling_rate_hz)
        # Période entre deux échantillons en microsecondes (ex: 100Hz → 10000µs)
        freq_str = f"{int(1e6 / sampling_rate_hz)}us"

        all_dfs = []
        rng = np.random.default_rng(seed=42)

        for motor_idx in range(n_motors):
            # ── Choix du type de défaut de ce moteur (classes 0–4) ───────────
            # Répartition réaliste : ~40% Normal, ~15% par type de panne
            label = rng.choice([0, 0, 1, 2, 3, 4], p=[0.40, 0.10, 0.15, 0.15, 0.15, 0.05])

            motor_id = f"SYNTH_m{motor_idx:03d}_lbl{label}"

            # ── Courbe de dégradation (0→1 sur la durée) ─────────────────────
            # Les moteurs "Normal" (label=0) ont une dégradation quasi nulle
            degradation = np.linspace(0.0, 0.2 if label == 0 else 1.0, n_samples)

            # ── Signaux capteurs avec physique simplifiée ─────────────────────
            # Vibration : bruit blanc + harmoniques qui augmentent avec la dégradation
            base_vib = 0.05 + 0.5 * degradation
            t = np.arange(n_samples) / sampling_rate_hz
            # Fréquence de rotation : 50 Hz (3000 RPM)
            rotation_freq = 50.0
            harmonic = 0.3 * degradation * np.sin(2 * np.pi * rotation_freq * t)
            vib_x = base_vib * rng.standard_normal(n_samples) + harmonic
            vib_y = 0.7 * base_vib * rng.standard_normal(n_samples)
            vib_z = 0.5 * base_vib * rng.standard_normal(n_samples)

            # Température : monte de ~25°C à ~75°C selon dégradation
            temp = 25.0 + 50.0 * degradation + rng.normal(0, 1.0, n_samples)

            # Courant : légèrement plus élevé quand le moteur force
            current = 5.0 + 3.0 * degradation + rng.normal(0, 0.2, n_samples)

            # Tension : quasi constante (variation secteur ±5V)
            voltage = 220.0 + rng.normal(0, 2.0, n_samples)

            # Acoustique : monte avec la dégradation
            acoustic = 55.0 + 25.0 * degradation + rng.normal(0, 2.0, n_samples)

            # RUL décroissant de DEFAULT_RUL[label] vers 0
            rul_start = self.DEFAULT_RUL.get(label, 180.0)
            rul = np.linspace(rul_start, 0.0, n_samples)

            df = pd.DataFrame({
                "timestamp":    pd.date_range("2024-01-01", periods=n_samples, freq=freq_str),
                "motor_id":     motor_id,
                "temperature":  temp,
                "vibration_x":  vib_x,
                "vibration_y":  vib_y,
                "vibration_z":  vib_z,
                "current":      current,
                "voltage":      voltage,
                "acoustic_db":  acoustic,
                "label":        label,
                "rul":          rul,
                "data_origin":  "synthetic",
            })

            all_dfs.append(df)
            logger.debug(f"  Moteur {motor_id}: label={label}, {n_samples:,} échantillons")

        combined = pd.concat(all_dfs, ignore_index=True)
        logger.info(f"[SYNTHETIC] {len(combined):,} lignes générées pour {n_motors} moteurs")
        return combined


# =============================================================================
# TEST LOCAL — lancé avec : python src/ingestion/dataset_loader.py
# =============================================================================

if __name__ == "__main__":
    loader = DatasetLoader(raw_dir="data/raw")

    # ── Test 1 : Données synthétiques (toujours disponibles) ─────────────────
    print("\n=== TEST 1 : Données synthétiques ===")
    df_synth = loader.generate_synthetic(n_motors=3, duration_hours=0.1, sampling_rate_hz=100)
    print(df_synth[["motor_id", "temperature", "vibration_x", "label", "rul"]].head())
    print(f"Shape : {df_synth.shape} | Labels : {df_synth['label'].value_counts().to_dict()}")

    # ── Test 2 : CWRU (nécessite les fichiers .mat dans data/raw/cwru/) ───────
    print("\n=== TEST 2 : CWRU ===")
    for fname in ["97.mat", "105.mat", "118.mat"]:
        try:
            df = loader.load_cwru_file(fname)
            print(f"  {fname}: {len(df):,} lignes | label={df['label'].iloc[0]} | v_x_rms={df['vibration_x'].std():.4f}")
        except FileNotFoundError:
            print(f"  {fname}: non trouvé (normal si le fichier n'est pas encore présent)")

    # ── Test 3 : MAFAULDA (nécessite l'arborescence brute dans data/raw/mafaulda/) ─
    print("\n=== TEST 3 : MAFAULDA (2 premiers essais par classe) ===")
    try:
        gen = loader.load_mafaulda_files(max_files_per_class=2)
        for df in gen:
            print(
                f"  {df['motor_id'].iloc[0]}: {len(df):,} lignes | "
                f"label={df['label'].iloc[0]} | v_x_rms={df['vibration_x'].std():.4f}"
            )
    except FileNotFoundError as e:
        print(f"  {e}")
