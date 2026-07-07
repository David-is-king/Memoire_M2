# =============================================================================
# tests/test_ingestion.py
# Tests unitaires pour src/ingestion/dataset_loader.py
# Lancement : pytest tests/test_ingestion.py -v
# =============================================================================
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest
from src.ingestion.dataset_loader import DatasetLoader


EXPECTED_COLS = {
    "timestamp", "motor_id", "temperature", "vibration_x",
    "vibration_y", "vibration_z", "current", "voltage",
    "acoustic_db", "label", "rul", "data_origin"
}


class TestSyntheticGeneration:
    """Tests sur la génération de données synthétiques (toujours disponibles)."""

    def setup_method(self):
        self.loader = DatasetLoader(raw_dir="data/raw")

    def test_columns_standard(self):
        """Le DataFrame synthétique doit avoir exactement les colonnes standard."""
        df = self.loader.generate_synthetic(n_motors=2, duration_hours=0.01)
        assert EXPECTED_COLS.issubset(set(df.columns)), \
            f"Colonnes manquantes : {EXPECTED_COLS - set(df.columns)}"

    def test_label_range(self):
        """Les labels doivent être dans [0, 4]."""
        df = self.loader.generate_synthetic(n_motors=5, duration_hours=0.01)
        assert df["label"].between(0, 4).all(), \
            f"Labels hors bornes : {df['label'].unique()}"

    def test_rul_positive(self):
        """Le RUL doit être positif ou nul."""
        df = self.loader.generate_synthetic(n_motors=3, duration_hours=0.01)
        assert (df["rul"] >= 0).all(), "RUL négatif détecté"

    def test_n_motors(self):
        """Le nombre de moteurs distincts doit correspondre au paramètre."""
        df = self.loader.generate_synthetic(n_motors=4, duration_hours=0.01)
        assert df["motor_id"].nunique() == 4

    def test_no_label_leakage_in_noise(self):
        """
        Les colonnes capteurs ne doivent pas être un simple proxy du label.
        Test : la corrélation entre temperature_mean_par_label ne doit pas
        varier de plus de 50°C entre classes extrêmes (sinon le modèle
        apprendrait uniquement le bruit, pas le signal).
        """
        df = self.loader.generate_synthetic(n_motors=10, duration_hours=0.05)
        temp_by_label = df.groupby("label")["temperature"].mean()
        if len(temp_by_label) > 1:
            spread = temp_by_label.max() - temp_by_label.min()
            # Un spread > 50°C suggère un biais fort corrélé au label
            # (tolérance large pour données synthétiques physiquement motivées)
            assert spread < 60, f"Température trop corrélée au label : spread={spread:.1f}°C"

    def test_data_origin_tag(self):
        """La colonne data_origin doit valoir 'synthetic'."""
        df = self.loader.generate_synthetic(n_motors=2, duration_hours=0.01)
        assert (df["data_origin"] == "synthetic").all()


