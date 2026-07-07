# =============================================================================
# src/cleaning/pipeline.py
#
# Pipeline de nettoyage des données en 3 niveaux :
#
#   NIVEAU 1 — Level1Cleaner
#       Nettoyage brut : valeurs physiquement impossibles, doublons,
#       NaN, outliers statistiques (6σ).
#       → Sortie : mêmes colonnes, données fiabilisées
#
#   NIVEAU 2 — Level2Cleaner
#       Structuration : rééchantillonnage à fréquence cible (100 Hz),
#       interpolation des trous, alignement temporel par moteur.
#       → Sortie : série temporelle régulière et synchronisée
#
#   NIVEAU 3 — Level3FeatureEngineer
#       Feature engineering : découpage en fenêtres glissantes + extraction
#       de ~80 features (domaine temporel, fréquentiel, cross-capteurs, rolling).
#       → Sortie : tableau features ML-ready (1 ligne = 1 fenêtre de signal)
#
#   ORCHESTRATEUR — CleaningPipeline
#       Enchaîne les 3 niveaux. Compatible batch ET streaming (ESP32).
# =============================================================================

import numpy as np                          # Calculs numériques vectorisés
import pandas as pd                         # Manipulation des DataFrames
from scipy import signal, stats             # Traitement du signal + statistiques
from scipy.fft import fft, fftfreq          # Transformée de Fourier rapide
from typing import Optional                 # Type hint : valeur potentiellement None
from loguru import logger                   # Logs colorés et détaillés
from dataclasses import dataclass, field    # Classes légères pour les rapports


# =============================================================================
# RAPPORT DE NETTOYAGE — Trace ce qui s'est passé à chaque niveau
# =============================================================================

@dataclass
class CleaningReport:
    """
    Résumé statistique d'une passe de nettoyage.
    Permet de vérifier que le pipeline n'a pas supprimé trop de données
    et de diagnostiquer les problèmes courants (trop de NaN, outliers...).
    """
    level: int                                 # Numéro du niveau (1, 2 ou 3)
    input_rows: int                            # Nombre de lignes à l'entrée
    output_rows: int = 0                       # Nombre de lignes à la sortie
    dropped_rows: int = 0                      # Nombre de lignes supprimées
    flagged_rows: int = 0                      # Nombre de lignes marquées (anomalies)
    interpolated_points: int = 0               # Nombre de points interpolés (L2)
    issues: list = field(default_factory=list) # Liste des problèmes rencontrés

    @property
    def retention_rate(self) -> float:
        """Taux de rétention = lignes conservées / lignes initiales.
        Idéalement > 95%. En dessous de 80%, investiguer les issues."""
        return self.output_rows / max(self.input_rows, 1)


# =============================================================================
# NIVEAU 1 — Nettoyage brut
# =============================================================================

