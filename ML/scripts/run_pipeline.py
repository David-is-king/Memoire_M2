# =============================================================================
# scripts/run_pipeline.py
#
# Script principal — lance tout le pipeline de bout en bout en 5 étapes :
#
#   Étape 1 — INGESTION    : Charge CWRU (.mat) et/ou MAFAULDA (.csv)
#                            et les convertit au format standard ESP32.
#
#   Étape 2 — CLEANING     : Pipeline 3 niveaux (L1 → L2 → L3).
#                            Sortie : features ML-ready (1 ligne = 1 fenêtre).
#
#   Étape 3 — TRAINING     : Entraîne les 3 modèles (IF, RF, LSTM).
#                            Sauvegarde les artefacts dans models/artifacts/.
#
#   Étape 4 — MONITORING   : Calcule les statistiques de référence pour
#                            la détection de drift PSI/KS.
#
#   Étape 5 — SIMULATION   : Rejoue les données comme l'ESP32 en temps réel
#             ou API        : Lance le serveur FastAPI.
#
# USAGE :
#   python scripts/run_pipeline.py --mode train          ← Entraîner les modèles
#   python scripts/run_pipeline.py --mode simulate       ← Simuler l'ESP32
#   python scripts/run_pipeline.py --mode api            ← Lancer l'API FastAPI
#   python scripts/run_pipeline.py --mode full           ← Tout en même temps
#   python scripts/run_pipeline.py --mode train --tune   ← Avec Optuna
# =============================================================================

import sys
import asyncio
import argparse
import pandas as pd                    # ← CORRECTION : import manquant dans la version originale
from pathlib import Path
from typing import Optional
from loguru import logger

# Ajouter le répertoire racine au path Python pour résoudre les imports relatifs
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.dataset_loader import DatasetLoader
from src.cleaning.pipeline import CleaningPipeline
from src.training.trainer import PredictiveMaintenanceTrainer
from src.inference.predictor import PredictiveMaintenancePredictor
from src.monitoring.drift_monitor import DriftMonitor
from src.simulator.esp32_simulator import ESP32Simulator, StreamingPipeline


def setup_logging():
    """Configure Loguru : console (INFO) + fichier rotatif (DEBUG)."""
    logger.remove()
    logger.add(
        sys.stderr,
        level   = "INFO",
        format  = "<green>{time:HH:mm:ss}</green> | <level>{level:8}</level> | {message}"
    )
    Path("logs").mkdir(exist_ok=True)
    logger.add("logs/pipeline.log", level="DEBUG", rotation="100 MB")


# =============================================================================
# ÉTAPE 1 — INGESTION
# =============================================================================

