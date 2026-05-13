"""
scripts/run_pipeline.py

Script principal — lance tout le pipeline de bout en bout :
  1. Télécharge / génère les datasets
  2. Nettoyage 3 niveaux
  3. Entraînement des modèles
  4. Évaluation + sauvegarde
  5. Lance le simulateur ESP32 + l'API FastAPI

Usage :
  python scripts/run_pipeline.py --mode train         # entraînement complet
  python scripts/run_pipeline.py --mode simulate      # simulateur temps réel
  python scripts/run_pipeline.py --mode api           # API seulement
  python scripts/run_pipeline.py --mode full          # tout (train + api + sim)
  python scripts/run_pipeline.py --mode train --tune  # avec Optuna tuning
"""

import sys
import asyncio
import argparse
from pathlib import Path
from loguru import logger

# Ajouter le root au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.dataset_loader import DatasetLoader
from src.cleaning.pipeline import CleaningPipeline
from src.training.trainer import PredictiveMaintenanceTrainer
from src.inference.predictor import PredictiveMaintenancePredictor
from src.monitoring.drift_monitor import DriftMonitor
from src.simulator.esp32_simulator import ESP32Simulator, StreamingPipeline


def setup_logging():
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level:8}</level> | {message}")
    logger.add("logs/pipeline.log", level="DEBUG", rotation="100 MB")
    Path("logs").mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────
# ÉTAPE 1 : INGESTION
# ─────────────────────────────────────────────────────────

def step_ingest(
    use_synthetic: bool = True,
    n_motors: int = 15,
    duration_hours: int = 1,
    sampling_rate_hz: int = 10,
    include_public_datasets: bool = False,
) -> "pd.DataFrame":
    import pandas as pd
    logger.info("━" * 60)
    logger.info("STEP 1 — DATA INGESTION")
    loader = DatasetLoader(raw_dir="data/raw")

    dfs = []

    if use_synthetic:
        # Données synthétiques complètes (tous capteurs ESP32)
        df_synth = loader.generate_synthetic(
            n_motors=n_motors,
            duration_hours=duration_hours,
            fault_rate=0.20,
            sampling_rate_hz=sampling_rate_hz,
        )
        dfs.append(df_synth)
        logger.info(f"  Synthetic: {len(df_synth):,} rows")

    if not include_public_datasets:
        combined = pd.concat(dfs, ignore_index=True)
        Path("data/raw").mkdir(parents=True, exist_ok=True)
        combined.to_parquet("data/raw/combined_raw.parquet", index=False)
        logger.info(f"  Synthetic-only total: {len(combined):,} rows - {combined['motor_id'].nunique()} motors")
        return combined

    # Essayer de charger les datasets publics (fallback sur synthétique si absent)
    try:
        df_cwru = loader.load_cwru(fault_type="all")
        dfs.append(df_cwru)
        logger.info(f"  CWRU: {len(df_cwru):,} rows")
    except Exception as e:
        logger.warning(f"  CWRU load failed: {e}")

    try:
        df_nasa = loader.load_nasa_ims(test_set=1)
        dfs.append(df_nasa)
        logger.info(f"  NASA IMS: {len(df_nasa):,} rows")
    except Exception as e:
        logger.warning(f"  NASA IMS load failed: {e}")

    combined = pd.concat(dfs, ignore_index=True)
    Path("data/raw").mkdir(parents=True, exist_ok=True)
    combined.to_parquet("data/raw/combined_raw.parquet", index=False)
    logger.info(f"  ✓ Total: {len(combined):,} rows — {combined['motor_id'].nunique()} motors")
    return combined


# ─────────────────────────────────────────────────────────
# ÉTAPE 2 : CLEANING
# ─────────────────────────────────────────────────────────

def step_clean(raw_df, resample_hz: int = 10) -> "pd.DataFrame":
    logger.info("━" * 60)
    logger.info("STEP 2 — CLEANING PIPELINE (3 levels)")

    pipeline = CleaningPipeline(config={
        "level1": {"null_strategy": "flag"},
        "level2": {"resample_hz": resample_hz, "max_gap_seconds": 5.0},
        "level3": {"window_size": 512, "overlap": 0.5},
    })

    Path("data/processed").mkdir(parents=True, exist_ok=True)
    Path("data/features").mkdir(parents=True, exist_ok=True)

    features_df, reports = pipeline.run(
        raw_df,
        save_intermediates=True,
        output_dir="data/processed",
    )

    features_df.to_parquet("data/features/features.parquet", index=False)

    for r in reports:
        logger.info(f"  Level {r.level}: {r.input_rows:,} → {r.output_rows:,} rows | retention={r.retention_rate:.1%}")
        for issue in r.issues[:5]:
            logger.debug(f"    ⚠ {issue}")

    logger.info(f"  ✓ Features: {len(features_df):,} windows × {len(features_df.columns)} features")
    return features_df


# ─────────────────────────────────────────────────────────
# ÉTAPE 3 : TRAINING
# ─────────────────────────────────────────────────────────