class Level1Cleaner:
    """
    Nettoyage des données telles qu'elles arrivent (ESP32 ou CSV brut).

    Étapes :
      1. Validation des timestamps (génération si absents, suppression si invalides)
      2. Suppression des doublons (même timestamp + même motor_id)
      3. Remplacement des valeurs hors bornes physiques par NaN
      4. Gestion des NaN (stratégie configurable : drop / interpolate / flag)
      5. Marquage des outliers statistiques (> 6σ de la moyenne)
    """

    # Bornes physiques réalistes pour chaque type de capteur.
    # Une valeur hors de ces plages EST physiquement impossible → remplacée par NaN.
    PHYSICAL_BOUNDS = {
        "temperature":  (-20.0, 300.0),    # -20°C (gel) à 300°C (max moteur industriel)
        "vibration_x":  (-50.0, 50.0),     # en g (accélération gravitationnelle)
        "vibration_y":  (-50.0, 50.0),     # en g
        "vibration_z":  (-50.0, 50.0),     # en g
        "current":      (-5.0,  100.0),    # Ampères (négatif = mesure bruit, 100A = surcharge max)
        "voltage":      (0.0,   500.0),    # Volts (0V = hors tension, 500V = max industriel)
        "acoustic_db":  (0.0,   140.0),    # dB (0 = silence absolu, 140 = seuil douleur)
    }

    SENSOR_COLS = list(PHYSICAL_BOUNDS.keys())

    def __init__(self, null_strategy: str = "flag"):
        """
        Args:
            null_strategy: Stratégie de gestion des NaN
                - "flag"        : marquer sans supprimer, interpolation légère (défaut)
                - "drop"        : supprimer toutes les lignes avec au moins un NaN
                - "interpolate" : interpolation linéaire jusqu'à 10 points consécutifs
        """
        if null_strategy not in ("flag", "drop", "interpolate"):
            raise ValueError(f"null_strategy invalide : {null_strategy}")
        self.null_strategy = null_strategy

    def clean(self, df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
        """
        Point d'entrée principal du Level 1.

        Args:
            df: DataFrame brut au format standard

        Returns:
            (DataFrame nettoyé, Rapport détaillé)
        """
        report = CleaningReport(level=1, input_rows=len(df))
        df = df.copy()  # Ne jamais modifier l'original

        # Étape 1 : Valider et normaliser la colonne timestamp
        df = self._validate_timestamps(df, report)

        # Étape 2 : Supprimer les doublons stricts (même timestamp + même motor_id)
        before = len(df)
        df = df.drop_duplicates(subset=["timestamp", "motor_id"])
        dup_dropped = before - len(df)
        if dup_dropped > 0:
            report.issues.append(f"Doublons supprimés : {dup_dropped}")
            report.dropped_rows += dup_dropped

        # Trier par moteur puis par temps pour garantir l'ordre chronologique
        df = df.sort_values(["motor_id", "timestamp"]).reset_index(drop=True)

        # Étape 3 : Remplacer les valeurs hors bornes physiques par NaN
        df, phy_report, oob_masks = self._check_physical_bounds(df)
        report.issues.extend(phy_report)
        # Compter les lignes avec au moins une anomalie physique
        report.flagged_rows += int(df["_out_of_bounds"].sum()) if "_out_of_bounds" in df.columns else 0

        # Étape 4 : Gérer les NaN (stratégie choisie à l'initialisation)
        df, null_report = self._handle_nulls(df, oob_masks)
        report.issues.extend(null_report)

        # Étape 5 : Marquer (sans supprimer) les outliers statistiques extrêmes (> 6σ)
        df = self._flag_statistical_outliers(df, sigma=6.0)

        # Mise à jour du rapport final
        report.output_rows = len(df)
        report.dropped_rows = report.input_rows - report.output_rows

        logger.info(
            f"[L1] {report.input_rows:,} → {report.output_rows:,} lignes "
            f"({report.retention_rate:.1%} conservées) | "
            f"{len(report.issues)} problème(s) détecté(s)"
        )
        return df, report

    def _validate_timestamps(self, df: pd.DataFrame, report: CleaningReport) -> pd.DataFrame:
        """
        Vérifie que la colonne 'timestamp' existe et contient des datetime valides.
        Si absente → génère des timestamps synthétiques à 100 Hz.
        Si invalides → les lignes correspondantes sont supprimées.
        """
        # ╔══════════════════════════════════════════════════════╗
        # ║  CORRECTION BUG : faute de frappe "columblns" → "columns"  ║
        # ╚══════════════════════════════════════════════════════╝
        if "timestamp" not in df.columns:   # ← CORRIGÉ (était "columblns")
            # Timestamps générés toutes les 10ms (100 Hz par défaut)
            df["timestamp"] = pd.date_range("2024-01-01", periods=len(df), freq="10ms")
            report.issues.append("Colonne timestamp absente → générée synthétiquement à 100 Hz")
            return df

        try:
            # Convertit en datetime pandas ; errors="coerce" met NaT si conversion impossible
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False, errors="coerce")
            invalid = df["timestamp"].isna().sum()
            if invalid > 0:
                df = df.dropna(subset=["timestamp"])
                report.issues.append(f"Timestamps invalides supprimés : {invalid}")
        except Exception as e:
            report.issues.append(f"Erreur parsing timestamp : {e}")

        return df

    def _check_physical_bounds(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list, dict]:
        """
        Remplace par NaN toutes les valeurs hors des bornes physiques définies
        dans PHYSICAL_BOUNDS. Ajoute une colonne '_out_of_bounds' (booléen).

        Retourne aussi oob_masks : {colonne: masque booléen des cellules mises
        à NaN par CE contrôle}, pour que _handle_nulls puisse distinguer une
        lecture physiquement impossible d'un NaN naturel (capteur déconnecté,
        trou de transmission...) — cf. CORRECTION dans _handle_nulls.
        """
        issues = []
        oob_masks: dict = {}
        df["_out_of_bounds"] = False

        for col, (lo, hi) in self.PHYSICAL_BOUNDS.items():
            if col not in df.columns:
                continue  # Colonne absente : pas d'erreur, juste on passe

            # Masque booléen : True sur chaque valeur impossible
            mask = (df[col] < lo) | (df[col] > hi)
            n_bad = int(mask.sum())

            if n_bad > 0:
                df.loc[mask, col] = np.nan            # Remplace par NaN
                df.loc[mask, "_out_of_bounds"] = True # Marque la ligne
                oob_masks[col] = mask
                issues.append(f"{col}: {n_bad} valeurs hors bornes (out-of-bounds) [{lo}, {hi}] → NaN")

        return df, issues, oob_masks

    def _handle_nulls(self, df: pd.DataFrame, oob_masks: Optional[dict] = None) -> tuple[pd.DataFrame, list]:
        """
        Gère les NaN selon la stratégie choisie à l'initialisation.
        N'affecte que les colonnes capteurs (pas label, rul, motor_id...).

        Args:
            oob_masks: masques par colonne des cellules mises à NaN par
                _check_physical_bounds (valeurs physiquement impossibles).
        """
        issues = []
        oob_masks = oob_masks or {}

        # Sélectionner seulement les colonnes capteurs présentes
        cols_present = [c for c in self.SENSOR_COLS if c in df.columns]
        null_counts = df[cols_present].isna().sum()
        total_nulls = int(null_counts.sum())

        if total_nulls == 0:
            return df, issues  # Rien à faire

        issues.append(f"NaN détectés : {dict(null_counts[null_counts > 0])}")

        if self.null_strategy == "drop":
            # Supprimer les lignes qui ont au moins un NaN dans les capteurs
            before = len(df)
            df = df.dropna(subset=cols_present)
            issues.append(f"Lignes supprimées (NaN) : {before - len(df)}")

        elif self.null_strategy == "interpolate":
            # Interpolation linéaire sur max 10 points consécutifs, puis bfill/ffill,
            # PAR MOTEUR (voir CORRECTION ci-dessous).
            for col in cols_present:
                df[col] = self._interpolate_per_motor(df, col, limit=10)
                # ╔═══════════════════════════════════════════════════════════╗
                # ║  CORRECTION PANDAS 2.x : .fillna(method=...) est         ║
                # ║  déprécié → utiliser .bfill() et .ffill() directement    ║
                # ╚═══════════════════════════════════════════════════════════╝
                df[col] = df.groupby("motor_id", sort=False)[col].transform(lambda s: s.bfill().ffill())  # ← CORRIGÉ

        elif self.null_strategy == "flag":
            # ╔═══════════════════════════════════════════════════════════════╗
            # ║  CORRECTION BUG : sous "flag", TOUS les NaN (y compris ceux   ║
            # ║  créés par _check_physical_bounds pour des valeurs            ║
            # ║  physiquement impossibles) étaient ré-interpolés → une        ║
            # ║  lecture aberrante (ex: -100g) redevenait une valeur          ║
            # ║  plausible fabriquée, rendant "_out_of_bounds" inutile en     ║
            # ║  pratique (l'anomalie disparaissait silencieusement).         ║
            # ║  Ici on n'interpole que les NaN "naturels" (capteur          ║
            # ║  déconnecté, trou de transmission...) ; les cellules          ║
            # ║  physiquement impossibles restent NaN et donc visibles.       ║
            # ╚═══════════════════════════════════════════════════════════════╝
            df["_has_null"] = df[cols_present].isna().any(axis=1)
            for col in cols_present:
                oob_mask = oob_masks.get(col)
                if oob_mask is None or not oob_mask.any():
                    df[col] = self._interpolate_per_motor(df, col, limit=5)
                    continue

                natural_nan = df[col].isna() & ~oob_mask.reindex(df.index, fill_value=False)
                if natural_nan.any():
                    interpolated = self._interpolate_per_motor(df, col, limit=5)
                    df.loc[natural_nan, col] = interpolated.loc[natural_nan]

        return df, issues

    @staticmethod
    def _interpolate_per_motor(df: pd.DataFrame, col: str, limit: int) -> pd.Series:
        """
        Interpole une colonne PAR MOTEUR plutôt que sur le DataFrame concaténé
        entier.

        CORRECTION : deux problèmes avec `df[col].interpolate(limit=...)` sur
        tout le DataFrame à la fois :
        1. Mémoire — l'implémentation pandas de interpolate(limit=...) a un
           coût qui explose sur de gros volumes (MemoryError observé à ~48M
           lignes réelles CWRU+MAFAULDA), alors que traiter moteur par moteur
           (quelques centaines de milliers de lignes chacun) reste léger.
        2. Correction — les données sont triées par motor_id puis timestamp ;
           un NaN proche d'une frontière entre deux moteurs pouvait être
           interpolé à partir des valeurs du moteur SUIVANT, mélangeant deux
           signaux physiquement indépendants.
        """
        return df.groupby("motor_id", sort=False)[col].transform(
            lambda s: s.interpolate(method="linear", limit=limit)
        )

    def _flag_statistical_outliers(self, df: pd.DataFrame, sigma: float = 6.0) -> pd.DataFrame:
        """
        Marque (sans supprimer) les valeurs statistiquement aberrantes :
        toute valeur à plus de 'sigma' écarts-types de la moyenne est suspecte.
        Un sigma = 6 est très conservateur (ne marque que des anomalies extrêmes).
        """
        df["_statistical_outlier"] = False

        for col in self.SENSOR_COLS:
            if col not in df.columns:
                continue

            mu  = df[col].mean()
            std = df[col].std()

            if std > 0:  # Évite la division par zéro sur colonnes constantes
                mask = (df[col] - mu).abs() > sigma * std
                df.loc[mask, "_statistical_outlier"] = True

        return df


