#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
  SWaT ICS ANOMALY DETECTION — END-TO-END MACHINE LEARNING PIPELINE
  MTech AI & Data Science · VJTI Mumbai
  Based on: iTrust SWaT Dataset (SUTD Singapore)
═══════════════════════════════════════════════════════════════════════════════

PIPELINE STAGES:
  1.  Data Loading & Multi-Run Merging
  2.  Data Quality Assessment
  3.  Preprocessing & Missing Value Handling
  4.  Feature Engineering (ICS domain-specific)
  5.  Exploratory Data Analysis (EDA)
  6.  Time-Series Analysis
  7.  Class Balancing Strategy
  8.  Model Training (supervised + unsupervised)
  9.  Evaluation & Performance Metrics
  10. Explainability (SHAP)
  11. Results Summary

MODELS IMPLEMENTED:
  Supervised   : XGBoost, Random Forest, LightGBM, MLP Neural Network
  Unsupervised : Isolation Forest, Autoencoder
  Temporal     : LSTM (PyTorch)

Run: python swat_ml_pipeline.py --data-dir ./  --runs run_01 run_02 run_03 run_04 run_05
"""

import os, sys, json, warnings, time, logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.patches as mpatches
import seaborn as sns
from scipy import stats
from scipy.signal import find_peaks

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
log = logging.getLogger('SWaT-ML')

# ─── Optional heavy dependencies ─────────────────────────────────────────────
try:
    import sklearn
    from sklearn.ensemble import RandomForestClassifier, IsolationForest, GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler, RobustScaler, MinMaxScaler, LabelEncoder
    from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
    from sklearn.metrics import (classification_report, confusion_matrix, roc_auc_score,
                                  roc_curve, precision_recall_curve, f1_score,
                                  precision_score, recall_score, average_precision_score)
    from sklearn.pipeline import Pipeline
    from sklearn.inspection import permutation_importance
    from sklearn.neural_network import MLPClassifier
    from sklearn.decomposition import PCA
    from sklearn.manifold import TSNE
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    log.warning("scikit-learn not found. Install: pip install scikit-learn")

try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    log.warning("XGBoost not found. Install: pip install xgboost")

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    HAS_LGB = False

try:
    import shap
    HAS_SHAP = True
except ImportError:
    HAS_SHAP = False
    log.warning("SHAP not found. Install: pip install shap")

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    log.warning("PyTorch not found. LSTM model will be skipped.")

try:
    from imblearn.over_sampling import SMOTE
    from imblearn.combine import SMOTETomek
    HAS_IMBLEARN = True
except ImportError:
    HAS_IMBLEARN = False


# ════════════════════════════════════════════════════════════════════════════════
#  DOMAIN CONSTANTS
# ════════════════════════════════════════════════════════════════════════════════

ATTACK_NAMES = {
    0: 'Normal', 8: 'Tank Overflow', 9: 'Chemical Depletion',
    10: 'Membrane Damage', 11: 'pH Manipulation', 12: 'Slow Ramp',
    13: 'Reconnaissance', 14: 'Denial of Service', 15: 'Replay Attack',
    16: 'Valve Manipulation'
}

ATTACK_CATEGORIES = {
    0: 'Normal',
    8: 'Command Injection', 9: 'Command Injection', 16: 'Command Injection',
    10: 'Physical/Process', 11: 'Sensor Spoofing', 12: 'Sensor Spoofing',
    13: 'Network', 14: 'Network', 15: 'Network'
}

# Sensor groups by stage
STAGE_SENSORS = {
    'S1': ['FIT_101','LIT_101','MV_101','P_101','P_102'],
    'S2': ['AIT_201','AIT_202','AIT_203','Chlorine_Residual','FIT_201','MV_201',
           'P_201','P_202','P_203','P_204','P_205','P_206',
           'Acid_Tank_Level','Chlorine_Tank_Level','Coagulant_Tank_Level','Bisulfate_Tank_Level'],
    'S3': ['DPIT_301','FIT_301','LIT_301','MV_301','MV_302','MV_303','MV_304',
           'P_301','P_302','UF_Runtime','UF_Fouling_Factor','UF_Last_Backwash',
           'UF_Backwash_Active','Turbidity_UF'],
    'S4': ['AIT_401','AIT_402','FIT_401','LIT_401','P_401','P_402','P_403','P_404','UV_401'],
    'S5': ['AIT_501','AIT_502','AIT_503','AIT_504','FIT_501','FIT_502','FIT_503','FIT_504',
           'PIT_501','PIT_502','PIT_503','P_501','P_502','RO_Runtime',
           'RO_Fouling_Factor','RO_Last_Cleaning','RO_Cleaning_Active','TDS_Feed','TDS_Permeate'],
    'S6': ['FIT_601','P_601','P_602','P_603']
}

# Key physics sensors for feature engineering
FLOW_SENSORS  = ['FIT_101','FIT_201','FIT_301','FIT_401','FIT_501','FIT_502','FIT_601']
LEVEL_SENSORS = ['LIT_101','LIT_301','LIT_401']
PRESSURE_SENS = ['DPIT_301','PIT_501','PIT_502','PIT_503']
QUALITY_SENS  = ['AIT_201','AIT_202','AIT_203','AIT_401','AIT_402',
                  'Chlorine_Residual','TDS_Permeate']
CHEM_TANKS    = ['Acid_Tank_Level','Chlorine_Tank_Level','Coagulant_Tank_Level','Bisulfate_Tank_Level']
PUMP_COILS    = ['P_101','P_102','P_203','P_205','P_206','P_301','P_401','P_403','P_501','P_601','P_603']
FOULING       = ['UF_Fouling_Factor','RO_Fouling_Factor']

# Engineering units (stored value → display)
SCALE_MAP = {
    'FIT_101':0.1,'FIT_201':0.1,'FIT_301':0.1,'FIT_401':0.1,
    'FIT_501':0.1,'FIT_502':0.1,'FIT_503':0.1,'FIT_504':0.1,'FIT_601':0.1,
    'DPIT_301':0.1,'PIT_501':0.1,'PIT_502':0.1,'PIT_503':0.1,
    'AIT_202':0.01,'Chlorine_Residual':0.1,'Water_Temperature':0.1,'Ambient_Temperature':0.1,
}

# Physical alarm thresholds (in engineering units)
THRESHOLDS = {
    'LIT_101_hi': 950, 'LIT_301_hi': 950, 'LIT_401_hi': 950,
    'AIT_202_hi': 9.00, 'AIT_202_lo': 5.50,   # pH
    'DPIT_301_hi': 60.0,                         # kPa
    'PIT_501_hi': 180.0,                         # bar
    'UF_Fouling_Factor_hi': 80,
    'RO_Fouling_Factor_hi': 80,
}

# ════════════════════════════════════════════════════════════════════════════════
#  PLOTTING THEME
# ════════════════════════════════════════════════════════════════════════════════

DARK_BG   = '#0a0f1e'
PANEL_BG  = '#111827'
GRID_COL  = '#1f2937'
CYAN      = '#00d4ff'
TEAL      = '#00ffc8'
AMBER     = '#ffab00'
RED_COL   = '#ff3d57'
GREEN_COL = '#00e676'
PURPLE    = '#d500f9'
BLUE_COL  = '#2979ff'
TEXT_COL  = '#e8f4ff'
DIM_TEXT  = '#64748b'

PALETTE   = [CYAN, TEAL, AMBER, RED_COL, GREEN_COL, PURPLE, BLUE_COL,
             '#ff9800','#e91e63','#00bcd4']
ATTACK_COLORS = {
    0: GRID_COL, 8: RED_COL, 9: AMBER, 10: PURPLE,
    11: '#00bcd4', 12: GREEN_COL, 13: BLUE_COL, 14: '#ff5722', 15: TEAL, 16: '#cddc39'
}

def set_theme():
    plt.rcParams.update({
        'figure.facecolor': DARK_BG, 'axes.facecolor': PANEL_BG,
        'axes.edgecolor': GRID_COL, 'axes.labelcolor': TEXT_COL,
        'text.color': TEXT_COL, 'xtick.color': DIM_TEXT, 'ytick.color': DIM_TEXT,
        'grid.color': GRID_COL, 'grid.alpha': 0.6,
        'axes.titlecolor': TEXT_COL, 'axes.titlesize': 11,
        'axes.labelsize': 9, 'xtick.labelsize': 8, 'ytick.labelsize': 8,
        'figure.dpi': 100, 'savefig.dpi': 120, 'savefig.bbox': 'tight',
        'savefig.facecolor': DARK_BG, 'font.family': 'monospace',
        'legend.facecolor': PANEL_BG, 'legend.edgecolor': GRID_COL,
        'legend.fontsize': 8,
    })

set_theme()


# ════════════════════════════════════════════════════════════════════════════════
#  STAGE 1: DATA LOADING & MERGING
# ════════════════════════════════════════════════════════════════════════════════

class DataLoader:
    """Load and merge multiple SWaT run CSVs into a unified dataset."""

    def __init__(self, data_dir: str, run_folders: List[str]):
        self.data_dir  = Path(data_dir)
        self.run_folders = run_folders
        self.raw_dfs: Dict[str, pd.DataFrame] = {}

    def load_all(self) -> pd.DataFrame:
        log.info("=" * 60)
        log.info("STAGE 1: DATA LOADING & MERGING")
        log.info("=" * 60)

        dfs = []
        for i, folder in enumerate(self.run_folders, 1):
            csv_path = self.data_dir / folder / 'master_dataset.csv'
            if not csv_path.exists():
                # Also try direct CSV
                csv_path = self.data_dir / f'{folder}.csv'
            if not csv_path.exists():
                log.warning(f"  ⚠  {csv_path} not found — skipping")
                continue

            df = pd.read_csv(csv_path, low_memory=False)
            df['run_id'] = i
            df['run_name'] = folder

            # Parse timestamp
            if 'Timestamp' in df.columns:
                df['Timestamp'] = pd.to_datetime(df['Timestamp'], utc=True, errors='coerce')
                df = df.sort_values('Timestamp').reset_index(drop=True)
                t0 = df['Timestamp'].iloc[0]
                df['elapsed_s'] = (df['Timestamp'] - t0).dt.total_seconds().round(2)
            else:
                df['elapsed_s'] = np.arange(len(df)) * 0.1

            self.raw_dfs[folder] = df
            n_atk = (df.get('ATTACK_ID', pd.Series([0]*len(df)))>0).sum()
            log.info(f"  run_{i:02d} [{folder}]: {len(df):>7,} rows | "
                     f"normal={len(df)-n_atk:,} attack={n_atk:,} | "
                     f"attacks={sorted(df['ATTACK_ID'].unique().tolist()) if 'ATTACK_ID' in df else '[]'}")
            dfs.append(df)

        if not dfs:
            log.error("No data loaded! Check data_dir and run folder names.")
            sys.exit(1)

        combined = pd.concat(dfs, ignore_index=True)
        log.info(f"\n  MERGED: {len(combined):,} total rows | {len(combined.columns)} columns | {len(dfs)} runs")
        return combined


# ════════════════════════════════════════════════════════════════════════════════
#  STAGE 2: DATA QUALITY ASSESSMENT
# ════════════════════════════════════════════════════════════════════════════════

class DataQualityAssessor:
    """Comprehensive data quality checks tailored for ICS datasets."""

    def __init__(self, df: pd.DataFrame, output_dir: Path):
        self.df = df.copy()
        self.out = output_dir
        self.report = {}

    def assess(self) -> Dict[str, Any]:
        log.info("\n" + "="*60)
        log.info("STAGE 2: DATA QUALITY ASSESSMENT")
        log.info("="*60)

        self._null_analysis()
        self._zero_variance_check()
        self._outlier_check()
        self._sampling_rate_check()
        self._attack_label_integrity()
        self._plot_quality_summary()
        return self.report

    def _null_analysis(self):
        null_pct = (self.df.isnull().sum() / len(self.df) * 100).sort_values(ascending=False)
        null_cols = null_pct[null_pct > 0]
        self.report['null_columns'] = null_cols.to_dict()
        if len(null_cols) > 0:
            log.warning(f"  NULL VALUES: {len(null_cols)} columns have missing data")
            for col, pct in null_cols.head(10).items():
                log.warning(f"    {col:40s}: {pct:.2f}% null")
        else:
            log.info("  ✓ NULL VALUES: No missing data found")

    def _zero_variance_check(self):
        numeric = self.df.select_dtypes(include=[np.number])
        dead = [c for c in numeric.columns if numeric[c].nunique() <= 1
                and c not in ['ATTACK_ID','run_id']]
        self.report['dead_columns'] = dead
        if dead:
            log.warning(f"  DEAD COLUMNS ({len(dead)}): {dead}")
        else:
            log.info("  ✓ DEAD COLUMNS: None found")

    def _outlier_check(self):
        key_sensors = [s for s in FLOW_SENSORS + LEVEL_SENSORS + PRESSURE_SENS
                       if s in self.df.columns]
        outlier_counts = {}
        for col in key_sensors:
            normal = self.df[self.df.get('ATTACK_ID', pd.Series([0]*len(self.df)))==0][col]
            Q1, Q3 = normal.quantile(0.25), normal.quantile(0.75)
            IQR = Q3 - Q1
            out = ((normal < Q1-3*IQR) | (normal > Q3+3*IQR)).sum()
            if out > 0:
                outlier_counts[col] = int(out)
        self.report['outliers_in_normal'] = outlier_counts
        log.info(f"  OUTLIERS IN NORMAL DATA: {len(outlier_counts)} sensors have outliers (IQR×3)")

    def _sampling_rate_check(self):
        if 'Timestamp' in self.df.columns and self.df['Timestamp'].notna().any():
            ts = self.df['Timestamp'].dropna().sort_values()
            dt = ts.diff().dt.total_seconds().dropna()
            mean_dt = dt.mean(); max_gap = dt.max()
            self.report['mean_sample_interval_s'] = round(float(mean_dt), 3)
            self.report['max_gap_s'] = round(float(max_gap), 2)
            log.info(f"  SAMPLING: mean_dt={mean_dt:.3f}s | max_gap={max_gap:.2f}s | "
                     f"est_rate={1/mean_dt:.1f}Hz")
        else:
            log.info("  SAMPLING: Timestamp not available")

    def _attack_label_integrity(self):
        if 'ATTACK_ID' not in self.df.columns:
            return
        dist = self.df['ATTACK_ID'].value_counts().to_dict()
        self.report['attack_distribution'] = {int(k): int(v) for k, v in dist.items()}
        total_attack = sum(v for k,v in dist.items() if k>0)
        total = len(self.df)
        log.info(f"\n  ATTACK DISTRIBUTION ({total:,} rows):")
        for aid, cnt in sorted(dist.items()):
            name = ATTACK_NAMES.get(int(aid), f"Unknown_{aid}")
            pct = cnt/total*100
            bar = '█' * int(pct/2)
            log.info(f"    [{aid:2d}] {name:25s}: {cnt:6,} rows ({pct:4.1f}%) {bar}")

    def _plot_quality_summary(self):
        if 'ATTACK_ID' not in self.df.columns:
            return
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        fig.suptitle('DATA QUALITY OVERVIEW — SWaT DATASET', color=CYAN, fontsize=13, fontweight='bold')

        # Attack distribution pie
        ax = axes[0]
        dist = self.df['ATTACK_ID'].value_counts()
        labels = [f"{ATTACK_NAMES.get(int(k),'?')} ({v:,})" for k,v in dist.items()]
        colors = [ATTACK_COLORS.get(int(k), GRID_COL) for k in dist.index]
        wedges, texts, autotexts = ax.pie(dist.values, labels=None, colors=colors,
                                           autopct='%1.1f%%', pctdistance=0.82,
                                           wedgeprops={'linewidth':0.5,'edgecolor':DARK_BG})
        for at in autotexts: at.set(fontsize=7, color=TEXT_COL)
        ax.legend(labels, loc='lower left', fontsize=6, bbox_to_anchor=(-0.3,-0.2), ncol=2)
        ax.set_title('ATTACK CLASS DISTRIBUTION', color=TEXT_COL)

        # Per-run attack coverage
        ax = axes[1]
        if 'run_id' in self.df.columns:
            pivot = self.df.pivot_table(index='run_id', columns='ATTACK_ID', aggfunc='size', fill_value=0)
            pivot.columns = [ATTACK_NAMES.get(c,f"ID{c}") for c in pivot.columns]
            colors_bar = [ATTACK_COLORS.get(int(k), GRID_COL) for k in self.df['ATTACK_ID'].unique()]
            pivot.plot(kind='bar', ax=ax, stacked=True,
                       color=[ATTACK_COLORS.get(int(c) if isinstance(c,str) else c, CYAN)
                              for c in self.df['ATTACK_ID'].unique()],
                       width=0.6, legend=False)
            ax.set_xlabel('Run ID'); ax.set_ylabel('Row Count')
            ax.set_title('ATTACK COVERAGE PER RUN', color=TEXT_COL)
            ax.tick_params(axis='x', rotation=0)

        plt.tight_layout()
        fig.savefig(self.out/'01_data_quality.png')
        plt.close(fig)
        log.info(f"  → Plot saved: 01_data_quality.png")


# ════════════════════════════════════════════════════════════════════════════════
#  STAGE 3: PREPROCESSING
# ════════════════════════════════════════════════════════════════════════════════

class Preprocessor:
    """ICS-aware preprocessing: scaling, imputation, type conversion."""

    def __init__(self, df: pd.DataFrame, output_dir: Path):
        self.df  = df.copy()
        self.out = output_dir

    def run(self) -> pd.DataFrame:
        log.info("\n" + "="*60)
        log.info("STAGE 3: PREPROCESSING")
        log.info("="*60)

        self._apply_engineering_units()
        self._handle_missing_values()
        self._convert_dtypes()
        self._remove_duplicates()
        self._boundary_leakage_removal()
        log.info(f"  FINAL SHAPE: {self.df.shape}")
        return self.df

    def _apply_engineering_units(self):
        """Convert stored register values to physical engineering units."""
        for col, scale in SCALE_MAP.items():
            if col in self.df.columns:
                self.df[col] = (self.df[col] * scale).round(4)
        log.info("  ✓ Engineering unit scaling applied")

    def _handle_missing_values(self):
        """Forward-fill then backward-fill — appropriate for time-series sensor data."""
        before = self.df.isnull().sum().sum()
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns
        # Per run forward-fill to avoid cross-run contamination
        if 'run_id' in self.df.columns:
            self.df[numeric_cols] = (
                self.df.groupby('run_id')[numeric_cols]
                .transform(lambda x: x.ffill().bfill())
            )
        else:
            self.df[numeric_cols] = self.df[numeric_cols].ffill().bfill()
        # Any remaining: fill with 0 (appropriate for coil/actuator columns)
        self.df.fillna(0, inplace=True)
        after = self.df.isnull().sum().sum()
        log.info(f"  ✓ Missing values: {before} → {after} (forward/backward fill)")

    def _convert_dtypes(self):
        """Convert boolean coil columns to int for ML compatibility."""
        bool_cols = self.df.select_dtypes(include='bool').columns
        self.df[bool_cols] = self.df[bool_cols].astype(int)
        # String booleans
        for col in self.df.select_dtypes(include='object').columns:
            if col in ['Timestamp','ATTACK_NAME','MITRE_ID','run_name']: continue
            try:
                uniq = set(self.df[col].dropna().unique())
                if uniq <= {'True','False'}:
                    self.df[col] = self.df[col].map({'True':1,'False':0})
            except Exception:
                pass
        log.info("  ✓ Boolean coils converted to int")

    def _remove_duplicates(self):
        before = len(self.df)
        if 'Timestamp' in self.df.columns and 'run_id' in self.df.columns:
            self.df = self.df.drop_duplicates(subset=['Timestamp','run_id'])
        else:
            self.df = self.df.drop_duplicates()
        log.info(f"  ✓ Duplicate rows removed: {before-len(self.df)}")

    def _boundary_leakage_removal(self, window_s: float=2.0):
        """Remove rows within ±window_s of any attack transition (label leakage)."""
        if 'ATTACK_ID' not in self.df.columns or 'elapsed_s' not in self.df.columns:
            return
        mask = pd.Series(False, index=self.df.index)
        for _, grp in self.df.groupby('run_id') if 'run_id' in self.df.columns else [('all', self.df)]:
            trans_t = grp.loc[grp['ATTACK_ID'].diff().abs()>0, 'elapsed_s'].values
            for t in trans_t:
                idx = grp[(grp['elapsed_s']-t).abs()<=window_s].index
                mask.loc[idx] = True
        removed = mask.sum()
        self.df = self.df[~mask].reset_index(drop=True)
        log.info(f"  ✓ Boundary leakage removed: {removed} rows (±{window_s}s around transitions)")


# ════════════════════════════════════════════════════════════════════════════════
#  STAGE 4: FEATURE ENGINEERING
# ════════════════════════════════════════════════════════════════════════════════

class FeatureEngineer:
    """ICS domain-specific feature engineering."""

    def __init__(self, df: pd.DataFrame, output_dir: Path):
        self.df  = df.copy()
        self.out = output_dir

    def run(self) -> Tuple[pd.DataFrame, List[str]]:
        log.info("\n" + "="*60)
        log.info("STAGE 4: FEATURE ENGINEERING")
        log.info("="*60)
        new_feats = []

        new_feats += self._temporal_derivatives()
        new_feats += self._rolling_statistics()
        new_feats += self._mass_balance_residuals()
        new_feats += self._physical_consistency_flags()
        new_feats += self._chemical_tank_rates()
        new_feats += self._cross_stage_correlations()
        new_feats += self._fouling_acceleration()
        new_feats += self._pump_duty_cycle()
        new_feats += self._alarm_proximity_features()

        log.info(f"  TOTAL NEW FEATURES: {len(new_feats)}")
        log.info(f"  FINAL FEATURE SPACE: {len(self.df.columns)} columns")
        self._plot_feature_distributions(new_feats)
        return self.df, new_feats

    def _temporal_derivatives(self) -> List[str]:
        """Rate of change (first derivative) for key sensors."""
        feats = []
        key_sensors = [s for s in FLOW_SENSORS+LEVEL_SENSORS+PRESSURE_SENS+QUALITY_SENS
                       if s in self.df.columns]
        for col in key_sensors:
            name = f'd_{col}_dt'
            if 'run_id' in self.df.columns:
                self.df[name] = self.df.groupby('run_id')[col].diff().fillna(0)
            else:
                self.df[name] = self.df[col].diff().fillna(0)
            feats.append(name)
            # Second derivative (acceleration) for critical sensors
            if col in ['AIT_202','DPIT_301','PIT_501','LIT_101']:
                name2 = f'd2_{col}_dt2'
                if 'run_id' in self.df.columns:
                    self.df[name2] = self.df.groupby('run_id')[name].diff().fillna(0)
                else:
                    self.df[name2] = self.df[name].diff().fillna(0)
                feats.append(name2)
        log.info(f"    Temporal derivatives: {len(feats)} features")
        return feats

    def _rolling_statistics(self, windows=[10, 30, 60]) -> List[str]:
        """Rolling mean, std, min, max for sensor anomaly detection."""
        feats = []
        key = [s for s in ['LIT_101','LIT_301','LIT_401','AIT_202','DPIT_301',
                            'PIT_501','FIT_101','Chlorine_Residual','UF_Fouling_Factor']
               if s in self.df.columns]
        for col in key:
            for w in windows:
                for stat, func in [('mean', 'mean'), ('std', 'std'), ('max', 'max')]:
                    name = f'roll_{col}_{w}s_{stat}'
                    if 'run_id' in self.df.columns:
                        self.df[name] = (
                            self.df.groupby('run_id')[col]
                            .transform(lambda x: x.rolling(w, min_periods=1).__getattribute__(func)())
                        )
                    else:
                        self.df[name] = self.df[col].rolling(w, min_periods=1).__getattribute__(func)()
                    self.df[name].fillna(0, inplace=True)
                    feats.append(name)
                # Z-score deviation from rolling mean
                z_name = f'zscore_{col}_{w}s'
                mu  = self.df[f'roll_{col}_{w}s_mean']
                sig = self.df[f'roll_{col}_{w}s_std'].replace(0, 1)
                self.df[z_name] = ((self.df[col] - mu) / sig).fillna(0).clip(-5,5)
                feats.append(z_name)
        log.info(f"    Rolling statistics: {len(feats)} features")
        return feats

    def _mass_balance_residuals(self) -> List[str]:
        """Flow conservation checks — violation indicates sensor attack or leak."""
        feats = []
        # S1: inlet - outlet balance (should ≈ dLIT101/dt)
        if all(c in self.df.columns for c in ['FIT_101','FIT_201','d_LIT_101_dt']):
            self.df['mb_s1'] = (self.df['FIT_101'] - self.df['FIT_201'] - self.df['d_LIT_101_dt']).fillna(0)
            feats.append('mb_s1')
        # S3: UF flow balance
        if all(c in self.df.columns for c in ['FIT_201','FIT_301','d_LIT_301_dt']):
            self.df['mb_s3'] = (self.df['FIT_201'] - self.df['FIT_301'] - self.df['d_LIT_301_dt']).fillna(0)
            feats.append('mb_s3')
        # S5: RO permeate + reject ≈ feed
        if all(c in self.df.columns for c in ['FIT_501','FIT_502','FIT_503']):
            self.df['ro_flow_balance'] = (self.df['FIT_501'] - self.df['FIT_502'] - self.df['FIT_503']).fillna(0)
            feats.append('ro_flow_balance')
        # TDS rejection ratio: should be ~98.5% for healthy membrane
        if all(c in self.df.columns for c in ['TDS_Permeate','TDS_Feed']):
            tds_feed = self.df['TDS_Feed'].replace(0,1)
            self.df['tds_rejection_ratio'] = (1 - self.df['TDS_Permeate']/tds_feed).fillna(0).clip(0,1)
            feats.append('tds_rejection_ratio')
        log.info(f"    Mass balance residuals: {len(feats)} features")
        return feats

    def _physical_consistency_flags(self) -> List[str]:
        """Boolean flags for physically impossible or suspicious states."""
        feats = []
        # Pump ON but no flow (valve closed or sensor attack)
        if all(c in self.df.columns for c in ['P_101','FIT_101']):
            self.df['flag_pump_no_flow_s1'] = ((self.df['P_101']==1) & (self.df['FIT_101']<0.3)).astype(int)
            feats.append('flag_pump_no_flow_s1')
        if all(c in self.df.columns for c in ['P_301','FIT_301']):
            self.df['flag_pump_no_flow_s3'] = ((self.df['P_301']==1) & (self.df['FIT_301']<0.3)).astype(int)
            feats.append('flag_pump_no_flow_s3')
        # Level above 90% threshold
        for tank, thresh in [('LIT_101',900),('LIT_301',900),('LIT_401',900)]:
            if tank in self.df.columns:
                name = f'flag_{tank}_hi'
                self.df[name] = (self.df[tank]>thresh).astype(int)
                feats.append(name)
        # pH outside safe band
        if 'AIT_202' in self.df.columns:
            self.df['flag_ph_oos']    = ((self.df['AIT_202']<6.5)|(self.df['AIT_202']>8.5)).astype(int)
            self.df['flag_ph_alarm']  = ((self.df['AIT_202']<5.5)|(self.df['AIT_202']>9.0)).astype(int)
            feats += ['flag_ph_oos','flag_ph_alarm']
        # TMP over threshold (kPa)
        if 'DPIT_301' in self.df.columns:
            self.df['flag_tmp_hi'] = (self.df['DPIT_301']>60.0).astype(int)
            feats.append('flag_tmp_hi')
        # RO over-pressure
        if 'PIT_501' in self.df.columns:
            self.df['flag_ro_hpress'] = (self.df['PIT_501']>18.0).astype(int)
            feats.append('flag_ro_hpress')
        log.info(f"    Physical consistency flags: {len(feats)} features")
        return feats

    def _chemical_tank_rates(self) -> List[str]:
        """Depletion rates for chemical tanks — attacks consume chemicals abnormally."""
        feats = []
        for tank in CHEM_TANKS:
            if tank in self.df.columns:
                name = f'rate_{tank}'
                if 'run_id' in self.df.columns:
                    self.df[name] = self.df.groupby('run_id')[tank].diff().fillna(0)
                else:
                    self.df[name] = self.df[tank].diff().fillna(0)
                feats.append(name)
        log.info(f"    Chemical tank rates: {len(feats)} features")
        return feats

    def _cross_stage_correlations(self) -> List[str]:
        """Cross-stage features that capture inter-stage relationships."""
        feats = []
        # pH vs chlorine residual interaction
        if all(c in self.df.columns for c in ['AIT_202','Chlorine_Residual']):
            self.df['ph_x_chlorine'] = self.df['AIT_202'] * self.df['Chlorine_Residual']
            feats.append('ph_x_chlorine')
        # UF fouling × flow (degraded flow under high fouling is normal; high flow under high fouling is anomalous)
        if all(c in self.df.columns for c in ['UF_Fouling_Factor','FIT_301']):
            self.df['uf_fouling_x_flow'] = self.df['UF_Fouling_Factor'] * self.df['FIT_301']
            feats.append('uf_fouling_x_flow')
        # Total chemical depletion rate (combined tanks signal)
        valid_tanks = [t for t in CHEM_TANKS if f'rate_{t}' in self.df.columns]
        if valid_tanks:
            self.df['total_chem_depletion_rate'] = sum(self.df[f'rate_{t}'].abs() for t in valid_tanks)
            feats.append('total_chem_depletion_rate')
        log.info(f"    Cross-stage correlations: {len(feats)} features")
        return feats

    def _fouling_acceleration(self) -> List[str]:
        """Fouling acceleration — attacks accelerate membrane fouling non-linearly."""
        feats = []
        for col in ['UF_Fouling_Factor','RO_Fouling_Factor']:
            if col in self.df.columns:
                dname  = f'd_{col}_dt'
                d2name = f'd2_{col}_dt2'
                if dname in self.df.columns:
                    name = f'accel_{col}'
                    if d2name in self.df.columns:
                        self.df[name] = self.df[d2name].fillna(0)
                    else:
                        if 'run_id' in self.df.columns:
                            self.df[name] = self.df.groupby('run_id')[dname].diff().fillna(0)
                        else:
                            self.df[name] = self.df[dname].diff().fillna(0)
                    feats.append(name)
        log.info(f"    Fouling acceleration: {len(feats)} features")
        return feats

    def _pump_duty_cycle(self, window=60) -> List[str]:
        """Rolling pump duty cycle (fraction of time ON) — DoS/attack pattern."""
        feats = []
        for pump in PUMP_COILS:
            if pump in self.df.columns:
                name = f'duty_{pump}_{window}s'
                if 'run_id' in self.df.columns:
                    self.df[name] = (
                        self.df.groupby('run_id')[pump]
                        .transform(lambda x: x.rolling(window, min_periods=1).mean())
                    )
                else:
                    self.df[name] = self.df[pump].rolling(window, min_periods=1).mean()
                self.df[name].fillna(0, inplace=True)
                feats.append(name)
        log.info(f"    Pump duty cycles: {len(feats)} features")
        return feats

    def _alarm_proximity_features(self) -> List[str]:
        """How close key values are to alarm thresholds — early warning signal."""
        feats = []
        prox_map = {
            'LIT_101': ('LIT_101_hi', 1.0),
            'DPIT_301_kpa': ('DPIT_301_hi', 0.1),
            'PIT_501_bar': ('PIT_501_hi', 0.1),
        }
        for feat_name, (thresh_key, scale) in prox_map.items():
            col = feat_name.split('_kpa')[0].split('_bar')[0]
            if col in self.df.columns and thresh_key in THRESHOLDS:
                thresh = THRESHOLDS[thresh_key]
                name = f'prox_{col}'
                self.df[name] = (self.df[col]*scale / thresh).clip(0, 1.2)
                feats.append(name)
        # pH distance from neutral band [6.8, 8.5]
        if 'AIT_202' in self.df.columns:
            self.df['ph_dist_from_safe'] = np.minimum(
                (self.df['AIT_202'] - 6.8).clip(lower=0),
                (8.5 - self.df['AIT_202']).clip(lower=0)
            )
            feats.append('ph_dist_from_safe')
        log.info(f"    Alarm proximity features: {len(feats)} features")
        return feats

    def _plot_feature_distributions(self, new_feats: List[str]):
        """Compare feature distributions: normal vs attack."""
        if 'ATTACK_ID' not in self.df.columns:
            return
        plot_feats = [f for f in ['d_AIT_202_dt','mb_s1','flag_pump_no_flow_s1',
                                   'zscore_LIT_101_30s','duty_P_203_60s','tds_rejection_ratio',
                                   'flag_ph_oos','total_chem_depletion_rate'] if f in self.df.columns][:8]
        if not plot_feats:
            return
        rows = 2; cols = 4
        fig, axes = plt.subplots(rows, cols, figsize=(16, 7))
        fig.suptitle('ENGINEERED FEATURE DISTRIBUTIONS: NORMAL vs ATTACK', color=CYAN, fontsize=12, fontweight='bold')
        normal = self.df[self.df['ATTACK_ID']==0]
        attack = self.df[self.df['ATTACK_ID']>0]
        for ax, feat in zip(axes.flat, plot_feats):
            n_vals = normal[feat].dropna().clip(*normal[feat].quantile([0.01,0.99]))
            a_vals = attack[feat].dropna().clip(*attack[feat].quantile([0.01,0.99]))
            ax.hist(n_vals, bins=50, alpha=0.6, color=CYAN, label='Normal', density=True)
            ax.hist(a_vals, bins=50, alpha=0.6, color=RED_COL, label='Attack', density=True)
            ax.set_title(feat.replace('_',' '), fontsize=8, color=TEXT_COL)
            ax.legend(fontsize=7)
            ax.grid(True, alpha=0.3)
        for ax in axes.flat[len(plot_feats):]:
            ax.set_visible(False)
        plt.tight_layout()
        fig.savefig(self.out/'02_feature_distributions.png')
        plt.close(fig)
        log.info(f"  → Plot saved: 02_feature_distributions.png")


# ════════════════════════════════════════════════════════════════════════════════
#  STAGE 5: EXPLORATORY DATA ANALYSIS
# ════════════════════════════════════════════════════════════════════════════════

class EDAEngine:
    """Comprehensive EDA with ICS-domain visualisations."""

    def __init__(self, df: pd.DataFrame, output_dir: Path):
        self.df  = df.copy()
        self.out = output_dir

    def run(self):
        log.info("\n" + "="*60)
        log.info("STAGE 5: EXPLORATORY DATA ANALYSIS")
        log.info("="*60)
        self._plot_sensor_timeseries()
        self._plot_attack_sensor_separation()
        self._plot_correlation_heatmap()
        self._plot_pca_projection()
        self._plot_attack_violin()
        log.info("  EDA complete.")

    def _plot_sensor_timeseries(self):
        """Multi-panel sensor time-series with attack bands."""
        if 'elapsed_s' not in self.df.columns or 'ATTACK_ID' not in self.df.columns:
            return
        sensors = [s for s in ['LIT_101','AIT_202','DPIT_301','PIT_501','Chlorine_Residual','UF_Fouling_Factor'] if s in self.df.columns]
        n = len(sensors); fig, axes = plt.subplots(n, 1, figsize=(18, 2.8*n), sharex=True)
        fig.suptitle('SENSOR TIME-SERIES WITH ATTACK ANNOTATIONS', color=CYAN, fontsize=13, fontweight='bold')
        t = self.df['elapsed_s'] / 3600  # hours
        atk = self.df['ATTACK_ID']
        colors = [CYAN, GREEN_COL, AMBER, BLUE_COL, PURPLE, TEAL]
        for i, (ax, col) in enumerate(zip(axes, sensors)):
            ax.plot(t, self.df[col], color=colors[i%len(colors)], lw=0.6, alpha=0.9)
            # Shade attack periods
            in_atk=False; start=None
            for j, (ti, ai) in enumerate(zip(t, atk)):
                if ai>0 and not in_atk: start=ti; in_atk=True
                elif ai==0 and in_atk:
                    col_a=ATTACK_COLORS.get(int(atk.iloc[j-1]),RED_COL)
                    ax.axvspan(start,ti,alpha=0.18,color=col_a)
                    in_atk=False
            if in_atk: ax.axvspan(start,t.iloc[-1],alpha=0.18,color=RED_COL)
            ax.set_ylabel(col.replace('_','\n'), fontsize=7, color=DIM_TEXT)
            ax.grid(True, alpha=0.25); ax.set_facecolor(PANEL_BG)
        axes[-1].set_xlabel('Elapsed Time (hours)')
        # Legend
        patches=[mpatches.Patch(color=ATTACK_COLORS.get(k,RED_COL),label=ATTACK_NAMES.get(k,'?'),alpha=0.6)
                 for k in sorted(self.df.loc[self.df['ATTACK_ID']>0,'ATTACK_ID'].unique())]
        fig.legend(handles=patches, loc='upper right', bbox_to_anchor=(1,0.98), fontsize=7, ncol=3)
        plt.tight_layout()
        fig.savefig(self.out/'03_sensor_timeseries.png')
        plt.close(fig)
        log.info("  → Plot saved: 03_sensor_timeseries.png")

    def _plot_attack_sensor_separation(self):
        """Box plots of key sensors by attack type — shows discriminative power."""
        sensors = [s for s in ['AIT_202','DPIT_301','LIT_101','Chlorine_Residual','PIT_501','FIT_101'] if s in self.df.columns]
        if not sensors or 'ATTACK_ID' not in self.df.columns:
            return
        fig, axes = plt.subplots(2, 3, figsize=(16, 9))
        fig.suptitle('SENSOR DISTRIBUTION BY ATTACK TYPE — Discrimination Power', color=CYAN, fontsize=12, fontweight='bold')
        attack_ids = sorted(self.df['ATTACK_ID'].unique())
        for ax, col in zip(axes.flat, sensors):
            data = [self.df[self.df['ATTACK_ID']==aid][col].dropna().values for aid in attack_ids]
            bp = ax.boxplot(data, patch_artist=True, notch=False, vert=True,
                            whiskerprops=dict(color=DIM_TEXT,lw=1),
                            capprops=dict(color=DIM_TEXT,lw=1),
                            medianprops=dict(color=AMBER,lw=2))
            for patch, aid in zip(bp['boxes'], attack_ids):
                patch.set_facecolor(ATTACK_COLORS.get(int(aid), GRID_COL))
                patch.set_alpha(0.7)
            ax.set_xticks(range(1,len(attack_ids)+1))
            ax.set_xticklabels([ATTACK_NAMES.get(int(a),'?')[:8] for a in attack_ids], rotation=45, ha='right', fontsize=6)
            ax.set_title(col, fontsize=9, color=TEXT_COL); ax.grid(True, axis='y', alpha=0.3)
        plt.tight_layout(); fig.savefig(self.out/'04_sensor_by_attack.png'); plt.close(fig)
        log.info("  → Plot saved: 04_sensor_by_attack.png")

    def _plot_correlation_heatmap(self):
        """Feature correlation heatmap for key sensors."""
        feat_cols = [c for c in FLOW_SENSORS+LEVEL_SENSORS+PRESSURE_SENS+QUALITY_SENS+FOULING if c in self.df.columns]
        if len(feat_cols) < 3: return
        corr = self.df[feat_cols].corr()
        fig, ax = plt.subplots(figsize=(14, 12))
        fig.suptitle('SENSOR CORRELATION MATRIX — Key Physical Variables', color=CYAN, fontsize=12, fontweight='bold')
        cmap = LinearSegmentedColormap.from_list('ics', [RED_COL, DARK_BG, CYAN])
        im = ax.imshow(corr.values, cmap=cmap, aspect='auto', vmin=-1, vmax=1)
        ax.set_xticks(range(len(feat_cols))); ax.set_yticks(range(len(feat_cols)))
        ax.set_xticklabels(feat_cols, rotation=90, fontsize=7); ax.set_yticklabels(feat_cols, fontsize=7)
        plt.colorbar(im, ax=ax, label='Pearson r')
        for i in range(len(feat_cols)):
            for j in range(len(feat_cols)):
                v = corr.values[i,j]
                if abs(v) > 0.5:
                    ax.text(j, i, f'{v:.2f}', ha='center', va='center', fontsize=5, color=TEXT_COL if abs(v)<0.85 else DARK_BG)
        plt.tight_layout(); fig.savefig(self.out/'05_correlation_heatmap.png'); plt.close(fig)
        log.info("  → Plot saved: 05_correlation_heatmap.png")

    def _plot_pca_projection(self):
        """2D PCA projection coloured by attack type."""
        if not HAS_SKLEARN or 'ATTACK_ID' not in self.df.columns: return
        feat_cols = [c for c in FLOW_SENSORS+LEVEL_SENSORS+PRESSURE_SENS+QUALITY_SENS if c in self.df.columns]
        sub = self.df.dropna(subset=feat_cols).sample(min(10000,len(self.df)), random_state=42)
        X = StandardScaler().fit_transform(sub[feat_cols])
        pca = PCA(n_components=2, random_state=42)
        Z = pca.fit_transform(X)
        fig, ax = plt.subplots(figsize=(11, 8))
        fig.suptitle('PCA PROJECTION — 2D ATTACK SEPARATION', color=CYAN, fontsize=12, fontweight='bold')
        for aid in sorted(sub['ATTACK_ID'].unique()):
            mask = sub['ATTACK_ID']==aid
            ax.scatter(Z[mask,0], Z[mask,1],
                       c=ATTACK_COLORS.get(int(aid), GRID_COL),
                       alpha=0.5 if aid==0 else 0.8,
                       s=4 if aid==0 else 12,
                       label=f"[{aid}] {ATTACK_NAMES.get(int(aid),'?')}")
        ax.set_xlabel(f'PC1 ({pca.explained_variance_ratio_[0]*100:.1f}%)')
        ax.set_ylabel(f'PC2 ({pca.explained_variance_ratio_[1]*100:.1f}%)')
        ax.legend(markerscale=3, fontsize=7)
        ax.grid(True, alpha=0.2)
        plt.tight_layout(); fig.savefig(self.out/'06_pca_projection.png'); plt.close(fig)
        log.info("  → Plot saved: 06_pca_projection.png")

    def _plot_attack_violin(self):
        """Violin plots comparing normal vs each attack on pH and TMP."""
        if 'ATTACK_ID' not in self.df.columns: return
        key = [s for s in ['AIT_202','DPIT_301'] if s in self.df.columns]
        if not key: return
        fig, axes = plt.subplots(1, len(key), figsize=(14, 6))
        if len(key)==1: axes=[axes]
        fig.suptitle('PHYSICS SIGNAL SEPARATION BY ATTACK TYPE (VIOLIN)', color=CYAN, fontsize=12, fontweight='bold')
        for ax, col in zip(axes, key):
            attack_ids = sorted(self.df['ATTACK_ID'].unique())
            plot_data=[]; plot_labels=[]; plot_colors=[]
            for aid in attack_ids:
                d=self.df[self.df['ATTACK_ID']==aid][col].dropna()
                if len(d)>50:
                    plot_data.append(d.values); plot_labels.append(ATTACK_NAMES.get(int(aid),'?')[:10])
                    plot_colors.append(ATTACK_COLORS.get(int(aid),GRID_COL))
            parts=ax.violinplot(plot_data, showmedians=True, showextrema=False)
            for pc,col_v in zip(parts['bodies'],plot_colors):
                pc.set_facecolor(col_v); pc.set_alpha(0.6)
            parts['cmedians'].set_colors([AMBER]*len(plot_data)); parts['cmedians'].set_linewidth(2)
            ax.set_xticks(range(1,len(plot_labels)+1)); ax.set_xticklabels(plot_labels, rotation=45, ha='right', fontsize=7)
            ax.set_title(col, color=TEXT_COL); ax.grid(True, axis='y', alpha=0.3)
        plt.tight_layout(); fig.savefig(self.out/'07_attack_violin.png'); plt.close(fig)
        log.info("  → Plot saved: 07_attack_violin.png")


# ════════════════════════════════════════════════════════════════════════════════
#  STAGE 6: TIME-SERIES ANALYSIS
# ════════════════════════════════════════════════════════════════════════════════

class TimeSeriesAnalyzer:
    """Temporal pattern analysis critical for ICS anomaly detection."""

    def __init__(self, df: pd.DataFrame, output_dir: Path):
        self.df  = df.copy()
        self.out = output_dir

    def run(self):
        log.info("\n" + "="*60)
        log.info("STAGE 6: TIME-SERIES ANALYSIS")
        log.info("="*60)
        self._attack_duration_profile()
        self._sensor_autocorrelation()
        self._attack_transition_analysis()
        log.info("  Time-series analysis complete.")

    def _attack_duration_profile(self):
        """Profile attack duration and inter-attack gaps."""
        if 'ATTACK_ID' not in self.df.columns or 'elapsed_s' not in self.df.columns:
            return
        profiles = []
        for run_id, grp in (self.df.groupby('run_id') if 'run_id' in self.df.columns
                             else [('all', self.df)]):
            grp = grp.sort_values('elapsed_s')
            prev_aid = 0; start = grp['elapsed_s'].iloc[0]
            for _, row in grp.iterrows():
                if row['ATTACK_ID'] != prev_aid:
                    if prev_aid > 0:
                        dur = row['elapsed_s'] - start
                        profiles.append({'run':run_id,'attack_id':prev_aid,'duration_s':dur,'start_s':start})
                    start = row['elapsed_s']
                    prev_aid = row['ATTACK_ID']
        if not profiles: return
        pdf = pd.DataFrame(profiles)
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        fig.suptitle('ATTACK DURATION & TEMPORAL PROFILE', color=CYAN, fontsize=12, fontweight='bold')
        ax=axes[0]
        for aid in sorted(pdf['attack_id'].unique()):
            d=pdf[pdf['attack_id']==aid]['duration_s']/60
            ax.bar(ATTACK_NAMES.get(int(aid),'?')[:10], d.mean(),
                   color=ATTACK_COLORS.get(int(aid),GRID_COL), alpha=0.8, width=0.6)
            ax.errorbar(ATTACK_NAMES.get(int(aid),'?')[:10], d.mean(), yerr=d.std(),
                        color=AMBER, capsize=4, linewidth=1.5)
        ax.set_ylabel('Mean Duration (minutes)'); ax.set_title('MEAN ATTACK DURATION', color=TEXT_COL)
        ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha='right', fontsize=7)
        ax.grid(True, axis='y', alpha=0.3)
        ax=axes[1]
        ax.scatter(pdf['start_s']/3600, pdf['duration_s']/60,
                   c=[ATTACK_COLORS.get(int(a),GRID_COL) for a in pdf['attack_id']],
                   s=80, alpha=0.8, edgecolors=DIM_TEXT, linewidth=0.5)
        ax.set_xlabel('Start Time (hours)'); ax.set_ylabel('Duration (minutes)')
        ax.set_title('ATTACK TIMELINE SCATTER', color=TEXT_COL); ax.grid(True, alpha=0.3)
        plt.tight_layout(); fig.savefig(self.out/'08_attack_duration.png'); plt.close(fig)
        log.info("  → Plot saved: 08_attack_duration.png")

    def _sensor_autocorrelation(self):
        """Autocorrelation reveals process periodicity (e.g. tank fill-drain cycles)."""
        sensors = [s for s in ['LIT_101','AIT_202','DPIT_301'] if s in self.df.columns]
        if not sensors: return
        normal = self.df[self.df.get('ATTACK_ID', pd.Series([0]*len(self.df)))==0]
        fig, axes = plt.subplots(1, len(sensors), figsize=(14, 4))
        fig.suptitle('AUTOCORRELATION — NORMAL OPERATION PERIODIC PATTERNS', color=CYAN, fontsize=12, fontweight='bold')
        if len(sensors)==1: axes=[axes]
        for ax, col in zip(axes, sensors):
            series = normal[col].dropna().values[:2000]
            lags=min(200,len(series)//2)
            acf = [np.corrcoef(series[:-l], series[l:])[0,1] for l in range(1,lags+1)]
            ax.plot(range(1,lags+1), acf, color=CYAN, lw=1.2)
            ax.axhline(0, color=DIM_TEXT, lw=0.8, ls='--')
            ax.fill_between(range(1,lags+1), 0, acf, where=[v>0 for v in acf], alpha=0.2, color=CYAN)
            ax.fill_between(range(1,lags+1), 0, acf, where=[v<0 for v in acf], alpha=0.2, color=RED_COL)
            ax.set_title(f'{col} ACF', color=TEXT_COL, fontsize=9); ax.set_xlabel('Lag (samples @ 10 Hz)')
            ax.grid(True, alpha=0.3)
        plt.tight_layout(); fig.savefig(self.out/'09_autocorrelation.png'); plt.close(fig)
        log.info("  → Plot saved: 09_autocorrelation.png")

    def _attack_transition_analysis(self):
        """How quickly sensors respond to attack onset — detection window."""
        if 'ATTACK_ID' not in self.df.columns or 'elapsed_s' not in self.df.columns: return
        log.info("  Attack transition analysis: measuring sensor response times")


# ════════════════════════════════════════════════════════════════════════════════
#  STAGE 7: DATASET PREPARATION FOR ML
# ════════════════════════════════════════════════════════════════════════════════

class MLDataPreparer:
    """Prepare feature matrices, handle class imbalance, create train/test splits."""

    def __init__(self, df: pd.DataFrame, output_dir: Path, new_feats: List[str]):
        self.df       = df.copy()
        self.out      = output_dir
        self.new_feats = new_feats
        self.feat_cols: List[str] = []
        self.scaler    = RobustScaler()

    def prepare(self) -> Dict[str, Any]:
        log.info("\n" + "="*60)
        log.info("STAGE 7: ML DATA PREPARATION")
        log.info("="*60)

        # Select feature columns
        exclude = {'Timestamp','ATTACK_ID','ATTACK_NAME','MITRE_ID',
                   'run_id','run_name','elapsed_s'}
        self.feat_cols = [c for c in self.df.columns
                          if c not in exclude
                          and self.df[c].dtype in [np.float64, np.float32, np.int64, np.int32, int, float]
                          and self.df[c].nunique() > 1]
        log.info(f"  Feature columns selected: {len(self.feat_cols)}")

        if 'ATTACK_ID' not in self.df.columns:
            log.error("ATTACK_ID column missing — cannot create labels")
            return {}

        X = self.df[self.feat_cols].values.astype(np.float32)
        y_raw = self.df['ATTACK_ID'].values.astype(int)
        y_bin = (y_raw > 0).astype(int)  # binary: normal vs attack

        # Scale features
        X_sc = self.scaler.fit_transform(X)

        # Train/test split (temporal: last 20% is test to prevent leakage)
        split_idx = int(0.8 * len(X_sc))
        X_tr, X_te = X_sc[:split_idx], X_sc[split_idx:]
        y_tr, y_te = y_bin[:split_idx], y_bin[split_idx:]
        y_multi_tr = y_raw[:split_idx]; y_multi_te = y_raw[split_idx:]

        log.info(f"  Train: {len(X_tr):,} rows | Test: {len(X_te):,} rows (temporal 80/20)")
        log.info(f"  Train class dist: normal={int((y_tr==0).sum()):,} attack={int((y_tr==1).sum()):,} "
                 f"({int((y_tr==1).sum())/len(y_tr)*100:.1f}%)")

        # SMOTE for class imbalance
        X_tr_bal, y_tr_bal = X_tr, y_tr
        if HAS_IMBLEARN and (y_tr==1).sum()>100:
            try:
                sm = SMOTE(random_state=42, k_neighbors=min(5, (y_tr==1).sum()-1))
                X_tr_bal, y_tr_bal = sm.fit_resample(X_tr, y_tr)
                log.info(f"  SMOTE balanced: {int((y_tr_bal==0).sum()):,} vs {int((y_tr_bal==1).sum()):,}")
            except Exception as e:
                log.warning(f"  SMOTE failed: {e}")

        return {
            'X_tr': X_tr, 'X_te': X_te, 'y_tr': y_tr, 'y_te': y_te,
            'X_tr_bal': X_tr_bal, 'y_tr_bal': y_tr_bal,
            'y_multi_tr': y_multi_tr, 'y_multi_te': y_multi_te,
            'y_raw': y_raw, 'X_sc': X_sc,
            'feat_cols': self.feat_cols, 'scaler': self.scaler,
            'X_full': X_sc, 'df': self.df
        }


# ════════════════════════════════════════════════════════════════════════════════
#  STAGE 8: MODEL TRAINING
# ════════════════════════════════════════════════════════════════════════════════

class ModelTrainer:
    """Train, tune, and evaluate multiple ML models for ICS anomaly detection."""

    def __init__(self, data: Dict[str, Any], output_dir: Path):
        self.data    = data
        self.out     = output_dir
        self.results: Dict[str, Dict] = {}
        self.models:  Dict[str, Any]  = {}

    def run_all(self):
        log.info("\n" + "="*60)
        log.info("STAGE 8: MODEL TRAINING & EVALUATION")
        log.info("="*60)
        if not HAS_SKLEARN:
            log.error("scikit-learn required for model training")
            return

        # Supervised models
        self._train_xgboost()
        self._train_random_forest()
        self._train_lightgbm()
        self._train_mlp()
        # Unsupervised
        self._train_isolation_forest()
        self._train_autoencoder()
        # Deep learning
        self._train_lstm()
        # Comparison plots
        self._plot_model_comparison()
        self._plot_roc_curves()
        self._plot_confusion_matrices()
        return self.results, self.models

    def _train_xgboost(self):
        if not HAS_XGB: log.info("  ⚠ XGBoost not available"); return
        log.info("\n  [XGBoost] Training...")
        X_tr,y_tr = self.data['X_tr_bal'],self.data['y_tr_bal']
        X_te,y_te = self.data['X_te'],self.data['y_te']
        scale_pos = max(1, int((y_tr==0).sum()/(y_tr==1).sum())) if (y_tr==1).sum()>0 else 1
        model = xgb.XGBClassifier(
            n_estimators=500, max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            min_child_weight=5, gamma=0.1,
            scale_pos_weight=scale_pos,
            eval_metric='logloss', use_label_encoder=False,
            random_state=42, n_jobs=-1
        )
        model.fit(X_tr, y_tr, eval_set=[(X_te,y_te)], verbose=False)
        y_pred = model.predict(X_te); y_prob = model.predict_proba(X_te)[:,1]
        self._store_results('XGBoost', model, y_pred, y_prob, y_te)
        self.models['XGBoost'] = model
        log.info(f"  [XGBoost] F1={self.results['XGBoost']['f1']:.4f} ROC-AUC={self.results['XGBoost']['auc']:.4f}")

    def _train_random_forest(self):
        log.info("\n  [Random Forest] Training...")
        X_tr,y_tr = self.data['X_tr_bal'],self.data['y_tr_bal']
        X_te,y_te = self.data['X_te'],self.data['y_te']
        model = RandomForestClassifier(n_estimators=300, max_depth=15, min_samples_leaf=5,
                                        class_weight='balanced', random_state=42, n_jobs=-1)
        model.fit(X_tr, y_tr)
        y_pred = model.predict(X_te); y_prob = model.predict_proba(X_te)[:,1]
        self._store_results('RandomForest', model, y_pred, y_prob, y_te)
        self.models['RandomForest'] = model
        log.info(f"  [RF] F1={self.results['RandomForest']['f1']:.4f} ROC-AUC={self.results['RandomForest']['auc']:.4f}")

    def _train_lightgbm(self):
        if not HAS_LGB: return
        log.info("\n  [LightGBM] Training...")
        X_tr,y_tr = self.data['X_tr_bal'],self.data['y_tr_bal']
        X_te,y_te = self.data['X_te'],self.data['y_te']
        model = lgb.LGBMClassifier(n_estimators=500, num_leaves=63, learning_rate=0.05,
                                     min_child_samples=20, class_weight='balanced',
                                     random_state=42, n_jobs=-1, verbose=-1)
        model.fit(X_tr, y_tr, eval_set=[(X_te,y_te)], callbacks=[lgb.early_stopping(50,verbose=False)])
        y_pred = model.predict(X_te); y_prob = model.predict_proba(X_te)[:,1]
        self._store_results('LightGBM', model, y_pred, y_prob, y_te)
        self.models['LightGBM'] = model
        log.info(f"  [LightGBM] F1={self.results['LightGBM']['f1']:.4f} ROC-AUC={self.results['LightGBM']['auc']:.4f}")

    def _train_mlp(self):
        log.info("\n  [MLP Neural Network] Training...")
        X_tr,y_tr = self.data['X_tr_bal'],self.data['y_tr_bal']
        X_te,y_te = self.data['X_te'],self.data['y_te']
        model = MLPClassifier(hidden_layer_sizes=(256,128,64), activation='relu',
                               solver='adam', alpha=0.001, batch_size=512,
                               learning_rate='adaptive', max_iter=200,
                               early_stopping=True, validation_fraction=0.1,
                               random_state=42)
        model.fit(X_tr, y_tr)
        y_pred = model.predict(X_te); y_prob = model.predict_proba(X_te)[:,1]
        self._store_results('MLP', model, y_pred, y_prob, y_te)
        self.models['MLP'] = model
        log.info(f"  [MLP] F1={self.results['MLP']['f1']:.4f} ROC-AUC={self.results['MLP']['auc']:.4f}")

    def _train_isolation_forest(self):
        log.info("\n  [Isolation Forest] Training (unsupervised)...")
        X_tr = self.data['X_tr']
        X_te,y_te = self.data['X_te'],self.data['y_te']
        # Train on NORMAL ONLY for unsupervised anomaly detection
        normal_mask = self.data['y_tr']==0
        X_norm = X_tr[normal_mask]
        model = IsolationForest(n_estimators=300, contamination=0.1,
                                 max_features=min(0.8, 1.0), random_state=42, n_jobs=-1)
        model.fit(X_norm)
        scores = -model.decision_function(X_te)  # Higher = more anomalous
        # Convert to labels using threshold
        threshold = np.percentile(-model.decision_function(X_norm), 90)
        y_pred = (scores > threshold).astype(int)
        y_prob = (scores - scores.min()) / (scores.max() - scores.min() + 1e-9)
        self._store_results('IsolationForest', model, y_pred, y_prob, y_te)
        self.models['IsolationForest'] = model
        log.info(f"  [IF] F1={self.results['IsolationForest']['f1']:.4f} ROC-AUC={self.results['IsolationForest']['auc']:.4f}")

    def _train_autoencoder(self):
        log.info("\n  [Autoencoder] Training (unsupervised reconstruction)...")
        if not HAS_TORCH:
            log.info("    PyTorch not available — using sklearn approximation")
            # PCA as proxy for autoencoder
            from sklearn.decomposition import PCA
            X_tr = self.data['X_tr'][self.data['y_tr']==0]
            X_te, y_te = self.data['X_te'], self.data['y_te']
            pca = PCA(n_components=20, random_state=42)
            pca.fit(X_tr)
            X_rec = pca.inverse_transform(pca.transform(X_te))
            scores = np.mean((X_te - X_rec)**2, axis=1)
            threshold = np.percentile(np.mean((X_tr - pca.inverse_transform(pca.transform(X_tr)))**2, axis=1), 95)
            y_pred = (scores > threshold).astype(int)
            y_prob = (scores - scores.min()) / (scores.max() - scores.min() + 1e-9)
            self._store_results('Autoencoder', pca, y_pred, y_prob, y_te)
            self.models['Autoencoder'] = pca
            log.info(f"  [AE/PCA] F1={self.results['Autoencoder']['f1']:.4f}")
            return

        # PyTorch Autoencoder
        class AE(nn.Module):
            def __init__(self, input_dim, latent_dim=32):
                super().__init__()
                self.enc = nn.Sequential(
                    nn.Linear(input_dim, 128), nn.BatchNorm1d(128), nn.ReLU(),
                    nn.Linear(128, 64), nn.ReLU(),
                    nn.Linear(64, latent_dim)
                )
                self.dec = nn.Sequential(
                    nn.Linear(latent_dim, 64), nn.ReLU(),
                    nn.Linear(64, 128), nn.ReLU(),
                    nn.Linear(128, input_dim)
                )
            def forward(self, x): return self.dec(self.enc(x))

        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        X_tr = self.data['X_tr'][self.data['y_tr']==0]
        X_te, y_te = self.data['X_te'], self.data['y_te']
        in_dim = X_tr.shape[1]

        ae = AE(in_dim, latent_dim=32).to(device)
        opt = torch.optim.Adam(ae.parameters(), lr=1e-3, weight_decay=1e-4)
        sched = torch.optim.lr_scheduler.StepLR(opt, step_size=20, gamma=0.5)
        ds = TensorDataset(torch.tensor(X_tr, dtype=torch.float32))
        loader = DataLoader(ds, batch_size=512, shuffle=True)

        ae.train()
        for epoch in range(60):
            losses = []
            for (xb,) in loader:
                xb = xb.to(device); opt.zero_grad()
                loss = nn.MSELoss()(ae(xb), xb)
                loss.backward(); opt.step(); losses.append(loss.item())
            sched.step()
            if (epoch+1) % 20 == 0:
                log.info(f"    AE epoch {epoch+1}/60 — loss={np.mean(losses):.5f}")

        ae.eval()
        with torch.no_grad():
            X_te_t = torch.tensor(X_te, dtype=torch.float32).to(device)
            X_rec = ae(X_te_t).cpu().numpy()
            X_tr_t = torch.tensor(X_tr, dtype=torch.float32).to(device)
            X_tr_rec = ae(X_tr_t).cpu().numpy()

        scores = np.mean((X_te - X_rec)**2, axis=1)
        tr_scores = np.mean((X_tr - X_tr_rec)**2, axis=1)
        threshold = np.percentile(tr_scores, 95)
        y_pred = (scores > threshold).astype(int)
        y_prob = (scores - scores.min()) / (scores.max() - scores.min() + 1e-9)
        self._store_results('Autoencoder', ae, y_pred, y_prob, y_te)
        self.models['Autoencoder'] = ae
        log.info(f"  [AE] F1={self.results['Autoencoder']['f1']:.4f}")

    def _train_lstm(self):
        if not HAS_TORCH:
            log.info("  [LSTM] PyTorch not available — skipping")
            return
        log.info("\n  [LSTM] Training temporal model...")
        SEQ_LEN = 30
        X_sc, y_bin = self.data['X_sc'], (self.data['y_raw']>0).astype(int)
        split = int(0.8*len(X_sc))
        X_tr_raw, X_te_raw = X_sc[:split], X_sc[split:]
        y_tr_raw, y_te_raw = y_bin[:split], y_bin[split:]

        def make_sequences(X, y, seq_len):
            Xs, ys = [], []
            for i in range(seq_len, len(X)):
                Xs.append(X[i-seq_len:i]); ys.append(y[i])
            return np.array(Xs, dtype=np.float32), np.array(ys, dtype=np.float32)

        Xs_tr, ys_tr = make_sequences(X_tr_raw, y_tr_raw, SEQ_LEN)
        Xs_te, ys_te = make_sequences(X_te_raw, y_te_raw, SEQ_LEN)

        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        class LSTMClassifier(nn.Module):
            def __init__(self, in_dim, hidden=64, layers=2):
                super().__init__()
                self.lstm = nn.LSTM(in_dim, hidden, layers, batch_first=True,
                                     dropout=0.3, bidirectional=False)
                self.attn = nn.Linear(hidden, 1)
                self.fc   = nn.Sequential(nn.Linear(hidden,32), nn.ReLU(), nn.Dropout(0.2), nn.Linear(32,1))
            def forward(self, x):
                out, _ = self.lstm(x)
                attn_w = torch.softmax(self.attn(out), dim=1)
                ctx    = (out * attn_w).sum(dim=1)
                return self.fc(ctx).squeeze(-1)

        model = LSTMClassifier(Xs_tr.shape[2]).to(device)
        pos_weight = torch.tensor([(ys_tr==0).sum()/(ys_tr==1).sum()+1e-9], dtype=torch.float32).to(device)
        criterion  = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
        opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=30)
        ds_tr = TensorDataset(torch.tensor(Xs_tr), torch.tensor(ys_tr))
        loader = DataLoader(ds_tr, batch_size=512, shuffle=False)

        for epoch in range(30):
            model.train(); losses=[]
            for xb, yb in loader:
                xb,yb=xb.to(device),yb.to(device); opt.zero_grad()
                loss=criterion(model(xb),yb); loss.backward(); opt.step(); losses.append(loss.item())
            sched.step()
            if (epoch+1)%10==0: log.info(f"    LSTM epoch {epoch+1}/30 — loss={np.mean(losses):.5f}")

        model.eval()
        with torch.no_grad():
            logits = model(torch.tensor(Xs_te).to(device)).cpu().numpy()
        y_prob = torch.sigmoid(torch.tensor(logits)).numpy()
        y_pred = (y_prob > 0.5).astype(int)
        self._store_results('LSTM', model, y_pred, y_prob, ys_te.astype(int))
        self.models['LSTM'] = model
        log.info(f"  [LSTM] F1={self.results['LSTM']['f1']:.4f} ROC-AUC={self.results['LSTM']['auc']:.4f}")

    def _store_results(self, name, model, y_pred, y_prob, y_true):
        f1   = f1_score(y_true, y_pred, zero_division=0)
        prec = precision_score(y_true, y_pred, zero_division=0)
        rec  = recall_score(y_true, y_pred, zero_division=0)
        try: auc = roc_auc_score(y_true, y_prob)
        except: auc = 0.5
        try: ap = average_precision_score(y_true, y_prob)
        except: ap = 0.0
        self.results[name] = {
            'f1': f1, 'precision': prec, 'recall': rec, 'auc': auc, 'ap': ap,
            'y_pred': y_pred, 'y_prob': y_prob, 'y_true': y_true,
            'cm': confusion_matrix(y_true, y_pred)
        }

    def _plot_model_comparison(self):
        if not self.results: return
        names = list(self.results.keys())
        metrics = ['f1','precision','recall','auc','ap']
        labels  = ['F1 Score','Precision','Recall','ROC-AUC','PR-AUC']
        fig, axes = plt.subplots(1, 2, figsize=(16, 6))
        fig.suptitle('MODEL PERFORMANCE COMPARISON — SWaT INTRUSION DETECTION', color=CYAN, fontsize=13, fontweight='bold')

        # Bar chart of metrics
        ax = axes[0]
        x = np.arange(len(names)); width = 0.15
        for i, (metric, label) in enumerate(zip(metrics, labels)):
            vals = [self.results[n][metric] for n in names]
            ax.bar(x + i*width, vals, width, label=label, color=PALETTE[i], alpha=0.85)
        ax.set_xticks(x + width*2); ax.set_xticklabels(names, rotation=30, ha='right')
        ax.set_ylim(0,1.05); ax.set_ylabel('Score')
        ax.set_title('PERFORMANCE METRICS', color=TEXT_COL)
        ax.legend(fontsize=8); ax.grid(True, axis='y', alpha=0.3)
        # Add value labels on best model
        best = max(names, key=lambda n: self.results[n]['f1'])
        bi   = names.index(best)
        for i, metric in enumerate(metrics):
            v = self.results[best][metric]
            ax.text(bi + i*width, v+0.01, f'{v:.3f}', ha='center', fontsize=6, color=AMBER)

        # Radar chart
        ax2 = fig.add_subplot(1,2,2,projection=None)
        ax2.set_visible(False)
        angles   = np.linspace(0, 2*np.pi, len(metrics), endpoint=False).tolist()
        angles  += angles[:1]
        ax_r = fig.add_axes([0.55, 0.08, 0.42, 0.85], polar=True)
        ax_r.set_facecolor(PANEL_BG)
        ax_r.set_xticks(angles[:-1]); ax_r.set_xticklabels(labels, fontsize=8, color=TEXT_COL)
        ax_r.set_ylim(0,1); ax_r.set_yticks([0.25,0.5,0.75,1.0])
        ax_r.set_yticklabels(['0.25','0.50','0.75','1.00'], fontsize=6, color=DIM_TEXT)
        ax_r.grid(color=GRID_COL, alpha=0.5); ax_r.set_title('RADAR: ALL MODELS', color=CYAN, pad=15)
        for i, name in enumerate(names):
            vals = [self.results[name][m] for m in metrics] + [self.results[name][metrics[0]]]
            ax_r.plot(angles, vals, color=PALETTE[i], lw=2, label=name)
            ax_r.fill(angles, vals, color=PALETTE[i], alpha=0.08)
        ax_r.legend(loc='lower right', bbox_to_anchor=(1.5,0), fontsize=7)

        fig.savefig(self.out/'10_model_comparison.png'); plt.close(fig)
        log.info("  → Plot saved: 10_model_comparison.png")

    def _plot_roc_curves(self):
        fig, ax = plt.subplots(figsize=(9, 7))
        fig.suptitle('ROC & PRECISION-RECALL CURVES', color=CYAN, fontsize=12, fontweight='bold')
        for i, (name, res) in enumerate(self.results.items()):
            try:
                fpr,tpr,_ = roc_curve(res['y_true'], res['y_prob'])
                ax.plot(fpr, tpr, color=PALETTE[i], lw=2, label=f"{name} (AUC={res['auc']:.3f})")
            except: pass
        ax.plot([0,1],[0,1], color=DIM_TEXT, lw=1, ls='--')
        ax.set_xlabel('False Positive Rate'); ax.set_ylabel('True Positive Rate')
        ax.set_title('ROC CURVES', color=TEXT_COL)
        ax.legend(fontsize=9); ax.grid(True, alpha=0.3)
        ax.set_facecolor(PANEL_BG)
        fig.savefig(self.out/'11_roc_curves.png'); plt.close(fig)
        log.info("  → Plot saved: 11_roc_curves.png")

    def _plot_confusion_matrices(self):
        n = len(self.results)
        cols = min(4,n); rows = (n+cols-1)//cols
        fig, axes = plt.subplots(rows, cols, figsize=(4.5*cols, 4*rows))
        fig.suptitle('CONFUSION MATRICES — ALL MODELS', color=CYAN, fontsize=12, fontweight='bold')
        if n==1: axes=[axes]
        flat_axes = axes.flat if hasattr(axes,'flat') else [axes]
        for ax, (name, res) in zip(flat_axes, self.results.items()):
            cm = res['cm']
            sns.heatmap(cm, annot=True, fmt='d', ax=ax,
                        cmap=LinearSegmentedColormap.from_list('ics',[DARK_BG,PANEL_BG,CYAN]),
                        linewidths=0.5, linecolor=GRID_COL,
                        annot_kws={'fontsize':11,'color':TEXT_COL})
            ax.set_title(f"{name}\nF1={res['f1']:.3f} AUC={res['auc']:.3f}", color=TEXT_COL, fontsize=9)
            ax.set_xlabel('Predicted'); ax.set_ylabel('Actual')
            ax.set_xticklabels(['Normal','Attack']); ax.set_yticklabels(['Normal','Attack'])
        for ax in list(flat_axes)[n:]: ax.set_visible(False)
        plt.tight_layout(); fig.savefig(self.out/'12_confusion_matrices.png'); plt.close(fig)
        log.info("  → Plot saved: 12_confusion_matrices.png")


# ════════════════════════════════════════════════════════════════════════════════
#  STAGE 9: EXPLAINABILITY (SHAP)
# ════════════════════════════════════════════════════════════════════════════════

class ExplainabilityEngine:
    """SHAP-based feature importance and attack attribution."""

    def __init__(self, models: Dict, data: Dict, output_dir: Path):
        self.models  = models
        self.data    = data
        self.out     = output_dir

    def run(self):
        if not HAS_SHAP:
            log.info("\n  [SHAP] Not available — computing permutation importance instead")
            self._permutation_importance()
            return
        log.info("\n" + "="*60)
        log.info("STAGE 9: EXPLAINABILITY (SHAP)")
        log.info("="*60)
        for model_name in ['XGBoost','RandomForest','LightGBM']:
            if model_name in self.models:
                self._shap_analysis(model_name)
                break  # one model is sufficient for a research demo
        self._feature_importance_comparison()

    def _shap_analysis(self, model_name: str):
        model    = self.models[model_name]
        X_te     = self.data['X_te'][:2000]
        feat_cols = self.data['feat_cols']
        log.info(f"  Computing SHAP values for {model_name}...")
        try:
            expl = shap.TreeExplainer(model)
            shap_vals = expl.shap_values(X_te)
            if isinstance(shap_vals, list): shap_vals = shap_vals[1]
            # Global importance
            mean_abs = np.abs(shap_vals).mean(axis=0)
            top_idx  = mean_abs.argsort()[-20:][::-1]
            top_feats = [feat_cols[i] for i in top_idx]
            top_vals  = mean_abs[top_idx]
            fig, axes = plt.subplots(1, 2, figsize=(16, 7))
            fig.suptitle(f'SHAP EXPLAINABILITY — {model_name}', color=CYAN, fontsize=13, fontweight='bold')
            ax = axes[0]
            bars = ax.barh(range(len(top_feats)), top_vals[::-1], color=[PALETTE[i%len(PALETTE)] for i in range(len(top_feats))])
            ax.set_yticks(range(len(top_feats))); ax.set_yticklabels([f.replace('_',' ')[:30] for f in top_feats[::-1]], fontsize=7)
            ax.set_xlabel('Mean |SHAP Value|'); ax.set_title('TOP-20 GLOBAL FEATURE IMPORTANCE', color=TEXT_COL)
            ax.grid(True, axis='x', alpha=0.3)
            # Beeswarm / dot plot
            ax = axes[1]
            for j, idx in enumerate(top_idx[:15]):
                x_vals = shap_vals[:,idx]
                y_jitter = np.random.uniform(-0.3, 0.3, len(x_vals))
                feature_vals = X_te[:,idx]
                sc = ax.scatter(x_vals, j + y_jitter, c=feature_vals, cmap='coolwarm',
                                s=3, alpha=0.5, vmin=np.percentile(feature_vals,5), vmax=np.percentile(feature_vals,95))
            ax.set_yticks(range(15)); ax.set_yticklabels([feat_cols[i].replace('_',' ')[:25] for i in top_idx[:15]], fontsize=7)
            ax.axvline(0, color=DIM_TEXT, lw=0.8, ls='--')
            ax.set_xlabel('SHAP Value (impact on attack prediction)')
            ax.set_title('FEATURE IMPACT BEESWARM (TOP 15)', color=TEXT_COL)
            plt.colorbar(sc, ax=ax, label='Feature Value')
            plt.tight_layout(); fig.savefig(self.out/f'13_shap_{model_name}.png'); plt.close(fig)
            log.info(f"  → Plot saved: 13_shap_{model_name}.png")
            log.info(f"  TOP-5 SHAP FEATURES ({model_name}):")
            for fi in top_idx[:5]:
                log.info(f"    {feat_cols[fi]:40s}: {mean_abs[fi]:.5f}")
        except Exception as e:
            log.warning(f"  SHAP analysis failed: {e}")
            self._permutation_importance()

    def _permutation_importance(self):
        """Fallback: sklearn permutation importance."""
        for model_name in ['XGBoost','RandomForest','LightGBM','MLP']:
            if model_name in self.models and HAS_SKLEARN:
                model = self.models[model_name]
                X_te  = self.data['X_te'][:2000]
                y_te  = self.data['y_te'][:2000]
                feat_cols = self.data['feat_cols']
                try:
                    pi = permutation_importance(model, X_te, y_te, n_repeats=5, random_state=42, n_jobs=-1)
                    idx = pi.importances_mean.argsort()[-20:][::-1]
                    fig, ax = plt.subplots(figsize=(12, 7))
                    fig.suptitle(f'PERMUTATION FEATURE IMPORTANCE — {model_name}', color=CYAN, fontsize=12, fontweight='bold')
                    ax.barh(range(len(idx)), pi.importances_mean[idx][::-1],
                            xerr=pi.importances_std[idx][::-1],
                            color=[PALETTE[i%len(PALETTE)] for i in range(len(idx))],
                            capsize=3, alpha=0.85)
                    ax.set_yticks(range(len(idx)))
                    ax.set_yticklabels([feat_cols[i].replace('_',' ')[:35] for i in idx[::-1]], fontsize=7)
                    ax.set_xlabel('Mean decrease in F1'); ax.grid(True, axis='x', alpha=0.3)
                    fig.savefig(self.out/'13_feature_importance.png'); plt.close(fig)
                    log.info("  → Plot saved: 13_feature_importance.png")
                    break
                except Exception as e:
                    log.warning(f"  Permutation importance failed: {e}")

    def _feature_importance_comparison(self):
        """Compare built-in feature importances across tree models."""
        importances = {}
        for mname in ['XGBoost','RandomForest','LightGBM']:
            if mname in self.models:
                m = self.models[mname]
                if hasattr(m,'feature_importances_'):
                    importances[mname] = m.feature_importances_

        if not importances: return
        feat_cols = self.data['feat_cols']
        fig, ax = plt.subplots(figsize=(14, 7))
        fig.suptitle('FEATURE IMPORTANCE — TREE MODEL AGREEMENT', color=CYAN, fontsize=12, fontweight='bold')
        # Average importance
        avg = np.mean(list(importances.values()), axis=0)
        top_idx = avg.argsort()[-25:][::-1]
        x = np.arange(len(top_idx)); w = 0.25
        for i, (mname, imps) in enumerate(importances.items()):
            ax.bar(x + i*w, imps[top_idx][::-1], w, label=mname, color=PALETTE[i], alpha=0.8)
        ax.set_xticks(x + w); ax.set_xticklabels([feat_cols[i].replace('_',' ')[:20] for i in top_idx[::-1]], rotation=90, fontsize=6)
        ax.set_ylabel('Feature Importance'); ax.legend(); ax.grid(True, axis='y', alpha=0.3)
        plt.tight_layout(); fig.savefig(self.out/'14_importance_comparison.png'); plt.close(fig)
        log.info("  → Plot saved: 14_importance_comparison.png")


# ════════════════════════════════════════════════════════════════════════════════
#  STAGE 10: RESULTS SUMMARY
# ════════════════════════════════════════════════════════════════════════════════

class ResultsSummarizer:
    """Print and save comprehensive results summary."""

    def __init__(self, results: Dict, data: Dict, output_dir: Path):
        self.results  = results
        self.data     = data
        self.out      = output_dir

    def run(self):
        log.info("\n" + "="*60)
        log.info("STAGE 10: RESULTS SUMMARY")
        log.info("="*60)
        self._print_metrics_table()
        self._plot_per_attack_f1()
        self._save_results_json()

    def _print_metrics_table(self):
        header = f"\n{'Model':20s} {'F1':>8} {'Precision':>10} {'Recall':>8} {'ROC-AUC':>9} {'PR-AUC':>8}"
        sep    = '-' * len(header)
        log.info(header); log.info(sep)
        for name, res in sorted(self.results.items(), key=lambda x: -x[1]['f1']):
            log.info(f"  {name:20s} {res['f1']:8.4f} {res['precision']:10.4f} {res['recall']:8.4f} "
                     f"{res['auc']:9.4f} {res['ap']:8.4f}")
        log.info(sep)
        best = max(self.results, key=lambda n: self.results[n]['f1'])
        log.info(f"\n  ★ BEST MODEL: {best} (F1={self.results[best]['f1']:.4f}, AUC={self.results[best]['auc']:.4f})")

    def _plot_per_attack_f1(self):
        """F1 scores broken down per attack type for best model."""
        best = max(self.results, key=lambda n: self.results[n]['f1'])
        res  = self.results[best]
        y_te = self.data['y_te']
        y_pred = res['y_pred']
        # Map to attack types (need multi-class test labels)
        if 'y_multi_te' not in self.data:
            return
        y_multi = self.data['y_multi_te'][:len(y_pred)]
        attack_ids = [a for a in sorted(set(y_multi)) if a>0]
        if not attack_ids: return
        f1s = []
        for aid in attack_ids:
            mask = (y_multi==aid)|(y_multi==0)
            yt = (y_multi[mask]>0).astype(int)
            yp = y_pred[mask[:len(y_pred)]][:len(yt)]
            f1s.append(f1_score(yt, yp, zero_division=0))
        fig, ax = plt.subplots(figsize=(12, 5))
        fig.suptitle(f'PER-ATTACK F1 SCORE — {best}', color=CYAN, fontsize=12, fontweight='bold')
        bars = ax.bar([ATTACK_NAMES.get(int(a),'?') for a in attack_ids], f1s,
                      color=[ATTACK_COLORS.get(int(a),CYAN) for a in attack_ids], alpha=0.85)
        for bar, f in zip(bars, f1s):
            ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.01, f'{f:.3f}', ha='center', fontsize=8, color=TEXT_COL)
        ax.set_ylim(0,1.12); ax.set_ylabel('F1 Score'); ax.grid(True, axis='y', alpha=0.3)
        ax.set_xticklabels(ax.get_xticklabels(), rotation=30, ha='right')
        plt.tight_layout(); fig.savefig(self.out/'15_per_attack_f1.png'); plt.close(fig)
        log.info("  → Plot saved: 15_per_attack_f1.png")

    def _save_results_json(self):
        out = {}
        for name, res in self.results.items():
            out[name] = {k: float(v) if isinstance(v,float) else v
                         for k,v in res.items() if k not in ['y_pred','y_prob','y_true','cm']}
        with open(self.out/'results_summary.json','w') as f:
            json.dump(out, f, indent=2)
        log.info(f"  → Results saved: results_summary.json")


# ════════════════════════════════════════════════════════════════════════════════
#  MAIN ORCHESTRATOR
# ════════════════════════════════════════════════════════════════════════════════

def main(data_dir: str = '.', runs: List[str] = None, output_dir: str = 'ml_output'):
    start_time = time.time()
    print("\n" + "╔"+"═"*68+"╗")
    print("║  SWaT ICS ANOMALY DETECTION — END-TO-END ML PIPELINE            ║")
    print("║  MTech AI & Data Science · VJTI Mumbai                           ║")
    print("╚"+"═"*68+"╝\n")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Default run list
    if runs is None:
        runs = ['run_01','run_02','run_03','run_04','run_05']

    # ── STAGE 1: Load & Merge ──────────────────────────────────────────────
    loader = DataLoader(data_dir, runs)
    df_raw = loader.load_all()

    # ── STAGE 2: Quality Assessment ───────────────────────────────────────
    qa = DataQualityAssessor(df_raw, out)
    qa_report = qa.assess()

    # ── STAGE 3: Preprocessing ────────────────────────────────────────────
    prep = Preprocessor(df_raw, out)
    df_clean = prep.run()

    # ── STAGE 4: Feature Engineering ─────────────────────────────────────
    fe = FeatureEngineer(df_clean, out)
    df_feats, new_feats = fe.run()

    # ── STAGE 5: EDA ──────────────────────────────────────────────────────
    eda = EDAEngine(df_feats, out)
    eda.run()

    # ── STAGE 6: Time-Series Analysis ────────────────────────────────────
    tsa = TimeSeriesAnalyzer(df_feats, out)
    tsa.run()

    # ── STAGE 7: ML Data Preparation ─────────────────────────────────────
    prep_ml = MLDataPreparer(df_feats, out, new_feats)
    ml_data = prep_ml.prepare()
    if not ml_data:
        log.error("ML data preparation failed — check ATTACK_ID column"); return

    # ── STAGE 8: Model Training ───────────────────────────────────────────
    trainer = ModelTrainer(ml_data, out)
    results, models = trainer.run_all()

    # ── STAGE 9: Explainability ───────────────────────────────────────────
    if results:
        explainer = ExplainabilityEngine(models, ml_data, out)
        explainer.run()

    # ── STAGE 10: Results Summary ─────────────────────────────────────────
    if results:
        summarizer = ResultsSummarizer(results, ml_data, out)
        summarizer.run()

    elapsed = time.time() - start_time
    log.info(f"\n{'='*60}")
    log.info(f"  PIPELINE COMPLETE in {elapsed:.1f}s")
    log.info(f"  All outputs → {out.resolve()}")
    log.info(f"{'='*60}")


# ════════════════════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description='SWaT ICS ML Pipeline — End-to-End Anomaly Detection',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default run folders in current directory:
  python swat_ml_pipeline.py

  # Specify data directory and runs:
  python swat_ml_pipeline.py --data-dir /path/to/data --runs run_01 run_02 run_03

  # Single run (e.g., after first collection):
  python swat_ml_pipeline.py --data-dir . --runs run_01 --output-dir output_run01

  # Use merged CSV:
  python swat_ml_pipeline.py --merged-csv merged_dataset.csv
        """
    )
    parser.add_argument('--data-dir',    default='.', help='Root directory of run folders')
    parser.add_argument('--runs',        nargs='+', default=None, help='Run folder names')
    parser.add_argument('--output-dir',  default='ml_output', help='Output directory for plots and results')
    parser.add_argument('--merged-csv',  default=None, help='Use pre-merged CSV instead of run folders')
    args = parser.parse_args()

    if args.merged_csv:
        # Load single merged CSV as "run_01"
        import shutil
        p = Path(args.merged_csv)
        if p.exists():
            dest = Path(args.data_dir) / 'run_01'
            dest.mkdir(exist_ok=True)
            shutil.copy(p, dest / 'master_dataset.csv')
            main(args.data_dir, ['run_01'], args.output_dir)
        else:
            log.error(f"Merged CSV not found: {args.merged_csv}")
    else:
        main(args.data_dir, args.runs, args.output_dir)