def step_train(features_df, tune: bool = False) -> dict:
    logger.info("━" * 60)
    logger.info("STEP 3 — MODEL TRAINING")
    logger.info(f"  Hyperparameter tuning (Optuna): {'YES' if tune else 'NO'}")

    trainer = PredictiveMaintenanceTrainer(
        output_dir="models/artifacts",
        mlflow_uri="http://localhost:5000",
        experiment_name="predictive_maintenance",
    )

    metrics = trainer.train(features_df, tune_hyperparams=tune, sequence_length=50)

    # Sauvegarder les métriques
    import json
    Path("models/registry").mkdir(exist_ok=True)
    with open("models/registry/latest_metrics.json", "w") as f:
        json.dump({k: {kk: str(vv) for kk, vv in v.items()} if isinstance(v, dict) else str(v)
                   for k, v in metrics.items()}, f, indent=2)

    return metrics


# ─────────────────────────────────────────────────────────
# ÉTAPE 4 : DRIFT MONITORING SETUP
# ─────────────────────────────────────────────────────────

def step_setup_monitoring(features_df):
    logger.info("━" * 60)
    logger.info("STEP 4 — DRIFT MONITOR SETUP")
    monitor = DriftMonitor(
        reference_data=features_df,
        artifacts_dir="models/artifacts",
    )
    logger.info("  ✓ Reference statistics computed and saved")
    return monitor


# ─────────────────────────────────────────────────────────
# ÉTAPE 5 : SIMULATION + API
# ─────────────────────────────────────────────────────────

async def step_simulate(raw_df, speedup: float = 50.0):
    logger.info("━" * 60)
    logger.info("STEP 5 — ESP32 SIMULATOR + STREAMING PIPELINE")

    predictor = PredictiveMaintenancePredictor(artifacts_dir="models/artifacts")
    cleaner   = CleaningPipeline()

    results_log = []

    async def on_prediction(pred):
        results_log.append({
            "motor_id":    pred.motor_id,
            "status":      pred.status,
            "health":      pred.health_score,
            "failure_prob": f"{pred.failure_probability:.1%}",
            "rul_days":    f"{pred.rul_days:.0f}",
        })

    streaming = StreamingPipeline(
        predictor=predictor,
        cleaning_pipeline=cleaner,
        buffer_size=512,
        on_prediction=on_prediction,
    )

    simulator = ESP32Simulator(data=raw_df, speedup=speedup, noise_factor=0.015)

    logger.info(f"  Streaming at {speedup}x speed...")
    logger.info("  Press Ctrl+C to stop\n")

    try:
        await simulator.stream_to_callback(streaming.ingest)
    except asyncio.CancelledError:
        pass
    finally:
        logger.info(f"\n  Predictions made: {len(results_log)}")
        if results_log:
            import pandas as pd
            pd.DataFrame(results_log).to_csv("logs/simulation_results.csv", index=False)


def step_api():
    import uvicorn
    logger.info("━" * 60)
    logger.info("STEP 5 — API SERVER")
    logger.info("  → http://localhost:8000")
    logger.info("  → http://localhost:8000/docs (Swagger)")
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=False)


# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────

def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="Predictive Maintenance Pipeline")
    parser.add_argument("--mode",    choices=["train", "simulate", "api", "full"], default="train")
    parser.add_argument("--tune",    action="store_true", help="Optuna hyperparameter tuning")
    parser.add_argument("--motors",  type=int, default=15, help="Number of synthetic motors")
    parser.add_argument("--speedup", type=float, default=50.0, help="Simulator speedup factor")
    parser.add_argument("--duration-hours", type=int, default=1, help="Synthetic data duration per motor")
    parser.add_argument("--sample-rate", type=int, default=10, help="Synthetic data sampling rate in Hz")
    parser.add_argument("--include-public-datasets", action="store_true", help="Also load CWRU/NASA datasets")
    args = parser.parse_args()

    logger.info("╔══════════════════════════════════════════════╗")
    logger.info("║   PREDICTIVE MAINTENANCE PIPELINE            ║")
    logger.info("║   Electric Motors · ESP32 · FastAPI · LSTM   ║")
    logger.info(f"║   Mode: {args.mode:37s}║")
    logger.info("╚══════════════════════════════════════════════╝\n")

    if args.mode in ("train", "full"):
        raw_df      = step_ingest(
            use_synthetic=True,
            n_motors=args.motors,
            duration_hours=args.duration_hours,
            sampling_rate_hz=args.sample_rate,
            include_public_datasets=args.include_public_datasets,
        )
        features_df = step_clean(raw_df, resample_hz=args.sample_rate)
        metrics     = step_train(features_df, tune=args.tune)
        step_setup_monitoring(features_df)

    if args.mode == "simulate":
        import pandas as pd
        try:
            raw_df = pd.read_parquet("data/raw/combined_raw.parquet")
        except FileNotFoundError:
            logger.info("Raw data not found — generating synthetic data for simulation")
            raw_df = DatasetLoader().generate_synthetic(n_motors=5, duration_hours=100)

        asyncio.run(step_simulate(raw_df, speedup=args.speedup))

    if args.mode == "api":
        step_api()

    if args.mode == "full":
        # Lance simultanément API + simulateur
        import subprocess, threading
        api_proc = subprocess.Popen(["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"])
        try:
            asyncio.run(step_simulate(raw_df, speedup=args.speedup))
        finally:
            api_proc.terminate()


if __name__ == "__main__":
    main()