# =============================================================================
# NIVEAU 2 — Structuration temporelle
# =============================================================================

class Level2Cleaner:
    """
    Rend les données cohérentes temporellement avant le feature engineering :
      1. Rééchantillonnage à fréquence fixe (par défaut 100 Hz)
      2. Interpolation des trous (gaps <= max_gap_seconds)
      3. Réintégration des labels et RUL
    
    Traite chaque moteur indépendamment (les moteurs ne sont pas synchronisés).
    """

    # Colonnes capteurs à rééchantillonner (héritées du Level1)
    SENSOR_COLS = Level1Cleaner.SENSOR_COLS

    def __init__(
        self,
        target_hz: int = 100,           # Fréquence cible : 100 Hz (100 pts/s)
        max_gap_seconds: float = 5.0,   # Ne pas interpoler les gaps > 5s (données manquantes trop longues)
        interp_method: str = "linear",  # Méthode d'interpolation (linear est robuste)
    ):
        self.target_hz = target_hz
        # Calcul de la période en chaîne de format pandas (ex: "0.010000s" pour 100Hz)
        self.target_freq = f"{1/target_hz:.6f}s"
        self.max_gap_seconds = max_gap_seconds
        self.interp_method = interp_method

    def clean(self, df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
        """
        Rééchantillonne et aligne les données.
        Chaque moteur est traité séparément (la temporalité est propre à chaque moteur).
        """
        report = CleaningReport(level=2, input_rows=len(df))
        results = []

        # Groupby motor_id : chaque moteur a sa propre chronologie
        for motor_id, group in df.groupby("motor_id"):
            cleaned, n_interp = self._process_motor(group.copy())
            report.interpolated_points += n_interp
            results.append(cleaned)

        df_out = pd.concat(results, ignore_index=True) if results else df.copy()
        report.output_rows = len(df_out)

        logger.info(
            f"[L2] {report.input_rows:,} → {report.output_rows:,} lignes | "
            f"points interpolés : {report.interpolated_points:,}"
        )
        return df_out, report

    def _process_motor(self, df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
        """
        Rééchantillonne les données d'UN moteur.
        
        Retourne (DataFrame rééchantillonné, nombre de points interpolés).
        """
        df = df.sort_values("timestamp")
        motor_id = df["motor_id"].iloc[0] if "motor_id" in df.columns else "unknown"

        # Calculer les écarts temporels entre mesures pour détecter les grands trous
        time_diffs = df["timestamp"].diff().dt.total_seconds()
        df["_large_gap"] = time_diffs.gt(self.max_gap_seconds).fillna(False)

        # Utiliser timestamp comme index pour le resample pandas
        df = df.set_index("timestamp")

        # Sauvegarder label et RUL (doivent être traités différemment des capteurs)
        label_col = df["label"].copy() if "label" in df.columns else None
        rul_col   = df["rul"].copy()   if "rul"   in df.columns else None

        # ── Rééchantillonnage des colonnes capteurs numériques ─────────────────
        numeric_cols = [c for c in self.SENSOR_COLS if c in df.columns]
        df_num = df[numeric_cols].copy()

        # resample().mean() : si plusieurs mesures dans un intervalle → moyenne
        df_resampled = df_num.resample(self.target_freq).mean()

        # Compter les points avant interpolation pour le rapport
        n_before = int(df_resampled.isna().sum().sum())
        # Interpolation linéaire, limitée à max_gap_seconds * target_hz points consécutifs
        df_resampled = df_resampled.interpolate(
            method=self.interp_method,
            limit=int(self.target_hz * self.max_gap_seconds)
        )
        n_interp = n_before - int(df_resampled.isna().sum().sum())

        # Remplir les bords (début/fin de série) avec bfill/ffill
        # ╔══════════════════════════════════════════════════════════════════╗
        # ║  CORRECTION PANDAS 2.x : .fillna(method="bfill") est déprécié  ║
        # ║  → utiliser .bfill() et .ffill() directement                   ║
        # ╚══════════════════════════════════════════════════════════════════╝
        df_resampled = df_resampled.bfill().ffill()   # ← CORRIGÉ

        # Reconstruire les colonnes metadata
        df_resampled = df_resampled.reset_index()
        df_resampled.rename(columns={"index": "timestamp"}, inplace=True)
        df_resampled["motor_id"]    = motor_id
        df_resampled["data_origin"] = df["data_origin"].iloc[0] if "data_origin" in df.columns else "unknown"

        # ── Réintégration du label (prendre le max sur l'intervalle) ──────────
        # Logique : si un seul point dans l'intervalle a un défaut, la fenêtre est défectueuse
        if label_col is not None:
            resampled_label = (
                label_col
                .resample(self.target_freq).max()
                .ffill().fillna(0).astype(int)
            )
            df_resampled["label"] = resampled_label.values[:len(df_resampled)]

        # ── Réintégration du RUL (interpolation par moyenne) ──────────────────
        if rul_col is not None:
            resampled_rul = rul_col.resample(self.target_freq).mean().interpolate()
            df_resampled["rul"] = resampled_rul.values[:len(df_resampled)]

        return df_resampled, int(n_interp)


# =============================================================================
# NIVEAU 3 — Feature Engineering
# =============================================================================

class Level3FeatureEngineer:
    """
    Extrait ~80 features par fenêtre glissante depuis les signaux temporels.
    
    Organisation :
      - Domaine temporel    : RMS, pic, kurtosis, skewness, crest factor...
      - Domaine fréquentiel : FFT, fréquence dominante, puissance par bande...
      - Distorsion courant  : THD (Total Harmonic Distortion)
      - Cross-capteurs      : corrélation vibration/courant, SNR acoustique...
      - Rolling stats       : moyenne/std/max glissants sur 10s, 60s, 300s
    """

    VIB_COLS = ["vibration_x", "vibration_y", "vibration_z"]

    def __init__(
        self,
        window_size: int = 512,      # Taille de la fenêtre : 512 échantillons (à 100Hz = 5.12s)
        overlap: float = 0.5,        # Chevauchement de 50% entre fenêtres consécutives
        sampling_rate: int = 100,    # Fréquence d'échantillonnage (doit correspondre au L2)
        rolling_windows: list = None,
    ):
        self.window_size = window_size
        # Pas entre fenêtres (ex: 50% overlap → step = 256)
        self.step = int(window_size * (1 - overlap))
        self.fs = sampling_rate
        # Fenêtres rolling : 10s (court terme), 60s (moyen terme), 300s (long terme = tendance)
        self.rolling_windows = rolling_windows or [10, 60, 300]

    def extract(self, df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
        """
        Extrait les features pour tous les moteurs du DataFrame.
        Chaque moteur est traité séparément.
        
        Retourne (features_df, rapport) où features_df a 1 ligne par fenêtre.
        """
        report = CleaningReport(level=3, input_rows=len(df))
        results = []

        for motor_id, group in df.groupby("motor_id"):
            features = self._extract_motor_features(group.copy())
            if features is not None:
                results.append(features)

        df_feat = pd.concat(results, ignore_index=True) if results else pd.DataFrame()
        report.output_rows = len(df_feat)

        n_feat = len(df_feat.columns) if not df_feat.empty else 0
        logger.info(
            f"[L3] {report.input_rows:,} échantillons → {report.output_rows:,} fenêtres "
            f"({n_feat} features par fenêtre)"
        )
        return df_feat, report

    def _extract_motor_features(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """
        Découpe les données d'un moteur en fenêtres glissantes et extrait les features.
        Retourne None si le moteur n'a pas assez de données pour une fenêtre complète.
        """
        if len(df) < self.window_size:
            logger.debug(f"  Moteur {df['motor_id'].iloc[0]}: trop peu de données ({len(df)} < {self.window_size})")
            return None

        windows = []
        n = len(df)

        # Découpage avec chevauchement : fenêtres [0:512], [256:768], [512:1024]...
        for start in range(0, n - self.window_size + 1, self.step):
            end = start + self.window_size
            window = df.iloc[start:end]
            feats = self._extract_window(window)
            windows.append(feats)

        return pd.DataFrame(windows)

    def _extract_window(self, w: pd.DataFrame) -> dict:
        """
        Calcule toutes les features pour UNE fenêtre de signal.
        Retourne un dictionnaire {nom_feature: valeur}.
        """
        feats = {
            "motor_id":    w["motor_id"].iloc[0],
            # Timestamp du milieu de la fenêtre (représentatif de la fenêtre)
            "timestamp":   w["timestamp"].iloc[self.window_size // 2],
            "data_origin": w["data_origin"].iloc[0] if "data_origin" in w.columns else "unknown",
        }

        # ── Features domaine temporel pour chaque axe de vibration ────────────
        for col in self.VIB_COLS:
            if col in w.columns:
                feats.update(self._time_domain_features(w[col].values, prefix=col))

        # ── Features spécifiques par type de capteur ──────────────────────────
        if "temperature" in w.columns and w["temperature"].notna().any():
            feats.update(self._temperature_features(w["temperature"].dropna().values))

        if "current" in w.columns and w["current"].notna().any():
            feats.update(self._current_features(w["current"].dropna().values))

        if "acoustic_db" in w.columns and w["acoustic_db"].notna().any():
            feats.update(self._acoustic_features(w["acoustic_db"].dropna().values))

        # ── Features domaine fréquentiel (FFT) ────────────────────────────────
        for col in self.VIB_COLS:
            if col in w.columns:
                feats.update(self._freq_domain_features(w[col].values, prefix=col))

        # ── Distorsion harmonique du courant (THD) ────────────────────────────
        if "current" in w.columns and w["current"].notna().any():
            feats.update(self._thd_feature(w["current"].dropna().values))

        # ── Features cross-capteurs (corrélations inter-signaux) ──────────────
        feats.update(self._cross_sensor_features(w))

        # ── Features rolling (tendances sur différentes échelles de temps) ────
        feats.update(self._rolling_features(w))

        # ── Labels (target pour l'entraînement) ───────────────────────────────
        if "label" in w.columns:
            feats["label"] = int(w["label"].mode()[0])  # label le plus fréquent dans la fenêtre
        if "rul" in w.columns:
            feats["rul"] = float(w["rul"].mean())        # RUL moyen de la fenêtre

        return feats

    # ─── Domaine temporel ─────────────────────────────────────────────────────

    def _time_domain_features(self, x: np.ndarray, prefix: str) -> dict:
        """
        Features statistiques dans le domaine temps :
        - RMS (Root Mean Square) : mesure la puissance globale du signal
        - Peak / Peak-to-peak    : mesure l'amplitude maximale
        - Kurtosis               : détecte les pics impulsionnels (défauts de roulement)
        - Skewness               : asymétrie de la distribution (déséquilibre)
        - Crest Factor           : ratio peak/RMS, augmente avant une panne
        - Shape / Impulse Factor : indicateurs de forme du signal
        - ZCR (Zero Crossing Rate) : approximation de la fréquence dominante
        """
        rms      = np.sqrt(np.mean(x ** 2))
        peak     = np.max(np.abs(x))
        mean_abs = np.mean(np.abs(x))
        std      = np.std(x)
        eps      = 1e-10  # Évite les divisions par zéro

        return {
            f"{prefix}_rms":            rms,
            f"{prefix}_peak":           peak,
            f"{prefix}_peak_to_peak":   np.ptp(x),           # max - min
            f"{prefix}_mean":           np.mean(x),
            f"{prefix}_std":            std,
            f"{prefix}_variance":       np.var(x),
            f"{prefix}_kurtosis":       stats.kurtosis(x),   # >3 = signal impulsionnel
            f"{prefix}_skewness":       stats.skew(x),       # asymétrie
            f"{prefix}_crest_factor":   peak / (rms + eps),  # >6 = alerte roulement
            f"{prefix}_shape_factor":   rms / (mean_abs + eps),
            f"{prefix}_impulse_factor": peak / (mean_abs + eps),
            f"{prefix}_zcr":            float(np.mean(np.diff(np.sign(x)) != 0)),
        }

    def _temperature_features(self, temp: np.ndarray) -> dict:
        """
        Features de température :
        - mean/std/max : statistiques de base
        - delta        : différence entre fin et début de fenêtre (tendance)
        - trend        : pente de la droite de régression linéaire (montée/descente)
        """
        return {
            "temp_mean":  float(np.mean(temp)),
            "temp_std":   float(np.std(temp)),
            "temp_max":   float(np.max(temp)),
            "temp_delta": float(temp[-1] - temp[0]),                            # Variation absolue
            "temp_trend": float(np.polyfit(np.arange(len(temp)), temp, 1)[0]), # Pente linéaire
        }

    def _current_features(self, curr: np.ndarray) -> dict:
        """
        Features du courant électrique.
        Une augmentation du RMS et du facteur de crête indique une surcharge.
        """
        rms = np.sqrt(np.mean(curr ** 2))
        return {
            "current_rms":  float(rms),
            "current_mean": float(np.mean(curr)),
            "current_std":  float(np.std(curr)),
            "current_peak": float(np.max(np.abs(curr))),
            "current_cf":   float(np.max(np.abs(curr)) / (rms + 1e-10)),  # Crest factor
        }

    def _acoustic_features(self, db: np.ndarray) -> dict:
        """
        Features acoustiques. Une hausse du niveau sonore peut indiquer
        des frottements, du jeu mécanique ou un défaut de roulement.
        """
        return {
            "acoustic_mean": float(np.mean(db)),
            "acoustic_std":  float(np.std(db)),
            "acoustic_max":  float(np.max(db)),
            "acoustic_p95":  float(np.percentile(db, 95)),  # 95ème percentile
        }

    # ─── Domaine fréquentiel ──────────────────────────────────────────────────

    def _freq_domain_features(self, x: np.ndarray, prefix: str) -> dict:
        """
        Features spectrales via FFT (Fast Fourier Transform) :
        - Fréquence dominante  : la fréquence avec la plus grande amplitude
        - Centroïde spectral   : "centre de gravité" du spectre (monte avec les défauts)
        - Spectral spread      : largeur du spectre (plus large = signal plus complexe)
        - Rolloff              : fréquence où 85% de l'énergie est atteinte
        - Flux spectral        : variation entre bins fréquentiels (instabilité)
        - Puissance par bandes : énergie dans 3 bandes (basses / moyennes / hautes)
        """
        n = len(x)
        # Fréquences de 0 à fs/2 (théorème de Nyquist : on ne peut mesurer que jusqu'à fs/2)
        freqs    = fftfreq(n, d=1 / self.fs)[:n // 2]
        spectrum = np.abs(fft(x))[:n // 2]  # Amplitude du spectre (partie positive)
        ps       = spectrum ** 2            # Spectre de puissance
        total_power = ps.sum() + 1e-10      # Évite division par zéro

        dominant_idx  = np.argmax(spectrum)
        spectral_mean = np.sum(freqs * ps) / total_power  # Centroïde = moment d'ordre 1

        def band_power(lo: float, hi: float) -> float:
            """Fraction de l'énergie totale dans la bande [lo, hi] Hz."""
            mask = (freqs >= lo) & (freqs < hi)
            return float(ps[mask].sum() / total_power)

        return {
            f"{prefix}_dominant_freq":     float(freqs[dominant_idx]),
            f"{prefix}_dominant_amp":      float(spectrum[dominant_idx]),
            f"{prefix}_spectral_centroid": float(spectral_mean),
            f"{prefix}_spectral_spread":   float(
                np.sqrt(np.sum((freqs - spectral_mean) ** 2 * ps) / total_power)
            ),
            f"{prefix}_spectral_rolloff":  float(self._spectral_rolloff(freqs, ps, 0.85)),
            f"{prefix}_spectral_flux":     float(np.sum(np.diff(spectrum) ** 2)),
            # Puissance par bandes fréquentielles
            f"{prefix}_bp_0_500":          band_power(0, 500),
            f"{prefix}_bp_500_2k":         band_power(500, 2000),
            f"{prefix}_bp_2k_5k":          band_power(2000, 5000),
        }

    def _thd_feature(self, current: np.ndarray) -> dict:
        """
        THD (Total Harmonic Distortion — Distorsion Harmonique Totale).
        
        Mesure la part des harmoniques (multiples de 50 Hz) par rapport
        à la fréquence fondamentale (50 Hz = fréquence du réseau électrique).
        Un THD élevé indique un défaut électrique (rotor excentrique, court-circuit...).
        
        THD = √(H2² + H3² + H4² + H5²) / H1
        où Hn = amplitude à n × 50 Hz
        """
        n = len(current)
        if n < 4:  # Pas assez de points pour une FFT significative
            return {"current_thd": 0.0}

        freqs    = fftfreq(n, d=1 / self.fs)[:n // 2]
        spectrum = np.abs(fft(current))[:n // 2]

        # Amplitude à la fondamentale 50 Hz
        f0_idx = np.argmin(np.abs(freqs - 50))
        f0_amp = spectrum[f0_idx]

        # Amplitudes aux harmoniques 2 à 5 (100, 150, 200, 250 Hz)
        harmonic_amps = [
            spectrum[np.argmin(np.abs(freqs - 50 * h))]
            for h in range(2, 6)
        ]

        thd = np.sqrt(sum(a ** 2 for a in harmonic_amps)) / (f0_amp + 1e-10)
        return {"current_thd": float(thd)}

    @staticmethod
    def _spectral_rolloff(freqs: np.ndarray, power_spectrum: np.ndarray, threshold: float = 0.85) -> float:
        """
        Fréquence de rolloff : plus petite fréquence f telle que
        l'énergie cumulée jusqu'à f représente 'threshold' (85%) de l'énergie totale.
        """
        cumsum      = np.cumsum(power_spectrum)
        rolloff_idx = np.searchsorted(cumsum, threshold * cumsum[-1])
        return float(freqs[min(rolloff_idx, len(freqs) - 1)])

    # ─── Cross-capteurs ───────────────────────────────────────────────────────

    def _cross_sensor_features(self, w: pd.DataFrame) -> dict:
        """
        Features calculées en croisant plusieurs capteurs :
        - Corrélation vibration/courant : haute corrélation → la vibration est
          mécaniquement liée à la charge électrique (normal) ; si découplée → anomalie
        - RMS vibration total (3 axes combinés) : mesure globale de la sévérité
        - SNR acoustique : rapport signal/bruit acoustique
        - Puissance apparente : produit courant × tension
        """
        feats = {}

        # Corrélation entre vibration axe X et courant (si les deux existent)
        if "vibration_x" in w.columns and "current" in w.columns:
            vx = w["vibration_x"].dropna().values
            ic = w["current"].dropna().values
            n  = min(len(vx), len(ic))
            if n > 2:
                feats["corr_vib_current"] = float(np.corrcoef(vx[:n], ic[:n])[0, 1])

        # RMS total vibratoire (norme des 3 axes)
        vib_cols_ok = [c for c in self.VIB_COLS if c in w.columns and w[c].notna().any()]
        if vib_cols_ok:
            feats["vibration_total_rms"] = float(
                np.sqrt(sum(np.nanmean(w[c].values ** 2) for c in vib_cols_ok))
            )

        # SNR acoustique estimé : signal_power - plancher de bruit (10ème percentile)
        if "acoustic_db" in w.columns and w["acoustic_db"].notna().any():
            db = w["acoustic_db"].dropna().values
            feats["acoustic_snr"] = float(np.mean(db) - np.percentile(db, 10))

        # Puissance apparente (VA) : moyenne courant × moyenne tension
        if "current" in w.columns and "voltage" in w.columns:
            ic_mean = w["current"].mean()
            vt_mean = w["voltage"].mean()
            if pd.notna(ic_mean) and pd.notna(vt_mean):
                feats["apparent_power"] = float(ic_mean * vt_mean)

        return feats

    # ─── Rolling stats ────────────────────────────────────────────────────────

    def _rolling_features(self, w: pd.DataFrame) -> dict:
        """
        Statistiques glissantes sur différentes échelles de temps.
        Capturent les tendances à court terme (10s), moyen terme (60s) et long terme (300s).
        Cruciales pour le LSTM qui raisonne sur l'évolution temporelle.
        """
        feats = {}
        # On ne calcule le rolling que sur les 3 colonnes les plus informatives
        key_cols = {
            "vibration_x": "vib",   # Signal mécanique principal
            "temperature":  "temp", # Thermique
            "current":      "cur",  # Électrique
        }

        for col, short in key_cols.items():
            if col not in w.columns:
                continue
            arr = w[col].dropna().values
            if len(arr) == 0:
                continue

            for win_s in self.rolling_windows:
                # Nombre de points dans la fenêtre (ex: 60s × 100Hz = 6000 pts)
                win_pts = min(int(win_s * self.fs), len(arr))
                window_data = arr[-win_pts:]  # Les win_pts derniers points

                feats[f"{short}_roll_{win_s}s_mean"] = float(np.mean(window_data))
                feats[f"{short}_roll_{win_s}s_std"]  = float(np.std(window_data))
                feats[f"{short}_roll_{win_s}s_max"]  = float(np.max(window_data))

        return feats


# =============================================================================
# ORCHESTRATEUR — Enchaîne les 3 niveaux
# =============================================================================

class CleaningPipeline:
    """
    Orchestre les 3 niveaux de nettoyage dans l'ordre : L1 → L2 → L3.
    
    Deux modes d'utilisation :
      - Batch    : pipeline.run(df)               → entraînement, données historiques
      - Streaming: pipeline.run_single_window(w)  → ESP32 temps réel
    """

    def __init__(self, config: dict = None):
        cfg    = config or {}
        l1_cfg = cfg.get("level1", {})
        l2_cfg = cfg.get("level2", {})
        l3_cfg = cfg.get("level3", {})

        # Instantiation des 3 niveaux avec leurs paramètres respectifs
        self.l1 = Level1Cleaner(null_strategy=l1_cfg.get("null_strategy", "flag"))
        self.l2 = Level2Cleaner(
            target_hz       = l2_cfg.get("resample_hz",     100),
            max_gap_seconds = l2_cfg.get("max_gap_seconds", 5.0),
        )
        self.l3 = Level3FeatureEngineer(
            window_size   = l3_cfg.get("window_size",  512),
            overlap       = l3_cfg.get("overlap",      0.5),
            sampling_rate = l2_cfg.get("resample_hz",  100),
        )

    def run(
        self,
        df: pd.DataFrame,
        save_intermediates: bool = False,
        output_dir: str = None,
    ) -> tuple[pd.DataFrame, list]:
        """
        Exécute les 3 niveaux en séquence.
        
        Args:
            df:                 DataFrame brut au format standard
            save_intermediates: Si True, sauvegarde les sorties L1 et L2 en .parquet
            output_dir:         Dossier de sortie (nécessaire si save_intermediates=True)
        
        Returns:
            (features_df, [report_L1, report_L2, report_L3])
        """
        logger.info(f"=== Pipeline Nettoyage DÉBUT : {len(df):,} lignes ===")
        reports = []

        # ── Niveau 1 : nettoyage brut ─────────────────────────────────────────
        df1, r1 = self.l1.clean(df)
        reports.append(r1)
        if save_intermediates and output_dir:
            df1.to_parquet(f"{output_dir}/level1_cleaned.parquet", index=False)

        # ── Niveau 2 : structuration temporelle ───────────────────────────────
        df2, r2 = self.l2.clean(df1)
        reports.append(r2)
        if save_intermediates and output_dir:
            df2.to_parquet(f"{output_dir}/level2_structured.parquet", index=False)

        # ── Niveau 3 : feature engineering ───────────────────────────────────
        df3, r3 = self.l3.extract(df2)
        reports.append(r3)
        if save_intermediates and output_dir:
            df3.to_parquet(f"{output_dir}/level3_features.parquet", index=False)

        logger.info(f"=== Pipeline Nettoyage FIN : {len(df3):,} fenêtres features ===")
        return df3, reports

    def run_single_window(self, window: pd.DataFrame) -> dict:
        """
        Mode streaming (ESP32 temps réel) : traite une seule fenêtre.
        
        Retourne un dict de features, pas un DataFrame, pour être injecté
        directement dans le predictor.
        """
        # L1 sur la fenêtre courante
        cleaned_l1, _ = self.l1.clean(window)
        # L2 sur la fenêtre
        cleaned_l2, _ = self.l2._process_motor(cleaned_l1)

        # Si trop peu de données après nettoyage, on pad par répétition
        if len(cleaned_l2) < self.l3.window_size:
            repeat = (self.l3.window_size // len(cleaned_l2)) + 1
            cleaned_l2 = pd.concat([cleaned_l2] * repeat, ignore_index=True)
            cleaned_l2 = cleaned_l2.iloc[:self.l3.window_size]

        # L3 sur la fenêtre unique
        return self.l3._extract_window(cleaned_l2)