def step_ingest(
    use_synthetic: bool = False,
    include_public_datasets: bool = True,
    n_motors: int = 5,
    duration_hours: float = 2.0,
    sampling_rate_hz: int = 100,
    mafaulda_max_files_per_class: Optional[int] = 60,
    mafaulda_max_seconds: Optional[float] = None,
    cwru_max_files: Optional[int] = None,
) -> pd.DataFrame:
    """
    Charge les datasets bruts et les fusionne au format standard.
    
    Priorité :
      1. CWRU (.mat)    → si les fichiers sont présents dans data/raw/cwru/
      2. MAFAULDA (.csv) → si le fichier est présent dans data/raw/mafaulda/
      3. Synthétique    → si aucun dataset réel n'est disponible (ou use_synthetic=True)
    
    ╔══════════════════════════════════════════════════════════════════╗
    ║  CORRECTION : signature corrigée pour correspondre à l'appel    ║
    ║  dans main() qui passe n_motors, duration_hours, sampling_rate_hz║
    ╚══════════════════════════════════════════════════════════════════╝
    
    Args:
        use_synthetic:            Si True, génère des données synthétiques
        include_public_datasets:  Si True, charge CWRU + MAFAULDA
        n_motors:                 Nombre de moteurs synthétiques si fallback
        duration_hours:           Durée simulée par moteur synthétique
        sampling_rate_hz:         Fréquence d'échantillonnage des données synthétiques
        mafaulda_max_files_per_class: Plafond de fichiers MAFAULDA par classe finale
            (0-4). Le dataset brut complet fait ~1 950 essais × ~250 000 lignes
            (~490M lignes) — None = tout charger (long, gourmand en RAM).
        mafaulda_max_seconds:     Tronque chaque essai MAFAULDA aux N premières
            secondes (les essais durent 5s réel à 50kHz). None = essai complet.

    Returns:
        DataFrame fusionné au format standard
    """
    logger.info("━" * 60)
    logger.info("ÉTAPE 1 — INGESTION & STANDARDISATION")

    loader  = DatasetLoader(raw_dir="data/raw")
    all_dfs = []

    if include_public_datasets and not use_synthetic:

        # ── Chargement CWRU ───────────────────────────────────────────────────
        # Ajoute ici tous les fichiers .mat présents dans data/raw/cwru/
        # Convention de nommage CWRU : 97.mat (Normal), 105.mat (Ball 0.007"),
        # 118.mat (Inner Race 0.007"), 130.mat (Outer Race 0.007"), etc.
        cwru_dir   = Path("data/raw/cwru")
        cwru_files = sorted(cwru_dir.glob("*.mat")) if cwru_dir.exists() else []
        if cwru_max_files is not None:
            cwru_files = cwru_files[:cwru_max_files]

        if cwru_files:
            logger.info(f"  CWRU : {len(cwru_files)} fichier(s) trouvé(s)")
            for mat_path in cwru_files:
                try:
                    df_cwru = loader.load_cwru_file(mat_path.name)
                    all_dfs.append(df_cwru)
                    logger.info(f"  ✓ {mat_path.name} : {len(df_cwru):,} lignes | label={df_cwru['label'].iloc[0]}")
                except Exception as e:
                    logger.error(f"  ✗ {mat_path.name} : {e}")
        else:
            logger.warning("  CWRU : aucun fichier .mat trouvé dans data/raw/cwru/")

        # ── Chargement MAFAULDA ───────────────────────────────────────────────
        # Dataset brut UFRJ : arborescence de dossiers par défaut sous data/raw/mafaulda/
        mafaulda_dir = Path("data/raw/mafaulda")
        if mafaulda_dir.exists():
            try:
                mafaulda_files = loader.iter_mafaulda_files(max_files_per_class=mafaulda_max_files_per_class)
                logger.info(f"  MAFAULDA : {len(mafaulda_files)} essai(s) sélectionné(s), lecture en cours...")
                n_loaded = 0
                for df_maf in loader.load_mafaulda_files(
                    max_files_per_class=mafaulda_max_files_per_class,
                    max_seconds=mafaulda_max_seconds,
                ):
                    all_dfs.append(df_maf)
                    n_loaded += 1
                logger.info(f"  ✓ MAFAULDA : {n_loaded} essai(s) chargé(s)")
            except FileNotFoundError as e:
                logger.warning(f"  MAFAULDA : {e}")
            except Exception as e:
                logger.error(f"  ✗ MAFAULDA : {e}")
        else:
            logger.warning("  MAFAULDA : dossier data/raw/mafaulda/ introuvable")

    # ── Fallback synthétique ─────────────────────────────────────────────────
    if use_synthetic or not all_dfs:
        reason = "demandé" if use_synthetic else "aucune donnée réelle disponible"
        logger.info(f"  Données synthétiques : {reason}")
        df_synth = loader.generate_synthetic(
            n_motors       = n_motors,
            duration_hours = duration_hours,
            sampling_rate_hz = sampling_rate_hz,
        )
        all_dfs.append(df_synth)

    # ── Fusion ───────────────────────────────────────────────────────────────
    combined = pd.concat(all_dfs, ignore_index=True)

    # Afficher la distribution des labels et origines pour vérification
    label_dist  = combined["label"].value_counts().sort_index().to_dict()
    origin_dist = combined["data_origin"].value_counts().to_dict()
    logger.info(f"✓ Ingestion terminée : {len(combined):,} lignes")
    logger.info(f"  Distribution labels  : {label_dist}")
    logger.info(f"  Origines des données : {origin_dist}")

    # Sauvegarder les données brutes combinées (pour le simulateur)
    Path("data/raw").mkdir(parents=True, exist_ok=True)
    combined.to_parquet("data/raw/combined_raw.parquet", index=False)

    return combined


