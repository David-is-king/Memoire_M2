# Predictive Maintenance — Moteurs Électriques

Système de maintenance prédictive complet :
**Datasets publics -> Nettoyage 3 niveaux -> Modèles ML -> API FastAPI -> App Flutter**

Compatible ESP32 dès que les capteurs seront prêts (changement de source uniquement).

# Structure du projet

```
predictive_maintenance/
│
├── configs/
│   └── config.yaml                 <- Tous les paramètres centralisés
│
├── data/
│   ├── raw/                        <- Datasets bruts (CWRU, NASA, synthétique)
│   ├── processed/                  <- Après nettoyage L1 + L2
│   └── features/                   <- Features ML-ready (L3)
│
├── src/
│   ├── ingestion/
│   │   └── dataset_loader.py       <- Charge CWRU / NASA IMS / MAFAULDA / synthétique
│   │
│   ├── cleaning/
│   │   └── pipeline.py             <- Pipeline 3 niveaux
│   │       ├── Level1Cleaner       -> Nettoyage brut (bounds, doublons, nulls)
│   │       ├── Level2Cleaner       -> Structuration (resample, interpolation)
│   │       ├── Level3FeatureEng.   -> Feature engineering (FFT, kurtosis, THD...)
│   │       └── CleaningPipeline    -> Orchestrateur (batch + streaming)
│   │
│   ├── training/
│   │   └── trainer.py              <- Entraînement des 3 modèles
│   │       ├── IsolationForest     -> Détection anomalies
│   │       ├── RandomForest        -> Classification (Normal/Warning/Critical)
│   │       └── LSTM + Attention    -> Prédiction RUL (jours restants)
│   │
│   ├── inference/
│   │   └── predictor.py            <- Prédiction temps réel (batch + streaming)
│   │
│   ├── simulator/
│   │   └── esp32_simulator.py      <- Rejoue les datasets comme l'ESP32 réel
│   │       ├── ESP32Simulator      -> WebSocket + MQTT publisher
│   │       └── StreamingPipeline   -> Connecte simulator → pipeline → API
│   │
│   ├── monitoring/
│   │   └── drift_monitor.py        <- Détection drift (PSI + KS) + auto-retrain
│   │
│   └── api/
│       └── main.py                 <- FastAPI (REST + WebSocket pour Flutter)
│
├── models/
│   ├── artifacts/                  <- Modèles entraînés (.pkl, .pt)
│   └── registry/                   <- Métriques par version
│
├── scripts/
│   └── run_pipeline.py             <- Script principal tout-en-un
│
├── tests/
├── requirements.txt
└── configs/config.yaml
```


# Démarrage

### 1. Installation
```bash

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Entraînement complet
```bash
python scripts/run_pipeline.py --mode train --motors 15
```
Génère 15 moteurs synthétiques, nettoie en 3 niveaux, entraîne les 3 modèles.

### 3. Simulateur ESP32 (temps réel)
```bash
python scripts/run_pipeline.py --mode simulate --speedup 50
```
Rejoue les données à 50× la vitesse réelle → prédictions en temps réel.

### 4. API FastAPI
```bash
python scripts/run_pipeline.py --mode api
# http://localhost:8000/docs
```

### 5. Tout en même temps
```bash
python scripts/run_pipeline.py --mode full --tune --motors 20
```


## Pipeline Nettoyage 3 Niveaux

| Niveau | Classe                  | Opérations 
|--------|-------------------------|-------------------------------------------------------|
| **L1** | `Level1Cleaner`         | Doublons, bounds physiques, NaN, outliers 6σ          |
| **L2** | `Level2Cleaner`         | Rééchantillonnage 100Hz, interpolation, alignement    |
| **L3** | `Level3FeatureEngineer` | RMS, Kurtosis, FFT, THD, rolling stats, cross-sensors |



## Modèles

| Modèle               | Type                  | Cible 
|----------------------|-----------------------|-----------------------------
| **Isolation Forest** | Non supervisé         | Détection anomalies         |
| **Random Forest**    | Classification        | Normal / Warning / Critical |
| **LSTM + Attention** | Régression temporelle | RUL (jours restants)        |
| **Ensemble**         | Soft voting           | HealthScore final (0–100)   |



## Intégration ESP32

Le simulateur et le vrai ESP32 utilisent **la même interface**.

### Maintenant (simulateur)
```python
simulator = ESP32Simulator(data=df, speedup=50)
await simulator.stream_to_callback(streaming.ingest)
```

### Plus tard (ESP32 réel via MQTT)
```python
# Même StreamingPipeline, source différente
client.on_message = lambda msg: asyncio.run(streaming.ingest(SensorReading.from_mqtt(msg)))
```

### Code Arduino ESP32 (à ajouter plus tard)
```cpp
// Envoyer les données au même endpoint API
HTTPClient http;
http.begin("http://YOUR_SERVER_IP:8000/api/v1/ingest");
http.addHeader("Content-Type", "application/json");
String payload = "{\"motor_id\":\"motor_001\","
    "\"temperature\":" + String(temp) + ","
    "\"vibration_x\":" + String(vib_x) + ","
    "\"current\":" + String(current) + "}";
http.POST(payload);
```

---

## API Endpoints

| Method | Endpoint                  | Description |
|--------|---------------------------|-------------|
| GET    | `/api/v1/devices`         | Liste tous les moteurs |
| GET    | `/api/v1/devices/{id}`    | Détail d'un moteur |
| GET    | `/api/v1/predictions/{id}`| Dernière prédiction |
| POST   | `/api/v1/ingest`          | **Recevoir données ESP32** |
| GET    | `/api/v1/alerts`          | Liste des alertes |
| WS     | `/ws/all`                 | Updates temps réel → Flutter |
| WS     | `/ws/devices/{id}`        | Updates moteur spécifique |

---

## Auto-retrain (drift monitoring)

Le `DriftMonitor` surveille en continu :
- **PSI < 0.10** → Pas de drift
- **PSI 0.10–0.25** → Drift mineur (log)
- **PSI > 0.25** → Drift majeur → auto-retrain déclenché

---

## MLflow Tracking

```bash
mlflow server --host 0.0.0.0 --port 5000
# http://localhost:5000
```
