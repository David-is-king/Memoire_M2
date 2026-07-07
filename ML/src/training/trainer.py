# =============================================================================
# src/training/trainer.py
#
# Pipeline d'entraînement complet — 3 modèles + ensemble :
#
#   1. Isolation Forest    : détection d'anomalies (non supervisé)
#                            → Sortie : score d'anomalie entre 0 et 1
#
#   2. Random Forest       : classification multi-classes
#                            → 5 classes : Normal / Déséquilibre / DésalignH /
#                                          DésalignV / Roulement
#
#   3. LSTM + Attention    : prédiction du RUL (Remaining Useful Life en jours)
#                            → Sortie : nombre de jours avant panne
#
#   4. Ensemble            : soft voting IF (30%) + RF (70%) pour le score santé final
#
# + MLflow tracking des métriques + Optuna hyperparameter tuning (optionnel)
# =============================================================================

import json
import time
import socket
import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from loguru import logger

import optuna
from optuna.samplers import TPESampler

from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import (
    f1_score, classification_report, confusion_matrix,
    roc_auc_score, mean_absolute_error
)

# MLflow est optionnel — si absent, on entraîne sans tracking
mlflow = None


def _is_mlflow_server_reachable(uri: str, timeout: float = 1.0) -> bool:
    """
    Sonde rapide (socket, timeout 1s) pour éviter les minutes de retry/backoff
    de urllib3 quand mlflow.set_experiment() est appelé sur un serveur absent.
    """
    parsed = urlparse(uri)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False  # URI non-HTTP (ex: fichier local) : pas de sonde réseau à faire
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((parsed.hostname, port), timeout=timeout):
            return True
    except OSError:
        return False


# =============================================================================
# ARCHITECTURE LSTM + ATTENTION (PyTorch)
# =============================================================================

