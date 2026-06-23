# ce fichier permet de charger les datasets publics et les convertit au format standard 
# attendu par le pipeline, du genre mêmes colonnes que l'ESP32.

import os
import numpy as np
import pandas as pd
from pathlib import Path
from loguru import logger
from scipy.io import loadmat

class DatasetLoader:

# les colonnes standars
    STANDARD_COLS = [
        "timestamp", "motor_id", "temperature", "vibration_x",
        "vibration_y", "vibration_z", "current", "voltage",
        "acoustic_db", "label", "rul"
    ]

    def __init__(self, raw_dir: str = "data/raw"):
        self.raw_dir = Path(raw_dir)

# Chargement du dataset CWRU Bearing Dataset
    def load_cwru_file(self, file_name: str) -> pd.DataFrame:
        
        # on charge un fichier .mat de CWRU et le formate selon le standard ESP32 
        path = self.raw_dir / "cwru" / file_name
        if not path.exists():
            raise FileNotFoundError(f"Fichier introuvable : {path}")

        logger.info(f"Chargement et standardisation du fichier CWRU : {file_name}")
        mat = loadmat(str(path))
        
        # on cherche les clés de vibration (ex: X105_DE_time)
        de_key = [k for k in mat.keys() if "DE_time" in k]
        fe_key = [k for k in mat.keys() if "FE_time" in k]
        
        if not de_key:
            raise ValueError(f"Pas de données Drive End (DE) dans {file_name}")
            
        v_x = mat[de_key[0]].ravel()
        n_samples = len(v_x)
        
        # Création du DataFrame standardisé
        df = pd.DataFrame(index=range(n_samples), columns=self.STANDARD_COLS)
        
        # Détermination du label (0: Normal, 1: Panne)
        is_normal = "normal" in file_name.lower() or "97" in file_name
        label_val = 0 if is_normal else 1

        # Remplissage avec les données disponibles
        df["motor_id"] = f"CWRU_{file_name.replace('.mat', '')}"
        df["vibration_x"] = v_x
        df["vibration_y"] = mat[fe_key[0]].ravel() if fe_key else np.random.normal(0, 0.02, n_samples)
        df["vibration_z"] = np.random.normal(0, 0.02, n_samples)
        
        # Si le moteur est en panne la température et le courant sont plus élevés
        base_temp = 42.0 if is_normal else 68.0
        base_current = 2.1 if is_normal else 3.8
        
        df["temperature"] = base_temp + np.random.normal(0, 1.2, n_samples)
        df["current"] = base_current + 0.2 * np.abs(v_x) + np.random.normal(0, 0.1, n_samples)
        df["voltage"] = 220.0 + np.random.normal(0, 1.0, n_samples)
        df["acoustic_db"] = (60.0 if is_normal else 82.0) + np.random.normal(0, 1.5, n_samples)
        
        df["label"] = label_val
        df["rul"] = 365.0 if is_normal else np.linspace(15.0, 0.0, n_samples) # RUL décroissant si panne
        
        # Fréquence d'échantillonnage CWRU d'origine (12 kHz)
        df["timestamp"] = pd.date_range(start=pd.Timestamp.now(), periods=n_samples, freq="83U") # ~12kHz
        
        return df


# Chargement du dataset MAFAULDA
    def load_mafaulda_stream(self, chunksize: int = 50000):
    
    # Lit le fichier MAFAULDA et renvoie un générateur 
        path = self.raw_dir / mafaulda / "MAFAULDA.csv"
        if not path.exists():
            raise FileNotFoundError(f"Fichier MAFAULDA introuvable : {path}")
            
        logger.info(f"Ouverture du flux MAFAULDA.csv")
        # MAFAULDA contient généralement 8 colonnes sans entête
        return pd.read_csv(path, chunksize=chunksize, header=None)

if __name__ == "__main__":
    # Bloc de test en mode local
    loader = DatasetLoader(raw_dir="data/raw")
    try:
        df_cwru = loader.load_cwru_file("97.mat")
        print("\n Fichier CWRU converti avec succès au format dynamique ESP32 !")
        print(df_cwru[['motor_id', 'temperature', 'current', 'label', 'rul']].head())
    except Exception as e:
        print(f" Erreur lors du test : {e}")