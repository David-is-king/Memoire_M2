"""
src/training/trainer.py

Pipeline d'entraînement complet :
1. Isolation Forest    — détection anomalies (non supervisé)
2. Random Forest       — classification (OK / Warning / Critical)
3. LSTM                — prédiction RUL (série temporelle)
4. Ensemble            — combinaison des 3 modèles
+ MLflow tracking + Optuna hyperparameter tuning
"""

import json
import time
import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from pathlib import Path
from typing import Optional
from loguru import logger

import optuna
from optuna.samplers import TPESampler

from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.metrics import (
    f1_score, classification_report, confusion_matrix,
    roc_auc_score, mean_absolute_error
)
from sklearn.pipeline import Pipeline as SKPipeline

mlflow = None


# ═══════════════════════════════════════════════════════════
# LSTM Model (PyTorch)
# ═══════════════════════════════════════════════════════════

class LSTMPredictor(nn.Module):
    """LSTM pour prédire le RUL (Remaining Useful Life) en jours."""

    def __init__(self, input_size: int, hidden_size: int = 128, num_layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers

        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
        )
        self.attention = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.Tanh(),
            nn.Linear(hidden_size // 2, 1),
            nn.Softmax(dim=1),
        )
        self.regressor = nn.Sequential(
            nn.Linear(hidden_size, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
            nn.ReLU(),   # RUL ≥ 0
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        lstm_out, _ = self.lstm(x)            # (B, T, H)
        attn_weights = self.attention(lstm_out)  # (B, T, 1)
        context = (attn_weights * lstm_out).sum(dim=1)  # (B, H)
        return self.regressor(context).squeeze(-1)


# ═══════════════════════════════════════════════════════════
# Trainer principal
# ═══════════════════════════════════════════════════════════

class PredictiveMaintenanceTrainer:

    def __init__(
        self,
        output_dir: str = "models/artifacts",
        mlflow_uri: str = "http://localhost:5000",
        experiment_name: str = "predictive_maintenance",
        device: str = "auto",
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "mps"
            if torch.backends.mps.is_available() else "cpu"
        ) if device == "auto" else torch.device(device)

        logger.info(f"Training device: {self.device}")

        # MLflow
        try:
            global mlflow
            import mlflow as _mlflow
            import mlflow.sklearn
            import mlflow.pytorch
            mlflow = _mlflow
            mlflow.set_tracking_uri(mlflow_uri)
            mlflow.set_experiment(experiment_name)
            self.mlflow_enabled = True
        except Exception as e:
            logger.warning(f"MLflow not available - training without tracking ({e})")
            self.mlflow_enabled = False

        # Artifacts
        self.scaler: Optional[StandardScaler] = None
        self.isolation_forest: Optional[IsolationForest] = None
        self.random_forest: Optional[RandomForestClassifier] = None
        self.lstm: Optional[LSTMPredictor] = None
        self.feature_cols: list = []

    # ── Entry point ───────────────────────────────────────────
    def train(
        self,
        features_df: pd.DataFrame,
        tune_hyperparams: bool = False,
        sequence_length: int = 50,
    ) -> dict:
        """
        Entraîne les 3 modèles + ensemble.
        Retourne les métriques finales.
        """
        logger.info("=" * 60)
        logger.info("TRAINING PIPELINE START")
        logger.info("=" * 60)

        run_name = f"training_{int(time.time())}"
        ctx = mlflow.start_run(run_name=run_name) if self.mlflow_enabled else _NullContext()

        with ctx:
            # ── Préparation données ───────────────────────────
            X, y_cls, y_rul, self.feature_cols = self._prepare_data(features_df)
            X_train, X_test, y_cls_train, y_cls_test, y_rul_train, y_rul_test = \
                self._split(X, y_cls, y_rul)

            # Normalisation
            self.scaler = StandardScaler()
            X_train_sc = self.scaler.fit_transform(X_train)
            X_test_sc  = self.scaler.transform(X_test)

            metrics = {}

            # ── 1. Isolation Forest ───────────────────────────
            logger.info("\n[1/3] Training Isolation Forest...")
            if_metrics = self._train_isolation_forest(
                X_train_sc, X_test_sc, y_cls_test, tune=tune_hyperparams
            )
            metrics["isolation_forest"] = if_metrics
            logger.info(f"  Anomaly detection → F1={if_metrics.get('f1', 'N/A'):.3f}")

            # ── 2. Random Forest ──────────────────────────────
            logger.info("\n[2/3] Training Random Forest Classifier...")
            rf_metrics = self._train_random_forest(
                X_train_sc, y_cls_train, X_test_sc, y_cls_test, tune=tune_hyperparams
            )
            metrics["random_forest"] = rf_metrics
            logger.info(f"  Classification → F1={rf_metrics['f1_macro']:.3f} | AUC={rf_metrics['auc']:.3f}")

            # ── 3. LSTM ───────────────────────────────────────
            logger.info("\n[3/3] Training LSTM (RUL prediction)...")
            lstm_metrics = self._train_lstm(
                X_train_sc, y_rul_train, X_test_sc, y_rul_test,
                sequence_length=sequence_length, tune=tune_hyperparams
            )
            metrics["lstm"] = lstm_metrics
            logger.info(f"  RUL prediction → MAE={lstm_metrics['mae']:.2f} days")

            # ── 4. Ensemble evaluation ───────────────────────
            logger.info("\nEvaluating Ensemble...")
            ens_metrics = self._evaluate_ensemble(X_test_sc, y_cls_test, y_rul_test)
            metrics["ensemble"] = ens_metrics

            # ── Log métriques MLflow ──────────────────────────
            if self.mlflow_enabled:
                mlflow.log_metrics({
                    "rf_f1_macro":  rf_metrics["f1_macro"],
                    "rf_auc":       rf_metrics["auc"],
                    "lstm_mae":     lstm_metrics["mae"],
                    "lstm_rmse":    lstm_metrics["rmse"],
                })

            # ── Sauvegarde ────────────────────────────────────
            self._save_artifacts()

            logger.info("\n" + "=" * 60)
            logger.info("TRAINING PIPELINE COMPLETE")
            self._print_summary(metrics)

        return metrics

    # ── Data preparation ──────────────────────────────────────
    def _prepare_data(self, df: pd.DataFrame) -> tuple:
        # Colonnes à exclure
        exclude = {"motor_id", "timestamp", "label", "rul",
                   "_out_of_bounds", "_has_null", "_statistical_outlier", "_has_anomaly", "_large_gap"}

        feature_cols = [c for c in df.columns if c not in exclude
                        and df[c].dtype in [np.float64, np.float32, np.int64, np.int32]]

        # Supprimer colonnes avec trop de NaN (>20%)
        nan_frac = df[feature_cols].isna().mean()
        feature_cols = [c for c in feature_cols if nan_frac[c] < 0.20]

        X = df[feature_cols].fillna(df[feature_cols].median()).values

        y_cls = df["label"].values.astype(int) if "label" in df.columns else np.zeros(len(df), dtype=int)
        y_rul = df["rul"].values.astype(float) if "rul" in df.columns else np.full(len(df), 365.0)

        logger.info(f"  Features: {len(feature_cols)} | Samples: {len(X):,}")
        logger.info(f"  Class distribution: {dict(zip(*np.unique(y_cls, return_counts=True)))}")

        return X, y_cls, y_rul, feature_cols

    def _split(self, X, y_cls, y_rul, test_size=0.2, val_size=0.1):
        X_train, X_test, yc_train, yc_test, yr_train, yr_test = train_test_split(
            X, y_cls, y_rul, test_size=test_size, stratify=y_cls, random_state=42
        )
        return X_train, X_test, yc_train, yc_test, yr_train, yr_test

    # ── Isolation Forest ──────────────────────────────────────
    def _train_isolation_forest(self, X_train, X_test, y_test, tune=False) -> dict:
        if tune:
            params = self._tune_isolation_forest(X_train)
        else:
            params = {"n_estimators": 200, "contamination": 0.05, "max_samples": "auto"}

        self.isolation_forest = IsolationForest(random_state=42, n_jobs=-1, **params)
        self.isolation_forest.fit(X_train)

        # Évaluation : -1=anomalie=critique, 1=normal
        preds = self.isolation_forest.predict(X_test)
        # Convertir: -1→anomalie(1), 1→normal(0)
        preds_binary = (preds == -1).astype(int)
        y_binary = (y_test > 0).astype(int)  # warning+critical = anomalie

        f1 = f1_score(y_binary, preds_binary, zero_division=0)
        if self.mlflow_enabled:
            mlflow.log_params({f"if_{k}": v for k, v in params.items()})
            mlflow.log_metric("if_f1", f1)

        return {"f1": f1, "params": params}

    def _tune_isolation_forest(self, X_train) -> dict:
        def objective(trial):
            params = {
                "n_estimators":  trial.suggest_int("n_estimators", 100, 500),
                "contamination": trial.suggest_float("contamination", 0.01, 0.15),
                "max_features":  trial.suggest_float("max_features", 0.5, 1.0),
            }
            model = IsolationForest(random_state=42, **params)
            model.fit(X_train)
            scores = model.decision_function(X_train)
            return scores.mean()  # proxy: maximize separation

        study = optuna.create_study(direction="maximize", sampler=TPESampler(seed=42))
        study.optimize(objective, n_trials=20, show_progress_bar=False)
        return study.best_params

    # ── Random Forest ─────────────────────────────────────────
    def _train_random_forest(self, X_train, y_train, X_test, y_test, tune=False) -> dict:
        if tune:
            params = self._tune_random_forest(X_train, y_train)
        else:
            params = {
                "n_estimators": 300, "max_depth": 20,
                "min_samples_split": 5, "class_weight": "balanced",
            }

        self.random_forest = RandomForestClassifier(random_state=42, n_jobs=-1, **params)
        self.random_forest.fit(X_train, y_train)

        y_pred  = self.random_forest.predict(X_test)
        y_proba = self.random_forest.predict_proba(X_test)

        f1_macro = f1_score(y_test, y_pred, average="macro", zero_division=0)
        f1_weighted = f1_score(y_test, y_pred, average="weighted", zero_division=0)
        n_classes = len(np.unique(y_test))
        auc = roc_auc_score(y_test, y_proba, multi_class="ovr", average="macro") \
              if n_classes > 1 else 0.5

        # Feature importance
        importance = pd.Series(
            self.random_forest.feature_importances_,
            index=self.feature_cols
        ).sort_values(ascending=False)
        top_features = importance.head(20).to_dict()

        logger.info(
            "\n  Classification Report:\n"
            + classification_report(
                y_test,
                y_pred,
                labels=[0, 1, 2],
                target_names=["Normal", "Warning", "Critical"],
                zero_division=0,
            )
        )

        if self.mlflow_enabled:
            mlflow.log_params({f"rf_{k}": v for k, v in params.items()})
            mlflow.sklearn.log_model(self.random_forest, "random_forest")

        return {
            "f1_macro": f1_macro, "f1_weighted": f1_weighted,
            "auc": auc, "top_features": top_features, "params": params,
        }

    def _tune_random_forest(self, X_train, y_train) -> dict:
        def objective(trial):
            params = {
                "n_estimators":     trial.suggest_int("n_estimators", 100, 500),
                "max_depth":        trial.suggest_int("max_depth", 5, 30),
                "min_samples_split": trial.suggest_int("min_samples_split", 2, 20),
                "max_features":     trial.suggest_categorical("max_features", ["sqrt", "log2", 0.5]),
                "class_weight":     "balanced",
            }
            cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
            scores = []
            for train_idx, val_idx in cv.split(X_train, y_train):
                rf = RandomForestClassifier(random_state=42, n_jobs=-1, **params)
                rf.fit(X_train[train_idx], y_train[train_idx])
                pred = rf.predict(X_train[val_idx])
                scores.append(f1_score(y_train[val_idx], pred, average="macro", zero_division=0))
            return np.mean(scores)

        study = optuna.create_study(direction="maximize", sampler=TPESampler(seed=42))
        study.optimize(objective, n_trials=30, show_progress_bar=True)
        return study.best_params

    # ── LSTM ──────────────────────────────────────────────────
    def _train_lstm(self, X_train, y_rul_train, X_test, y_rul_test,
                    sequence_length=50, tune=False) -> dict:
        if tune:
            hp = self._tune_lstm(X_train, y_rul_train, sequence_length)
        else:
            hp = {"hidden_size": 128, "num_layers": 2, "dropout": 0.2,
                  "lr": 1e-3, "batch_size": 64}

        input_size = X_train.shape[1]
        self.lstm = LSTMPredictor(
            input_size=input_size,
            hidden_size=hp["hidden_size"],
            num_layers=hp["num_layers"],
            dropout=hp["dropout"],
        ).to(self.device)

        # Créer séquences
        X_seq_train, y_seq_train = self._make_sequences(X_train, y_rul_train, sequence_length)
        X_seq_test,  y_seq_test  = self._make_sequences(X_test,  y_rul_test,  sequence_length)

        if len(X_seq_train) == 0 or len(X_seq_test) == 0:
            logger.warning("  Not enough data for LSTM sequences — skipping LSTM training")
            return {"mae": 999, "rmse": 999, "params": hp}

        train_ds = TensorDataset(
            torch.FloatTensor(X_seq_train),
            torch.FloatTensor(y_seq_train)
        )
        train_loader = DataLoader(train_ds, batch_size=hp["batch_size"], shuffle=True, num_workers=0)

        optimizer = torch.optim.Adam(self.lstm.parameters(), lr=hp["lr"], weight_decay=1e-5)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)
        criterion = nn.HuberLoss()

        best_val_loss = float("inf")
        patience_counter = 0
        epochs = 100
        patience = 15

        logger.info(f"  LSTM training: {len(X_seq_train)} sequences, device={self.device}")

        for epoch in range(epochs):
            self.lstm.train()
            train_loss = 0
            for X_batch, y_batch in train_loader:
                X_batch, y_batch = X_batch.to(self.device), y_batch.to(self.device)
                optimizer.zero_grad()
                pred = self.lstm(X_batch)
                loss = criterion(pred, y_batch)
                loss.backward()
                nn.utils.clip_grad_norm_(self.lstm.parameters(), 1.0)
                optimizer.step()
                train_loss += loss.item()

            # Validation
            self.lstm.eval()
            with torch.no_grad():
                X_val_t = torch.FloatTensor(X_seq_test).to(self.device)
                preds = self.lstm(X_val_t).cpu().numpy()
            val_loss = mean_absolute_error(y_seq_test, preds)
            scheduler.step(val_loss)

            if epoch % 10 == 0:
                logger.debug(f"    Epoch {epoch:3d} | train_loss={train_loss/len(train_loader):.4f} | val_mae={val_loss:.2f}d")

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                torch.save(self.lstm.state_dict(), self.output_dir / "lstm_best.pt")
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    logger.info(f"  Early stopping at epoch {epoch}")
                    break

        # Load best weights
        self.lstm.load_state_dict(torch.load(self.output_dir / "lstm_best.pt", map_location=self.device))

        # Final metrics
        self.lstm.eval()
        with torch.no_grad():
            X_test_t = torch.FloatTensor(X_seq_test).to(self.device)
            final_preds = self.lstm(X_test_t).cpu().numpy()

        mae  = mean_absolute_error(y_seq_test, final_preds)
        rmse = np.sqrt(np.mean((y_seq_test - final_preds) ** 2))

        if self.mlflow_enabled:
            mlflow.pytorch.log_model(self.lstm, "lstm")

        return {"mae": mae, "rmse": rmse, "best_val_loss": best_val_loss, "params": hp}

    def _tune_lstm(self, X_train, y_train, sequence_length) -> dict:
        def objective(trial):
            hp = {
                "hidden_size": trial.suggest_categorical("hidden_size", [64, 128, 256]),
                "num_layers":  trial.suggest_int("num_layers", 1, 3),
                "dropout":     trial.suggest_float("dropout", 0.1, 0.4),
                "lr":          trial.suggest_float("lr", 1e-4, 1e-2, log=True),
                "batch_size":  trial.suggest_categorical("batch_size", [32, 64, 128]),
            }
            model = LSTMPredictor(X_train.shape[1], hp["hidden_size"], hp["num_layers"], hp["dropout"]).to(self.device)
            optimizer = torch.optim.Adam(model.parameters(), lr=hp["lr"])
            X_seq, y_seq = self._make_sequences(X_train[:5000], y_train[:5000], sequence_length)
            if len(X_seq) < 10:
                return 999.0
            ds = TensorDataset(torch.FloatTensor(X_seq), torch.FloatTensor(y_seq))
            loader = DataLoader(ds, batch_size=hp["batch_size"], shuffle=True)
            model.train()
            for _ in range(10):
                for xb, yb in loader:
                    xb, yb = xb.to(self.device), yb.to(self.device)
                    optimizer.zero_grad()
                    nn.HuberLoss()(model(xb), yb).backward()
                    optimizer.step()
            model.eval()
            with torch.no_grad():
                preds = model(torch.FloatTensor(X_seq[:200]).to(self.device)).cpu().numpy()
            return mean_absolute_error(y_seq[:200], preds)

        study = optuna.create_study(direction="minimize", sampler=TPESampler(seed=42))
        study.optimize(objective, n_trials=15, show_progress_bar=True)
        return study.best_params

    @staticmethod
    def _make_sequences(X, y, seq_len):
        if len(X) <= seq_len:
            return np.array([]), np.array([])
        X_seq = np.array([X[i:i + seq_len] for i in range(len(X) - seq_len)])
        y_seq = y[seq_len:]
        return X_seq, y_seq

    # ── Ensemble evaluation ───────────────────────────────────
    def _evaluate_ensemble(self, X_test, y_cls_test, y_rul_test) -> dict:
        if self.random_forest is None:
            return {}

        rf_proba  = self.random_forest.predict_proba(X_test)
        if_scores = -self.isolation_forest.decision_function(X_test)  # higher = more anomalous

        # Ensemble classification : weighted soft voting
        n_classes = rf_proba.shape[1]
        if_contribution = np.zeros((len(X_test), n_classes))
        if_scores_norm = (if_scores - if_scores.min()) / (if_scores.max() - if_scores.min() + 1e-10)

        if n_classes >= 2:
            if_contribution[:, 0] = 1 - if_scores_norm
            if_contribution[:, 1] = if_scores_norm
            if n_classes == 3:
                # Split anomaly score entre warning et critical
                if_contribution[:, 1] = if_scores_norm * 0.5
                if_contribution[:, 2] = if_scores_norm * 0.5
                if_contribution[:, 0] = 1 - if_scores_norm

        ensemble_proba = 0.3 * if_contribution + 0.7 * rf_proba
        ensemble_pred  = np.argmax(ensemble_proba, axis=1)

        f1 = f1_score(y_cls_test, ensemble_pred, average="macro", zero_division=0)
        return {"f1_macro": f1, "ensemble_pred_dist": dict(zip(*np.unique(ensemble_pred, return_counts=True)))}

    # ── Save ──────────────────────────────────────────────────
    def _save_artifacts(self):
        joblib.dump(self.scaler,           self.output_dir / "scaler.pkl")
        joblib.dump(self.isolation_forest, self.output_dir / "isolation_forest.pkl")
        joblib.dump(self.random_forest,    self.output_dir / "random_forest.pkl")
        joblib.dump(self.feature_cols,     self.output_dir / "feature_cols.pkl")
        if self.lstm is not None:
            torch.save(self.lstm.state_dict(), self.output_dir / "lstm_final.pt")
            config = {
                "input_size": len(self.feature_cols),
                "hidden_size": self.lstm.hidden_size,
                "num_layers": self.lstm.num_layers,
            }
            with open(self.output_dir / "lstm_config.json", "w") as f:
                json.dump(config, f)
        logger.info(f"  ✓ All artifacts saved to {self.output_dir}")

    @staticmethod
    def _print_summary(metrics: dict):
        print("\n+-----------------------------------------+")
        print("|           TRAINING SUMMARY              |")
        print("+-----------------------------------------+")
        if "isolation_forest" in metrics:
            print(f"|  Isolation Forest  F1:  {metrics['isolation_forest'].get('f1', 0):.3f}           |")
        if "random_forest" in metrics:
            rf = metrics["random_forest"]
            print(f"|  Random Forest     F1:  {rf['f1_macro']:.3f}  AUC: {rf['auc']:.3f}  |")
        if "lstm" in metrics:
            lstm = metrics["lstm"]
            print(f"|  LSTM              MAE: {lstm['mae']:.1f}d  RMSE: {lstm['rmse']:.1f}d |")
        if "ensemble" in metrics:
            print(f"|  Ensemble          F1:  {metrics['ensemble'].get('f1_macro', 0):.3f}           |")
        print("+-----------------------------------------+")


class _NullContext:
    """Context manager no-op quand MLflow n'est pas disponible."""
    def __enter__(self): return self
    def __exit__(self, *args): pass