class LSTMPredictor(nn.Module):
    """
    Réseau LSTM bi-couche avec mécanisme d'attention pour prédire le RUL.

    Architecture :
      Input (B, T, F)  : B = batch, T = séquence temporelle, F = features
      LSTM             : 2 couches cachées
      Attention        : pondère les pas de temps les plus informatifs
      Régresseur MLP   : 3 couches → 1 valeur (RUL en jours)
      ReLU finale      : garantit RUL ≥ 0

    Le mécanisme d'attention est important pour le RUL : certains instants
    (début de dégradation rapide) sont plus informatifs que d'autres.
    """

    def __init__(
        self,
        input_size: int,
        hidden_size: int = 128,
        num_layers: int = 2,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers  = num_layers

        # LSTM : batch_first=True → shape (batch, seq, features)
        # Dropout entre couches LSTM (seulement si num_layers > 1)
        self.lstm = nn.LSTM(
            input_size  = input_size,
            hidden_size = hidden_size,
            num_layers  = num_layers,
            batch_first = True,
            dropout     = dropout if num_layers > 1 else 0,
        )

        # Mécanisme d'attention : calcule un score scalaire par pas de temps
        # puis normalise avec Softmax → vecteur de poids sommant à 1
        self.attention = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.Tanh(),                      # Tanh centre les scores entre -1 et 1
            nn.Linear(hidden_size // 2, 1),
            nn.Softmax(dim=1),              # Normalise sur la dimension temporelle
        )

        # MLP régresseur : projette le vecteur contexte → RUL
        self.regressor = nn.Sequential(
            nn.Linear(hidden_size, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
            nn.ReLU(),  # RUL ≥ 0 (pas de jours négatifs)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.
        x : (B, T, F) — batch de séquences de features
        Retourne : (B,) — prédiction RUL pour chaque élément du batch
        """
        lstm_out, _ = self.lstm(x)              # (B, T, H) — sorties à chaque pas de temps
        attn_weights = self.attention(lstm_out)  # (B, T, 1) — poids d'importance
        # Vecteur contexte = somme pondérée des états cachés
        context = (attn_weights * lstm_out).sum(dim=1)  # (B, H)
        return self.regressor(context).squeeze(-1)       # (B,)


# =============================================================================
# TRAINER PRINCIPAL
# =============================================================================

class PredictiveMaintenanceTrainer:
    """
    Orchestre l'entraînement complet des 3 modèles.
    Utilise un split par moteur pour éviter la fuite temporelle.
    """

    def __init__(
        self,
        output_dir: str = "models/artifacts",
        mlflow_uri: str = "http://localhost:5000",
        experiment_name: str = "predictive_maintenance",
        device: str = "auto",
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Sélection automatique du device de calcul : GPU (CUDA) > Apple Silicon (MPS) > CPU
        self.device = (
            torch.device("cuda" if torch.cuda.is_available() else
                         "mps" if torch.backends.mps.is_available() else "cpu")
            if device == "auto" else torch.device(device)
        )
        logger.info(f"Device d'entraînement : {self.device}")

        # ── Initialisation MLflow (optionnel — entraîne normalement si absent) ─
        # CORRECTION : mlflow.set_experiment() sur un serveur injoignable ne
        # signale l'échec qu'après plusieurs minutes (retries + backoff de
        # urllib3), ce qui ralentissait chaque entraînement pour rien quand
        # aucun serveur MLflow ne tourne. Une vérification socket rapide
        # (timeout 1s) permet de basculer en "sans tracking" quasi instantanément.
        try:
            global mlflow
            import mlflow as _mlflow
            import mlflow.sklearn
            import mlflow.pytorch
            if not _is_mlflow_server_reachable(mlflow_uri):
                raise ConnectionError(f"Serveur MLflow injoignable à {mlflow_uri}")
            mlflow = _mlflow
            mlflow.set_tracking_uri(mlflow_uri)
            mlflow.set_experiment(experiment_name)
            self.mlflow_enabled = True
            logger.info("✓ MLflow tracking activé")
        except Exception as e:
            logger.warning(f"MLflow non disponible — entraînement sans tracking ({e})")
            self.mlflow_enabled = False

        # Artefacts (initialisés à None, remplis après l'entraînement)
        self.scaler:           Optional[StandardScaler]       = None
        self.isolation_forest: Optional[IsolationForest]      = None
        self.random_forest:    Optional[RandomForestClassifier] = None
        self.lstm:             Optional[LSTMPredictor]        = None
        self.feature_cols:     list                           = []
        self.train_median:     Optional[pd.Series]            = None  # pour imputation test

    # =========================================================================
    # POINT D'ENTRÉE PRINCIPAL
    # =========================================================================

    def train(
        self,
        features_df: pd.DataFrame,
        tune_hyperparams: bool = False,
        sequence_length: int = 50,
    ) -> dict:
        """
        Entraîne les 3 modèles séquentiellement.
        
        Args:
            features_df:      DataFrame features issu du Level3 (1 ligne = 1 fenêtre)
            tune_hyperparams: Si True, lance Optuna pour optimiser les hyperparamètres
            sequence_length:  Longueur des séquences LSTM (nombre de fenêtres consécutives)
        
        Returns:
            Dictionnaire de métriques {modele: {metric: valeur}}
        """
        logger.info("=" * 60)
        logger.info("ENTRAÎNEMENT — DÉBUT")
        logger.info("=" * 60)

        run_name = f"training_{int(time.time())}"
        ctx = mlflow.start_run(run_name=run_name) if self.mlflow_enabled else _NullContext()

        with ctx:
            # ── Étape 1 : Préparation des données ─────────────────────────────
            X, y_cls, y_rul, self.feature_cols = self._prepare_data(features_df)

            # ── Étape 2 : Split MOTEUR-LEVEL ─────────────────────────────────
            # IMPORTANT : le split se fait par moteur, pas par ligne.
            # Pourquoi ? Les fenêtres L3 se chevauchent à 50% → deux fenêtres
            # consécutives d'un même moteur sont très similaires. Un split
            # aléatoire par ligne mettrait des fenêtres jumelles en train ET test,
            # gonflant artificiellement les scores.
            # Avec un split par moteur, le modèle ne voit jamais en test les
            # signaux d'un moteur présent en train. C'est le bon protocole.
            (X_train, X_test,
             y_cls_train, y_cls_test,
             y_rul_train, y_rul_test) = self._split_by_motor(features_df, X, y_cls, y_rul)

            logger.info(f"Split : {len(X_train):,} train / {len(X_test):,} test")

            # ── Étape 3 : Normalisation ───────────────────────────────────────
            # IMPORTANT : le StandardScaler est fitté UNIQUEMENT sur le train,
            # puis appliqué (transform) au test. Ne jamais fitter sur les deux.
            self.scaler = StandardScaler()
            X_train_sc  = self.scaler.fit_transform(X_train)  # fit + transform sur train
            X_test_sc   = self.scaler.transform(X_test)       # transform uniquement sur test

            metrics = {}

            # ── Étape 4 : Entraînement des 3 modèles ─────────────────────────
            # Chaque modèle rapporte aussi ses métriques TRAIN (en plus de test) :
            # un écart train/test important est le signal classique d'overfitting,
            # et il n'était auparavant visible nulle part (ni logs, ni MLflow,
            # ni latest_metrics.json) — seul le score test était calculé.
            logger.info("\n[1/3] Isolation Forest (détection anomalies)...")
            if_metrics = self._train_isolation_forest(
                X_train_sc, y_cls_train, X_test_sc, y_cls_test, tune=tune_hyperparams
            )
            metrics["isolation_forest"] = if_metrics
            logger.info(
                f"  → F1 binaire test = {if_metrics.get('f1', 0):.3f} "
                f"(train = {if_metrics.get('f1_train', 0):.3f})"
            )

            logger.info("\n[2/3] Random Forest (classification 5 classes)...")
            rf_metrics = self._train_random_forest(
                X_train_sc, y_cls_train, X_test_sc, y_cls_test, tune=tune_hyperparams
            )
            metrics["random_forest"] = rf_metrics
            logger.info(
                f"  → F1-macro test = {rf_metrics['f1_macro']:.3f} (train = {rf_metrics['f1_macro_train']:.3f}) | "
                f"AUC test = {rf_metrics['auc']:.3f} (train = {rf_metrics['auc_train']:.3f})"
            )
            self._warn_if_overfitting("Random Forest", rf_metrics["f1_macro_train"], rf_metrics["f1_macro"])

            logger.info("\n[3/3] LSTM + Attention (prédiction RUL)...")
            lstm_metrics = self._train_lstm(
                X_train_sc, y_rul_train, X_test_sc, y_rul_test,
                sequence_length=sequence_length, tune=tune_hyperparams
            )
            metrics["lstm"] = lstm_metrics
            logger.info(
                f"  → MAE test = {lstm_metrics['mae']:.1f}j (train = {lstm_metrics['mae_train']:.1f}j) | "
                f"RMSE test = {lstm_metrics['rmse']:.1f}j (train = {lstm_metrics['rmse_train']:.1f}j)"
            )

            # ── Étape 5 : Évaluation de l'ensemble ───────────────────────────
            logger.info("\nÉvaluation Ensemble (IF + RF)...")
            ens_metrics = self._evaluate_ensemble(X_test_sc, y_cls_test, y_rul_test)
            metrics["ensemble"] = ens_metrics

            # ── Étape 6 : Log MLflow ──────────────────────────────────────────
            if self.mlflow_enabled:
                mlflow.log_metrics({
                    "rf_f1_macro":        rf_metrics["f1_macro"],
                    "rf_f1_macro_train":  rf_metrics["f1_macro_train"],
                    "rf_auc":             rf_metrics["auc"],
                    "rf_auc_train":       rf_metrics["auc_train"],
                    "lstm_mae":           lstm_metrics["mae"],
                    "lstm_mae_train":     lstm_metrics["mae_train"],
                    "lstm_rmse":          lstm_metrics["rmse"],
                    "lstm_rmse_train":    lstm_metrics["rmse_train"],
                    "if_f1":              if_metrics.get("f1", 0),
                    "if_f1_train":        if_metrics.get("f1_train", 0),
                })
                mlflow.log_param("n_features", len(self.feature_cols))
                mlflow.log_param("n_train",    len(X_train))
                mlflow.log_param("n_test",     len(X_test))

            # ── Étape 7 : Sauvegarde des artefacts ───────────────────────────
            self._save_artifacts()

        logger.info("\n" + "=" * 60)
        logger.info("ENTRAÎNEMENT — TERMINÉ")
        self._print_summary(metrics)

        return metrics

    # =========================================================================
    # PRÉPARATION DES DONNÉES
    # =========================================================================

    def _prepare_data(self, df: pd.DataFrame) -> tuple:
        """
        Extrait X, y_cls, y_rul depuis le DataFrame features.
        
        - Exclut les colonnes non-features (metadata, labels internes)
        - Supprime les colonnes avec > 20% de NaN
        - Impute les NaN restants (médiane calculée PLUS TARD sur le train uniquement)
        
        Retourne : (X_raw, y_cls, y_rul, feature_cols)
        Note : X_raw n'est pas encore imputé ici — l'imputation se fait dans _split_by_motor
              pour garantir que la médiane est calculée uniquement sur le train.
        """
        # Colonnes à exclure : metadata + labels cibles + colonnes de nettoyage internes
        exclude = {
            "motor_id", "timestamp", "label", "rul", "data_origin",
            "_out_of_bounds", "_has_null", "_statistical_outlier",
            "_has_anomaly", "_large_gap"
        }

        # Ne garder que les colonnes numériques qui ne sont pas exclues
        feature_cols = [
            c for c in df.columns
            if c not in exclude
            and pd.api.types.is_numeric_dtype(df[c])
        ]

        # Supprimer les colonnes avec trop de NaN (> 20% manquant = pas fiable)
        nan_frac = df[feature_cols].isna().mean()
        feature_cols = [c for c in feature_cols if nan_frac[c] < 0.20]

        # Extraire X brut (sans imputation — voir _split_by_motor)
        X_raw = df[feature_cols].values

        # Cible classification : label (défaut par défaut = 0 = Normal)
        y_cls = df["label"].values.astype(int) if "label" in df.columns else np.zeros(len(df), dtype=int)
        # Cible régression : RUL en jours (défaut = 365 jours = moteur neuf)
        y_rul = df["rul"].values.astype(float) if "rul" in df.columns else np.full(len(df), 365.0)

        logger.info(f"  Features sélectionnées : {len(feature_cols)}")
        logger.info(f"  Échantillons : {len(X_raw):,}")
        logger.info(f"  Distribution classes : {dict(zip(*np.unique(y_cls, return_counts=True)))}")

        return X_raw, y_cls, y_rul, feature_cols

    # =========================================================================
    # SPLIT PAR MOTEUR — Sans fuite temporelle
    # =========================================================================

    def _split_by_motor(
        self,
        df: pd.DataFrame,
        X: np.ndarray,
        y_cls: np.ndarray,
        y_rul: np.ndarray,
        test_ratio: float = 0.2,
        random_state: int = 42,
    ) -> tuple:
        """
        ╔═══════════════════════════════════════════════════════════════════╗
        ║  CORRECTION FUITE TEMPORELLE                                     ║
        ║                                                                   ║
        ║  PROBLÈME : train_test_split aléatoire sur les lignes crée une   ║
        ║  fuite car les fenêtres L3 se chevauchent à 50% → une fenêtre    ║
        ║  en train et sa jumelle en test rendent le test trivial.         ║
        ║                                                                   ║
        ║  SOLUTION : on split les MOTEURS, pas les lignes.                ║
        ║  Tous les moteurs de test sont 100% inconnus pendant l'entraîn.  ║
        ╚═══════════════════════════════════════════════════════════════════╝
        
        Stratégie :
        1. Lister les moteurs uniques
        2. Mélanger les moteurs (seed fixe pour reproductibilité)
        3. Les 20% derniers → test, les 80% premiers → train
        4. Imputer les NaN AVEC la médiane du train uniquement
        """
        if "motor_id" not in df.columns:
            raise ValueError("Colonne 'motor_id' absente — impossible de faire le split par moteur")

        # Liste des moteurs uniques et shuffle reproductible
        rng = np.random.default_rng(seed=random_state)
        unique_motors = np.array(df["motor_id"].unique())
        rng.shuffle(unique_motors)

        # Calcul du point de coupure
        n_test = max(1, int(len(unique_motors) * test_ratio))
        test_motors  = set(unique_motors[-n_test:])
        train_motors = set(unique_motors[:-n_test])

        logger.info(f"  Moteurs train : {len(train_motors)} | Moteurs test : {len(test_motors)}")
        logger.info(f"  Moteurs test  : {sorted(test_motors)}")

        # Masques booléens sur les lignes
        motor_series  = df["motor_id"].values
        train_mask    = np.isin(motor_series, list(train_motors))
        test_mask     = np.isin(motor_series, list(test_motors))

        X_train_raw   = X[train_mask]
        X_test_raw    = X[test_mask]
        y_cls_train   = y_cls[train_mask]
        y_cls_test    = y_cls[test_mask]
        y_rul_train   = y_rul[train_mask]
        y_rul_test    = y_rul[test_mask]

        # ── Imputation des NaN ────────────────────────────────────────────────
        # La médiane est calculée UNIQUEMENT sur le train → pas de fuite
        self.train_median = np.nanmedian(X_train_raw, axis=0)
        # Remplacer les NaN par la médiane correspondante (colonne par colonne)
        X_train = np.where(np.isnan(X_train_raw), self.train_median, X_train_raw)
        X_test  = np.where(np.isnan(X_test_raw),  self.train_median, X_test_raw)

        return X_train, X_test, y_cls_train, y_cls_test, y_rul_train, y_rul_test

    # =========================================================================
    # MODÈLE 1 — ISOLATION FOREST (Détection d'anomalies non supervisée)
    # =========================================================================

    def _train_isolation_forest(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_test: np.ndarray,
        y_test: np.ndarray,
        tune: bool = False,
    ) -> dict:
        """
        Entraîne l'Isolation Forest.

        L'IF est non supervisé : il n'utilise que X_train (sans labels).
        Il apprend à isoler les points rares/anomaux vs les points normaux.

        Évaluation : on binarise y_test/y_train (0=Normal, 1+=Défaut) et on
        compare aux prédictions de l'IF (-1=anomalie → 1, +1=normal → 0).
        y_train sert uniquement à calculer le F1 train (diagnostic
        overfitting) — l'entraînement lui-même reste non supervisé.
        """
        if tune:
            params = self._tune_isolation_forest(X_train)
        else:
            params = {"n_estimators": 200, "contamination": 0.05, "max_samples": "auto"}

        self.isolation_forest = IsolationForest(random_state=42, n_jobs=-1, **params)
        self.isolation_forest.fit(X_train)  # Non supervisé : pas de labels

        # Conversion des prédictions IF : -1 (anomalie) → 1, +1 (normal) → 0
        preds_if    = self.isolation_forest.predict(X_test)
        preds_bin   = (preds_if == -1).astype(int)
        y_binary    = (y_test > 0).astype(int)  # warning + critical = anomalie
        f1 = f1_score(y_binary, preds_bin, zero_division=0)

        # Score train (même transformation, sur X_train/y_train)
        preds_if_train  = self.isolation_forest.predict(X_train)
        preds_bin_train = (preds_if_train == -1).astype(int)
        y_binary_train  = (y_train > 0).astype(int)
        f1_train = f1_score(y_binary_train, preds_bin_train, zero_division=0)

        if self.mlflow_enabled:
            mlflow.log_params({f"if_{k}": v for k, v in params.items()})
            mlflow.log_metric("if_f1", f1)
            mlflow.log_metric("if_f1_train", f1_train)

        return {"f1": f1, "f1_train": f1_train, "params": params}

    def _tune_isolation_forest(self, X_train: np.ndarray) -> dict:
        """Optimise les hyperparamètres IF avec Optuna."""
        def objective(trial):
            params = {
                "n_estimators":  trial.suggest_int("n_estimators", 100, 500),
                "contamination": trial.suggest_float("contamination", 0.01, 0.15),
                "max_features":  trial.suggest_float("max_features", 0.5, 1.0),
            }
            model = IsolationForest(random_state=42, **params)
            model.fit(X_train)
            # Proxy d'optimisation : maximiser la séparation des scores
            return float(model.decision_function(X_train).mean())

        study = optuna.create_study(direction="maximize", sampler=TPESampler(seed=42))
        study.optimize(objective, n_trials=20, show_progress_bar=False)
        return study.best_params

    # =========================================================================
    # MODÈLE 2 — RANDOM FOREST (Classification multi-classes)
    # =========================================================================

    def _train_random_forest(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        tune: bool = False,
    ) -> dict:
        """
        Entraîne le Random Forest pour la classification 5 classes :
          0 = Normal
          1 = Déséquilibre de masse (imbalance)
          2 = Désalignement horizontal
          3 = Désalignement vertical
          4 = Défaut de roulement (bearing)
        
        class_weight="balanced" compense le déséquilibre de classes
        (MAFAULDA et CWRU n'ont pas la même distribution par classe).
        """
        logger.info("  Entraînement Random Forest multi-classes...")

        if tune:
            logger.info("  Optimisation Optuna en cours (peut prendre quelques minutes)...")
            # ╔══════════════════════════════════════════════════════════╗
            # ║  CORRECTION : était "_tune_rf" (inexistant) → corrigé   ║
            # ║  en "_tune_random_forest" (nom réel de la méthode)       ║
            # ╚══════════════════════════════════════════════════════════╝
            params = self._tune_random_forest(X_train, y_train)  # ← CORRIGÉ
        else:
            params = {
                "n_estimators": 150,
                "max_depth":    12,
                "random_state": 42,
                "class_weight": "balanced",
                "n_jobs":       -1,
            }

        rf = RandomForestClassifier(**params)
        rf.fit(X_train, y_train)
        self.random_forest = rf

        # ── Évaluation test ───────────────────────────────────────────────────
        preds = rf.predict(X_val)
        probs = rf.predict_proba(X_val)

        # F1-macro : moyenne du F1 sur chaque classe (équitable même si déséquilibré)
        f1_macro = f1_score(y_val, preds, average="macro", zero_division=0)

        # AUC multi-classes avec stratégie One-vs-Rest (obligatoire en sklearn)
        try:
            auc = roc_auc_score(y_val, probs, multi_class="ovr", average="macro")
        except Exception as e:
            logger.warning(f"  AUC non calculable : {e} → 0.5 par défaut")
            auc = 0.5

        # ── Évaluation train (diagnostic overfitting) ─────────────────────────
        # Un F1-macro train nettement supérieur au test (écart > ~0.15-0.20) est
        # le signal classique d'un modèle qui a mémorisé le train plutôt
        # qu'appris à généraliser (cf. _warn_if_overfitting).
        preds_train = rf.predict(X_train)
        probs_train = rf.predict_proba(X_train)
        f1_macro_train = f1_score(y_train, preds_train, average="macro", zero_division=0)
        try:
            auc_train = roc_auc_score(y_train, probs_train, multi_class="ovr", average="macro")
        except Exception:
            auc_train = 0.5

        # Rapport détaillé par classe
        logger.info(
            f"\n  Rapport de classification (test) :\n"
            f"{classification_report(y_val, preds, zero_division=0)}"
        )

        # Matrice de confusion
        conf_matrix = confusion_matrix(y_val, preds)
        logger.debug(f"  Matrice de confusion :\n{conf_matrix}")

        if self.mlflow_enabled:
            mlflow.log_params({f"rf_{k}": v for k, v in params.items()})
            mlflow.log_metric("rf_f1_macro",       f1_macro)
            mlflow.log_metric("rf_f1_macro_train", f1_macro_train)
            mlflow.log_metric("rf_auc",            auc)
            mlflow.log_metric("rf_auc_train",      auc_train)

        return {
            "f1_macro":       f1_macro,
            "f1_macro_train": f1_macro_train,
            "auc":            auc,
            "auc_train":      auc_train,
            "matrix":         conf_matrix.tolist(),
        }

    def _tune_random_forest(self, X_train: np.ndarray, y_train: np.ndarray) -> dict:
        """
        Optimise les hyperparamètres du Random Forest avec Optuna
        via validation croisée stratifiée 3-fold.
        """
        def objective(trial):
            params = {
                "n_estimators":      trial.suggest_int("n_estimators", 100, 500),
                "max_depth":         trial.suggest_int("max_depth", 5, 30),
                "min_samples_split": trial.suggest_int("min_samples_split", 2, 20),
                "max_features":      trial.suggest_categorical("max_features", ["sqrt", "log2", 0.5]),
                "class_weight":      "balanced",
                "random_state":      42,
                "n_jobs":            -1,
            }
            cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
            scores = []
            for train_idx, val_idx in cv.split(X_train, y_train):
                rf = RandomForestClassifier(**params)
                rf.fit(X_train[train_idx], y_train[train_idx])
                pred = rf.predict(X_train[val_idx])
                scores.append(f1_score(y_train[val_idx], pred, average="macro", zero_division=0))
            return float(np.mean(scores))

        study = optuna.create_study(direction="maximize", sampler=TPESampler(seed=42))
        study.optimize(objective, n_trials=30, show_progress_bar=True)
        logger.info(f"  Meilleurs hyperparamètres RF : {study.best_params}")
        return study.best_params

    # =========================================================================
    # MODÈLE 3 — LSTM + ATTENTION (Prédiction RUL)
    # =========================================================================

    def _train_lstm(
        self,
        X_train: np.ndarray,
        y_rul_train: np.ndarray,
        X_test: np.ndarray,
        y_rul_test: np.ndarray,
        sequence_length: int = 50,
        tune: bool = False,
    ) -> dict:
        """
        Entraîne le LSTM pour prédire le RUL.
        
        Données d'entrée : X_train est déjà trié chronologiquement par moteur
        (grâce au split moteur-level + sort dans le loader).
        
        Hyperparamètres : HuberLoss (robuste aux outliers de RUL),
        early stopping sur la val_loss, ReduceLROnPlateau.
        """
        if tune:
            hp = self._tune_lstm(X_train, y_rul_train, sequence_length)
        else:
            hp = {
                "hidden_size": 128,
                "num_layers":  2,
                "dropout":     0.2,
                "lr":          1e-3,
                "batch_size":  64,
            }

        input_size = X_train.shape[1]
        self.lstm = LSTMPredictor(
            input_size   = input_size,
            hidden_size  = hp["hidden_size"],
            num_layers   = hp["num_layers"],
            dropout      = hp["dropout"],
        ).to(self.device)

        # ── Création des séquences ─────────────────────────────────────────────
        # Le LSTM reçoit des séquences de 'sequence_length' fenêtres consécutives
        X_seq_train, y_seq_train = self._make_sequences(X_train, y_rul_train, sequence_length)
        X_seq_test,  y_seq_test  = self._make_sequences(X_test,  y_rul_test,  sequence_length)

        if len(X_seq_train) == 0 or len(X_seq_test) == 0:
            logger.warning("  Pas assez de données pour les séquences LSTM — modèle LSTM ignoré")
            return {"mae": 999.0, "mae_train": 999.0, "rmse": 999.0, "rmse_train": 999.0, "params": hp}

        # DataLoader PyTorch
        train_ds = TensorDataset(
            torch.FloatTensor(X_seq_train),
            torch.FloatTensor(y_seq_train),
        )
        train_loader = DataLoader(
            train_ds,
            batch_size  = hp["batch_size"],
            shuffle     = True,   # Shuffle OK : les séquences sont déjà construites
            num_workers = 0,      # 0 pour compatibilité Windows
        )

        # ── Optimiseur et scheduler ───────────────────────────────────────────
        optimizer  = torch.optim.Adam(self.lstm.parameters(), lr=hp["lr"], weight_decay=1e-5)
        scheduler  = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)
        criterion  = nn.HuberLoss()  # Robuste aux outliers de RUL (mieux que MSE)

        best_val_loss    = float("inf")
        patience_counter = 0
        epochs           = 100
        patience         = 15  # Arrêt si pas d'amélioration pendant 15 epochs

        logger.info(f"  LSTM : {len(X_seq_train)} séquences | device={self.device}")

        for epoch in range(epochs):
            # ── Phase d'entraînement ──────────────────────────────────────────
            self.lstm.train()
            train_loss = 0.0
            for X_batch, y_batch in train_loader:
                X_batch, y_batch = X_batch.to(self.device), y_batch.to(self.device)
                optimizer.zero_grad()
                pred  = self.lstm(X_batch)
                loss  = criterion(pred, y_batch)
                loss.backward()
                # Gradient clipping : évite les exploding gradients (fréquent avec LSTM)
                nn.utils.clip_grad_norm_(self.lstm.parameters(), 1.0)
                optimizer.step()
                train_loss += loss.item()

            # ── Phase de validation ───────────────────────────────────────────
            self.lstm.eval()
            with torch.no_grad():
                X_val_t = torch.FloatTensor(X_seq_test).to(self.device)
                preds   = self.lstm(X_val_t).cpu().numpy()
            val_loss = mean_absolute_error(y_seq_test, preds)
            scheduler.step(val_loss)

            if epoch % 10 == 0:
                avg_train = train_loss / max(len(train_loader), 1)
                logger.debug(f"    Epoch {epoch:3d} | train_loss={avg_train:.4f} | val_MAE={val_loss:.2f}j")

            # ── Early stopping ────────────────────────────────────────────────
            if val_loss < best_val_loss:
                best_val_loss    = val_loss
                patience_counter = 0
                torch.save(self.lstm.state_dict(), self.output_dir / "lstm_best.pt")
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    logger.info(f"  Early stopping déclenché à l'epoch {epoch}")
                    break

        # ── Chargement des meilleurs poids ────────────────────────────────────
        self.lstm.load_state_dict(
            torch.load(self.output_dir / "lstm_best.pt", map_location=self.device)
        )

        # ── Métriques finales sur le test ─────────────────────────────────────
        self.lstm.eval()
        with torch.no_grad():
            final_preds = self.lstm(
                torch.FloatTensor(X_seq_test).to(self.device)
            ).cpu().numpy()

        mae  = mean_absolute_error(y_seq_test, final_preds)
        rmse = float(np.sqrt(np.mean((y_seq_test - final_preds) ** 2)))

        # ── Métriques finales sur le train (diagnostic overfitting) ──────────
        # Comparé au MAE/RMSE test ci-dessus : un écart important (train très
        # bas, test élevé) signale que le LSTM a mémorisé les séquences train.
        with torch.no_grad():
            final_preds_train = self.lstm(
                torch.FloatTensor(X_seq_train).to(self.device)
            ).cpu().numpy()

        mae_train  = mean_absolute_error(y_seq_train, final_preds_train)
        rmse_train = float(np.sqrt(np.mean((y_seq_train - final_preds_train) ** 2)))

        if self.mlflow_enabled:
            mlflow.pytorch.log_model(self.lstm, "lstm")
            mlflow.log_metric("lstm_mae_final",        mae)
            mlflow.log_metric("lstm_mae_final_train",  mae_train)
            mlflow.log_metric("lstm_rmse_final",       rmse)
            mlflow.log_metric("lstm_rmse_final_train", rmse_train)

        return {
            "mae":            mae,
            "mae_train":      mae_train,
            "rmse":           rmse,
            "rmse_train":     rmse_train,
            "best_val_loss":  best_val_loss,
            "params":         hp,
        }

    def _tune_lstm(self, X_train: np.ndarray, y_train: np.ndarray, sequence_length: int) -> dict:
        """Optimise les hyperparamètres LSTM avec Optuna (15 trials sur 5000 points max)."""
        def objective(trial):
            hp = {
                "hidden_size": trial.suggest_categorical("hidden_size", [64, 128, 256]),
                "num_layers":  trial.suggest_int("num_layers", 1, 3),
                "dropout":     trial.suggest_float("dropout", 0.1, 0.4),
                "lr":          trial.suggest_float("lr", 1e-4, 1e-2, log=True),
                "batch_size":  trial.suggest_categorical("batch_size", [32, 64, 128]),
            }
            model = LSTMPredictor(
                X_train.shape[1], hp["hidden_size"], hp["num_layers"], hp["dropout"]
            ).to(self.device)
            optimizer = torch.optim.Adam(model.parameters(), lr=hp["lr"])
            # Sur un sous-ensemble pour la rapidité du tuning
            X_sub = X_train[:5000]
            y_sub = y_train[:5000]
            X_seq, y_seq = self._make_sequences(X_sub, y_sub, sequence_length)
            if len(X_seq) < 10:
                return 999.0
            loader = DataLoader(
                TensorDataset(torch.FloatTensor(X_seq), torch.FloatTensor(y_seq)),
                batch_size=hp["batch_size"], shuffle=True
            )
            model.train()
            for _ in range(10):  # 10 epochs pour le proxy
                for xb, yb in loader:
                    xb, yb = xb.to(self.device), yb.to(self.device)
                    optimizer.zero_grad()
                    nn.HuberLoss()(model(xb), yb).backward()
                    optimizer.step()
            model.eval()
            with torch.no_grad():
                preds = model(torch.FloatTensor(X_seq[:200]).to(self.device)).cpu().numpy()
            return float(mean_absolute_error(y_seq[:200], preds))

        study = optuna.create_study(direction="minimize", sampler=TPESampler(seed=42))
        study.optimize(objective, n_trials=15, show_progress_bar=True)
        return study.best_params

    @staticmethod
    def _make_sequences(X: np.ndarray, y: np.ndarray, seq_len: int) -> tuple:
        """
        Construit des séquences glissantes pour le LSTM.
        
        Exemple avec seq_len=3 :
          X = [f0, f1, f2, f3, f4, f5]
          → Séquences X : [[f0,f1,f2], [f1,f2,f3], [f2,f3,f4]]
          → Cibles y    : [y3,          y4,          y5        ]
        """
        if len(X) <= seq_len:
            return np.array([]), np.array([])
        X_seq = np.array([X[i:i + seq_len] for i in range(len(X) - seq_len)])
        y_seq = y[seq_len:]
        return X_seq, y_seq

    # =========================================================================
    # ENSEMBLE (IF + RF)
    # =========================================================================

    def _evaluate_ensemble(
        self,
        X_test: np.ndarray,
        y_cls_test: np.ndarray,
        y_rul_test: np.ndarray,
    ) -> dict:
        """
        Évalue l'ensemble : combinaison pondérée IF (30%) + RF (70%).
        
        L'IF apporte la détection d'anomalies non supervisée.
        Le RF apporte la classification supervisée précise.
        Le vote doux (soft voting) combine leurs probabilités.
        """
        if self.random_forest is None or self.isolation_forest is None:
            return {}

        rf_proba    = self.random_forest.predict_proba(X_test)   # (N, n_classes)
        if_scores   = -self.isolation_forest.decision_function(X_test)  # Plus élevé = plus anomal
        n_classes   = rf_proba.shape[1]

        # Normalisation des scores IF entre 0 et 1
        if_min, if_max   = if_scores.min(), if_scores.max()
        if_norm          = (if_scores - if_min) / (if_max - if_min + 1e-10)

        # Contribution IF : distribué sur les classes anormales
        if_contribution  = np.zeros((len(X_test), n_classes))
        if_contribution[:, 0] = 1 - if_norm   # Classe 0 (Normal) = 1 - anomaly_score

        if n_classes > 1:
            # Répartir le score d'anomalie équitablement entre classes de défauts
            per_fault = if_norm / max(n_classes - 1, 1)
            for c in range(1, n_classes):
                if_contribution[:, c] = per_fault

        # Vote doux pondéré
        ensemble_proba = 0.3 * if_contribution + 0.7 * rf_proba
        ensemble_pred  = np.argmax(ensemble_proba, axis=1)

        f1 = f1_score(y_cls_test, ensemble_pred, average="macro", zero_division=0)

        unique, counts = np.unique(ensemble_pred, return_counts=True)
        return {
            "f1_macro":         f1,
            "ensemble_pred_dist": dict(zip(unique.tolist(), counts.tolist())),
        }

    # =========================================================================
    # SAUVEGARDE DES ARTEFACTS
    # =========================================================================

    def _save_artifacts(self):
        """
        Sauvegarde tous les artefacts nécessaires à l'inférence.
        Les noms de fichiers doivent correspondre exactement à ce que charge predictor.py.
        """
        # Modèles sklearn → joblib (format .pkl)
        joblib.dump(self.scaler,           self.output_dir / "scaler.pkl")
        joblib.dump(self.isolation_forest, self.output_dir / "isolation_forest.pkl")
        joblib.dump(self.random_forest,    self.output_dir / "random_forest.pkl")

        # Liste des features dans l'ordre exact → indispensable pour l'inférence
        joblib.dump(self.feature_cols,     self.output_dir / "feature_cols.pkl")

        # Médiane du train → pour imputer les NaN à l'inférence
        if self.train_median is not None:
            np.save(self.output_dir / "train_median.npy", self.train_median)

        # LSTM → poids PyTorch + config (nécessaire pour reconstruire l'architecture)
        if self.lstm is not None:
            torch.save(self.lstm.state_dict(), self.output_dir / "lstm_final.pt")
            config = {
                "input_size":  len(self.feature_cols),
                "hidden_size": self.lstm.hidden_size,
                "num_layers":  self.lstm.num_layers,
            }
            with open(self.output_dir / "lstm_config.json", "w") as f:
                json.dump(config, f, indent=2)

        logger.info(f"✓ Tous les artefacts sauvegardés dans {self.output_dir}")

    # =========================================================================
    # DIAGNOSTIC OVERFITTING
    # =========================================================================

    @staticmethod
    def _warn_if_overfitting(model_name: str, train_score: float, test_score: float, threshold: float = 0.15):
        """
        Logue un avertissement si l'écart train/test dépasse 'threshold'.

        Seuil de 0.15 : au-delà, l'écart dépasse ce qu'on attend de la seule
        variance d'échantillonnage entre splits et suggère une mémorisation du
        train plutôt qu'une généralisation (règle empirique, pas une preuve
        statistique — à recouper avec la courbe train_loss/val_MAE du LSTM et
        avec un nouveau split si le doute persiste).
        """
        gap = train_score - test_score
        if gap > threshold:
            logger.warning(
                f"  ⚠ {model_name} : écart train/test = {gap:.3f} "
                f"(train={train_score:.3f}, test={test_score:.3f}) — possible overfitting"
            )

    # =========================================================================
    # AFFICHAGE DU RÉSUMÉ
    # =========================================================================

    @staticmethod
    def _print_summary(metrics: dict):
        """
        Affiche un tableau récapitulatif des métriques d'entraînement (test vs train).

        CORRECTION : print() plante avec UnicodeEncodeError sur les caractères
        de dessin de boîte (╔═╗...) quand la console Windows utilise l'encodage
        cp1252 par défaut (le crash survenait APRÈS la sauvegarde des artefacts
        — l'entraînement avait réussi mais le script sortait quand même en
        erreur). logger.info() gère déjà ces caractères sans problème ailleurs
        dans ce même fichier → on l'utilise ici aussi au lieu de print().
        """
        lines = [
            "",
            "╔══════════════════════════════════════════════════════════╗",
            "║              RÉSUMÉ DE L'ENTRAÎNEMENT (test | train)       ║",
            "╠══════════════════════════════════════════════════════════╣",
        ]
        if "isolation_forest" in metrics:
            if_m = metrics["isolation_forest"]
            lines.append(f"║  Isolation Forest  — F1 binaire : {if_m.get('f1', 0):.3f} | {if_m.get('f1_train', 0):.3f}")
        if "random_forest" in metrics:
            rf = metrics["random_forest"]
            lines.append(f"║  Random Forest     — F1-macro   : {rf['f1_macro']:.3f} | {rf['f1_macro_train']:.3f}")
            lines.append(f"║                    — AUC-ROC    : {rf['auc']:.3f} | {rf['auc_train']:.3f}")
        if "lstm" in metrics:
            lstm = metrics["lstm"]
            lines.append(f"║  LSTM + Attention  — MAE RUL    : {lstm['mae']:6.1f}j | {lstm['mae_train']:6.1f}j")
            lines.append(f"║                    — RMSE RUL   : {lstm['rmse']:6.1f}j | {lstm['rmse_train']:6.1f}j")
        if "ensemble" in metrics:
            ens = metrics["ensemble"]
            lines.append(f"║  Ensemble (IF+RF)  — F1-macro   : {ens.get('f1_macro', 0):.3f}")
        lines.append("╚══════════════════════════════════════════════════════════╝")
        logger.info("\n".join(lines))


# =============================================================================
# Utilitaire interne — Context manager no-op si MLflow absent
# =============================================================================

class _NullContext:
    """Remplace mlflow.start_run() quand MLflow n'est pas disponible."""
    def __enter__(self):  return self
    def __exit__(self, *args): pass