# =============================================================================
# ÉTAPE 2 — CLEANING
# =============================================================================

def step_clean(raw_df: pd.DataFrame, resample_hz: int = 100, window_size: int = 256) -> pd.DataFrame:
    """
    Applique le pipeline de nettoyage 3 niveaux et sauvegarde les intermédiaires.

    Args:
        raw_df:      DataFrame brut issu de step_ingest()
        resample_hz: Fréquence de rééchantillonnage cible pour le Level 2
        window_size: Taille des fenêtres L3, en échantillons post-resample.
            IMPORTANT : chaque essai MAFAULDA dure ~5s réel → à 100Hz cela ne
            donne que ~500 points après le Level 2. Avec window_size=512
            (l'ancien défaut), aucune fenêtre n'est produite pour MAFAULDA
            (Level3FeatureEngineer._extract_motor_features rejette tout moteur
            plus court que window_size) : tous les essais MAFAULDA seraient
            silencieusement exclus de l'entraînement. 256 (2.56s) laisse de la
            marge pour obtenir plusieurs fenêtres même sur ces essais courts.

    Returns:
        features_df : DataFrame features ML-ready (1 ligne = 1 fenêtre L3)
    """
    logger.info("━" * 60)
    logger.info("ÉTAPE 2 — PIPELINE NETTOYAGE (3 niveaux)")

    pipeline = CleaningPipeline(config={
        "level1": {"null_strategy": "flag"},
        "level2": {"resample_hz": resample_hz, "max_gap_seconds": 5.0},
        "level3": {"window_size": window_size, "overlap": 0.5},
    })

    # Création des dossiers de sortie
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    Path("data/features").mkdir(parents=True, exist_ok=True)

    features_df, reports = pipeline.run(
        raw_df,
        save_intermediates = True,         # Sauvegarde L1 et L2 pour inspection
        output_dir         = "data/processed",
    )

    # Sauvegarde du tableau features final
    features_df.to_parquet("data/features/features.parquet", index=False)

    # Affichage des rapports de chaque niveau
    logger.info("  Résumé des 3 niveaux :")
    for r in reports:
        logger.info(
            f"    L{r.level} : {r.input_rows:,} → {r.output_rows:,} lignes "
            f"(retention {r.retention_rate:.1%})"
        )
        for issue in r.issues[:5]:  # Afficher au max 5 problèmes par niveau
            logger.debug(f"      ⚠ {issue}")

    logger.info(
        f"✓ Features générées : {len(features_df):,} fenêtres × {len(features_df.columns)} features"
    )
    return features_df


# =============================================================================
# ÉTAPE 3 — TRAINING
# =============================================================================

def step_train(features_df: pd.DataFrame, tune: bool = False) -> dict:
    """
    Entraîne les 3 modèles et sauvegarde les artefacts.
    
    Args:
        features_df: DataFrame features issu de step_clean()
        tune:        Si True, active Optuna pour l'optimisation des hyperparamètres
    
    Returns:
        Dictionnaire de métriques
    """
    logger.info("━" * 60)
    logger.info("ÉTAPE 3 — ENTRAÎNEMENT DES MODÈLES")
    logger.info(f"  Tuning Optuna : {'OUI' if tune else 'NON (hyperparamètres par défaut)'}")

    trainer = PredictiveMaintenanceTrainer(
        output_dir      = "models/artifacts",
        mlflow_uri      = "http://localhost:5000",
        experiment_name = "predictive_maintenance",
    )

    metrics = trainer.train(features_df, tune_hyperparams=tune, sequence_length=50)

    # Sauvegarde des métriques en JSON pour consultation ultérieure
    import json
    Path("models/registry").mkdir(parents=True, exist_ok=True)
    metrics_serializable = {
        k: {kk: str(vv) for kk, vv in v.items()}
        if isinstance(v, dict) else str(v)
        for k, v in metrics.items()
    }
    with open("models/registry/latest_metrics.json", "w") as f:
        json.dump(metrics_serializable, f, indent=2)

    logger.info("✓ Métriques sauvegardées dans models/registry/latest_metrics.json")
    return metrics