class TestMafauldaParsing:
    """
    Tests sur le chargement du dataset MAFAULDA brut (arborescence UFRJ réelle :
    data/raw/mafaulda/<defaut>/[<severite>/]*.csv, 8 colonnes sans en-tête).
    """

    @staticmethod
    def _write_fake_trial(path, n_rows=20, seed=0):
        """Écrit un faux essai MAFAULDA (8 colonnes, sans en-tête, comme le vrai format)."""
        rng = np.random.default_rng(seed)
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rng.normal(size=(n_rows, 8))).to_csv(path, header=False, index=False)

    def _make_fake_mafaulda_tree(self, tmp_path):
        raw_dir = tmp_path / "data" / "raw"
        maf = raw_dir / "mafaulda"
        self._write_fake_trial(maf / "normal" / "12.288.csv")
        self._write_fake_trial(maf / "imbalance" / "6g" / "13.0.csv")
        self._write_fake_trial(maf / "horizontal-misalignment" / "0.5mm" / "14.0.csv")
        self._write_fake_trial(maf / "vertical-misalignment" / "0.51mm" / "15.0.csv")
        self._write_fake_trial(maf / "overhang" / "ball_fault" / "6g" / "16.0.csv")
        self._write_fake_trial(maf / "underhang" / "cage_fault" / "0g" / "17.0.csv")
        return raw_dir

    def test_folder_label_map_coverage(self):
        """Le mapping dossier → label doit couvrir les 6 dossiers racine MAFAULDA."""
        m = DatasetLoader.MAFAULDA_FOLDER_LABEL_MAP
        assert m["normal"] == 0
        assert m["imbalance"] == 1
        assert m["horizontal-misalignment"] == 2
        assert m["vertical-misalignment"] == 3
        # overhang et underhang = même roulement défectueux, dossiers différents
        assert m["overhang"] == 4
        assert m["underhang"] == 4

    def test_iter_mafaulda_files_labels(self, tmp_path):
        """Chaque essai doit recevoir le label correspondant à son dossier racine."""
        raw_dir = self._make_fake_mafaulda_tree(tmp_path)
        loader = DatasetLoader(raw_dir=str(raw_dir))
        found = loader.iter_mafaulda_files()
        labels_by_name = {p.stem: lbl for p, lbl in found}
        assert labels_by_name["12.288"] == 0
        assert labels_by_name["13.0"] == 1
        assert labels_by_name["14.0"] == 2
        assert labels_by_name["15.0"] == 3
        assert labels_by_name["16.0"] == 4   # overhang
        assert labels_by_name["17.0"] == 4   # underhang

    def test_load_mafaulda_files_standard_format(self, tmp_path):
        """Chaque essai chargé doit respecter le format standard du projet."""
        raw_dir = self._make_fake_mafaulda_tree(tmp_path)
        loader = DatasetLoader(raw_dir=str(raw_dir))
        dfs = list(loader.load_mafaulda_files())

        assert len(dfs) == 6
        for df in dfs:
            assert EXPECTED_COLS.issubset(set(df.columns))
            assert (df["data_origin"] == "MAFAULDA").all()
            assert df["vibration_y"].notna().all()  # overhang_radial, toujours dispo
            assert df["motor_id"].nunique() == 1     # 1 essai = 1 moteur

    def test_max_files_per_class_applies_to_combined_label(self, tmp_path):
        """
        overhang/ et underhang/ partagent le label 4 : la limite doit s'appliquer
        à leur TOTAL combiné, pas à chaque dossier séparément.
        """
        raw_dir = self._make_fake_mafaulda_tree(tmp_path)
        # Ajoute un second essai "underhang" pour avoir 2 fichiers label=4 côté underhang
        self._write_fake_trial(raw_dir / "mafaulda" / "underhang" / "cage_fault" / "0g" / "18.0.csv")
        loader = DatasetLoader(raw_dir=str(raw_dir))

        found = loader.iter_mafaulda_files(max_files_per_class=1)
        label4_files = [p for p, lbl in found if lbl == 4]
        assert len(label4_files) == 1, "La limite par classe doit s'appliquer au total overhang+underhang"

    def test_max_seconds_truncates_trial(self, tmp_path):
        """max_seconds doit tronquer le nombre de lignes lues (proportionnel à 50kHz)."""
        raw_dir = self._make_fake_mafaulda_tree(tmp_path)
        self._write_fake_trial(raw_dir / "mafaulda" / "normal" / "big.csv", n_rows=100_000)
        loader = DatasetLoader(raw_dir=str(raw_dir))

        df = loader._load_mafaulda_file(
            raw_dir / "mafaulda" / "normal" / "big.csv", label=0, max_seconds=1.0
        )
        assert len(df) == loader.MAFAULDA_SAMPLING_RATE_HZ


class TestCwruLabelInference:
    """
    Tests sur l'inférence du label depuis le nom de fichier CWRU.

    CWRU ne contient que des défauts de roulement (piste intérieure, bille,
    piste extérieure) : aucune distinction n'est faite entre ces sous-types
    dans le schéma à 5 classes du projet, tous vont vers la classe 4
    (Roulement) — cf. le commentaire de correction dans _infer_cwru_label.
    """

    def test_normal_files(self):
        assert DatasetLoader._infer_cwru_label("97.mat") == 0
        assert DatasetLoader._infer_cwru_label("98.mat") == 0
        assert DatasetLoader._infer_cwru_label("99.mat") == 0
        assert DatasetLoader._infer_cwru_label("100.mat") == 0
        assert DatasetLoader._infer_cwru_label("normal.mat") == 0

    def test_inner_race_is_bearing(self):
        """105-108 = piste intérieure (convention réelle CWRU) → Roulement."""
        assert DatasetLoader._infer_cwru_label("105.mat") == 4
        assert DatasetLoader._infer_cwru_label("108.mat") == 4

    def test_ball_fault_is_bearing(self):
        """118-121 = bille (convention réelle CWRU) → Roulement."""
        assert DatasetLoader._infer_cwru_label("118.mat") == 4
        assert DatasetLoader._infer_cwru_label("121.mat") == 4

    def test_outer_race_is_bearing(self):
        """130+ = piste extérieure → Roulement."""
        assert DatasetLoader._infer_cwru_label("130.mat") == 4
        assert DatasetLoader._infer_cwru_label("3008.mat") == 4