# =============================================================================
# ÉTAPE 4 — SETUP DU MONITORING (Détection de drift)
# =============================================================================

def step_setup_monitoring(features_df: pd.DataFrame) -> DriftMonitor:
    """
    Initialise le DriftMonitor avec les données d'entraînement comme référence.
    
    Les statistiques de référence (PSI bins, KS samples) sont sauvegardées pour
    être comparées aux nouvelles données arrivant de l'ESP32.
    """
    logger.info("━" * 60)
    logger.info("ÉTAPE 4 — INITIALISATION DU DRIFT MONITOR")

    monitor = DriftMonitor(
        reference_data = features_df,
        artifacts_dir  = "models/artifacts",
    )
    logger.info("✓ Statistiques de référence calculées et sauvegardées")
    return monitor


# =============================================================================
# ÉTAPE 5 — SIMULATION ESP32
# =============================================================================

async def step_simulate(raw_df: pd.DataFrame, speedup: float = 50.0):
    """
    Simule l'ESP32 en rejouant les données historiques à vitesse accélérée.
    
    Utile pour tester le pipeline temps réel AVANT d'avoir le vrai ESP32.
    La même StreamingPipeline sera utilisée avec les données réelles.
    
    Args:
        raw_df:  DataFrame brut (données à rejouer)
        speedup: Facteur de vitesse (50 = 50× plus vite que le temps réel)
    """
    logger.info("━" * 60)
    logger.info(f"ÉTAPE 5 — SIMULATEUR ESP32 (×{speedup} vitesse réelle)")

    predictor = PredictiveMaintenancePredictor(artifacts_dir="models/artifacts")
    cleaner   = CleaningPipeline()

    results_log = []

    async def on_prediction(pred):
        """Callback appelé à chaque nouvelle prédiction — logge et sauvegarde."""
        results_log.append({
            "motor_id":     pred.motor_id,
            "status":       pred.status,
            "health":       pred.health_score,
            "fail_prob":    f"{pred.failure_probability:.1%}",
            "rul_days":     f"{pred.rul_days:.0f}",
            "top_features": ", ".join(pred.anomaly_features[:2]),
        })

    streaming = StreamingPipeline(
        predictor         = predictor,
        cleaning_pipeline = cleaner,
        buffer_size       = 512,
        on_prediction     = on_prediction,
    )

    simulator = ESP32Simulator(data=raw_df, speedup=speedup, noise_factor=0.015)

    logger.info(f"  Démarrage du simulateur — Ctrl+C pour arrêter")

    try:
        await simulator.stream_to_callback(streaming.ingest)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        logger.info(f"\n  Prédictions effectuées : {len(results_log)}")
        if results_log:
            df_results = pd.DataFrame(results_log)
            df_results.to_csv("logs/simulation_results.csv", index=False)
            logger.info("  Résultats sauvegardés dans logs/simulation_results.csv")
            print("\n  Dernières prédictions :")
            print(df_results.tail(10).to_string(index=False))


def step_api():
    """Lance le serveur FastAPI."""
    import uvicorn
    logger.info("━" * 60)
    logger.info("ÉTAPE 5 — SERVEUR API")
    logger.info("  → http://localhost:8000")
    logger.info("  → http://localhost:8000/docs  (Swagger interactif)")
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=False)


# =============================================================================
# MAIN — Point d'entrée
# =============================================================================

def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="Pipeline Maintenance Prédictive")
    parser.add_argument(
        "--mode",
        choices    = ["train", "simulate", "api", "full"],
        default    = "train",
        help       = "Mode d'exécution"
    )
    parser.add_argument(
        "--tune",
        action     = "store_true",
        help       = "Activer l'optimisation Optuna des hyperparamètres"
    )
    parser.add_argument(
        "--motors",
        type       = int,
        default    = 5,
        help       = "Nombre de moteurs synthétiques (si pas de données réelles)"
    )
    parser.add_argument(
        "--duration-hours",
        type       = float,
        default    = 2.0,
        help       = "Durée simulée par moteur (heures)"
    )
    parser.add_argument(
        "--speedup",
        type       = float,
        default    = 50.0,
        help       = "Facteur d'accélération du simulateur"
    )
    parser.add_argument(
        "--sample-rate",
        type       = int,
        default    = 100,
        help       = "Fréquence d'échantillonnage (Hz)"
    )
    parser.add_argument(
        "--include-public-datasets",
        action     = "store_true",
        help       = "Charger CWRU + MAFAULDA si disponibles"
    )
    parser.add_argument(
        "--mafaulda-max-files-per-class",
        type       = int,
        default    = 60,
        help       = "Plafond d'essais MAFAULDA par classe (0-4). -1 = tout charger (~1950 essais, lent)"
    )
    parser.add_argument(
        "--mafaulda-max-seconds",
        type       = float,
        default    = None,
        help       = "Tronque chaque essai MAFAULDA aux N premières secondes (défaut : essai complet, 5s)"
    )
    parser.add_argument(
        "--window-size",
        type       = int,
        default    = 256,
        help       = "Taille des fenêtres L3 en échantillons post-resample (voir step_clean)"
    )
    parser.add_argument(
        "--cwru-max-files",
        type       = int,
        default    = None,
        help       = "Plafond de fichiers .mat CWRU à charger (défaut : tous, ~161 fichiers, ~36M lignes)"
    )
    args = parser.parse_args()
    mafaulda_max_files = None if args.mafaulda_max_files_per_class == -1 else args.mafaulda_max_files_per_class

    logger.info("╔══════════════════════════════════════════════╗")
    logger.info("║   PREDICTIVE MAINTENANCE PIPELINE            ║")
    logger.info("║   Moteurs Électriques · ESP32 · FastAPI      ║")
    logger.info(f"║   Mode : {args.mode:<37s}║")
    logger.info("╚══════════════════════════════════════════════╝\n")

    raw_df = None  # Initialisé ici pour être accessible dans le bloc "full"

    # ── Modes qui nécessitent l'entraînement ─────────────────────────────────
    if args.mode in ("train", "full"):
        raw_df = step_ingest(
            use_synthetic           = not args.include_public_datasets,
            include_public_datasets = args.include_public_datasets,
            n_motors                = args.motors,
            duration_hours          = args.duration_hours,
            sampling_rate_hz        = args.sample_rate,
            mafaulda_max_files_per_class = mafaulda_max_files,
            mafaulda_max_seconds         = args.mafaulda_max_seconds,
            cwru_max_files               = args.cwru_max_files,
        )
        features_df = step_clean(raw_df, resample_hz=args.sample_rate, window_size=args.window_size)
        metrics     = step_train(features_df, tune=args.tune)
        step_setup_monitoring(features_df)

    # ── Mode simulateur seul ──────────────────────────────────────────────────
    if args.mode == "simulate":
        # Charger les données brutes sauvegardées précédemment (ou générer de synthétiques)
        raw_path = Path("data/raw/combined_raw.parquet")
        if raw_path.exists():
            raw_df = pd.read_parquet(raw_path)
        else:
            logger.info("Pas de données brutes → génération synthétique pour la simulation")
            loader = DatasetLoader()
            raw_df = loader.generate_synthetic(n_motors=5, duration_hours=10.0)
        asyncio.run(step_simulate(raw_df, speedup=args.speedup))

    # ── Mode API seul ─────────────────────────────────────────────────────────
    if args.mode == "api":
        step_api()

    # ── Mode full : API + simulateur en parallèle ─────────────────────────────
    if args.mode == "full":
        import subprocess
        # Lance l'API en arrière-plan
        api_proc = subprocess.Popen(
            ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
        )
        try:
            asyncio.run(step_simulate(raw_df, speedup=args.speedup))
        finally:
            api_proc.terminate()


if __name__ == "__main__":
    main()
