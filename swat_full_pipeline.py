"""
SWaT Digital Twin — 3-Layer Ensemble Anomaly Detection
=======================================================
Architecture : Isolation Forest → XGBoost → LSTM + SHAP Explainability
Target       : Binary F1 > 0.9 | ROC-AUC > 0.9 | FPR < 3 %

Changes vs. original notebook
-------------------------------
1. Removed irrelevant features : energy, fouling-factor, tank-level columns
2. SMOTE applied to training set to balance minority attack classes
3. Full GPU support : TensorFlow LSTM on CUDA GPU + XGBoost GPU acceleration
"""

# =============================================================================
# 0.  ENVIRONMENT SETUP
# =============================================================================
import subprocess, sys

packages = [
    'xgboost', 'shap', 'scikit-learn', 'pandas', 'numpy',
    'matplotlib', 'seaborn', 'tensorflow', 'imbalanced-learn'
]
for pkg in packages:
    try:
        __import__(pkg.replace('-', '_'))
    except ImportError:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '-q'])

import warnings
warnings.filterwarnings('ignore')

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    classification_report, confusion_matrix, roc_auc_score,
    roc_curve, precision_recall_curve, f1_score,
    average_precision_score, ConfusionMatrixDisplay
)

import xgboost as xgb
import shap

import tensorflow as tf
from tensorflow.keras.models import Model, Sequential
from tensorflow.keras.layers import (
    LSTM, Dense, Dropout, Input, Bidirectional, BatchNormalization
)
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
from tensorflow.keras.utils import to_categorical

# SMOTE for class balancing
from imblearn.over_sampling import SMOTE

# ── Reproducibility ──────────────────────────────────────────────────────────
SEED = 42
np.random.seed(SEED)
tf.random.set_seed(SEED)

# ── GPU Configuration ─────────────────────────────────────────────────────────
# TensorFlow — allow memory growth so the GPU is not fully reserved
gpus = tf.config.list_physical_devices('GPU')
if gpus:
    try:
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)
        print(f'[GPU] TensorFlow detected {len(gpus)} GPU(s): {[g.name for g in gpus]}')
        print('[GPU] Memory-growth enabled — TF will use GPU for LSTM training.')
    except RuntimeError as e:
        print(f'[GPU] Memory-growth config error: {e}')
else:
    print('[GPU] No GPU detected by TensorFlow — LSTM will run on CPU.')

# XGBoost GPU device string (used later when building the model)
# 'cuda' for XGBoost >= 2.0 ;  older versions used 'gpu_hist'
try:
    _xgb_ver = tuple(int(x) for x in xgb.__version__.split('.')[:2])
    XGB_DEVICE = 'cuda' if _xgb_ver >= (2, 0) else 'gpu_hist'
    XGB_TREE_METHOD = 'hist'           # 'hist' works for both CPU and GPU in XGB>=2
except Exception:
    XGB_DEVICE = 'cpu'
    XGB_TREE_METHOD = 'hist'

# Detect if an NVIDIA GPU is actually available for XGBoost
try:
    _test_dmat = xgb.DMatrix(np.zeros((2, 2)), label=np.zeros(2))
    _test_params = {'tree_method': XGB_TREE_METHOD, 'device': XGB_DEVICE,
                    'n_estimators': 1, 'verbosity': 0}
    xgb.train(_test_params, _test_dmat, num_boost_round=1)
    print(f'[GPU] XGBoost GPU ({XGB_DEVICE}) confirmed available.')
except Exception:
    XGB_DEVICE = 'cpu'
    print('[GPU] XGBoost GPU not available — will use CPU.')

# ── Plot style ────────────────────────────────────────────────────────────────
plt.rcParams.update({
    'figure.dpi': 120,
    'axes.grid': True,
    'grid.alpha': 0.3,
    'font.size': 11
})
sns.set_palette('husl')

print(f'TensorFlow : {tf.__version__}')
print(f'XGBoost    : {xgb.__version__}')
print(f'NumPy      : {np.__version__}')


# =============================================================================
# STEP 1 — DATA LOADING & INSPECTION
# =============================================================================
# Loads the master dataset, parses timestamps, sorts chronologically,
# and handles missing values.

DATASET_PATH   = 'data/attack_24h_hw(1)/master_dataset.csv'
SAMPLE_RATE_HZ = 10       # 10 Hz → dt = 0.1 s
EXPECTED_DT    = 0.1      # seconds per sample

print(f'\nLoading dataset from: {DATASET_PATH}')
df = pd.read_csv(DATASET_PATH)

# ── Timestamp parsing ─────────────────────────────────────────────────────────
ts_col = None
for col in ['Timestamp', 'timestamp', 'Time', 'time', 'datetime']:
    if col in df.columns:
        ts_col = col
        break

if ts_col:
    df[ts_col] = pd.to_datetime(df[ts_col], infer_datetime_format=True)
    df = df.sort_values(ts_col).reset_index(drop=True)
    df.rename(columns={ts_col: 'Timestamp'}, inplace=True)
    print(f'Timestamp column: "{ts_col}"  |  Range: {df["Timestamp"].min()} → {df["Timestamp"].max()}')
else:
    print('⚠ No timestamp column found — creating synthetic index timestamps.')
    df.insert(0, 'Timestamp', pd.date_range('2026-01-01', periods=len(df), freq='100ms'))

print(f'\nShape: {df.shape[0]:,} rows × {df.shape[1]} columns')
print(f'Duration: ~{len(df)/SAMPLE_RATE_HZ/3600:.2f} hours at 10 Hz')
print(f'\nColumn types:')
print(df.dtypes.value_counts())

# ── Missing values ────────────────────────────────────────────────────────────
missing = df.isnull().sum()
miss_df = pd.DataFrame({'count': missing, 'pct': (missing / len(df) * 100).round(2)})
miss_df = miss_df[miss_df['count'] > 0].sort_values('pct', ascending=False)

if len(miss_df) > 0:
    print(f'Columns with missing values ({len(miss_df)}):')
    print(miss_df.to_string())
    df.fillna(method='ffill', inplace=True)
    df.fillna(method='bfill', inplace=True)
    print('\n✅ Missing values filled (ffill → bfill).')
else:
    print('✅ No missing values.')

# ── Boolean → int conversion ──────────────────────────────────────────────────
bool_cols = df.select_dtypes(include='bool').columns.tolist()
if bool_cols:
    df[bool_cols] = df[bool_cols].astype(int)
    print(f'Converted {len(bool_cols)} boolean columns to int.')

# ── Object columns → numeric where possible ───────────────────────────────────
obj_cols = [c for c in df.select_dtypes(include='object').columns if c != 'Timestamp']
for col in obj_cols:
    try:
        df[col] = pd.to_numeric(df[col])
    except Exception:
        pass

# ── ATTACK_ID check ───────────────────────────────────────────────────────────
assert 'ATTACK_ID' in df.columns, '❌ ATTACK_ID column missing!'
print('\nATTACK_ID distribution:')
atk_counts = df['ATTACK_ID'].value_counts().sort_index()
for aid, cnt in atk_counts.items():
    pct = cnt / len(df) * 100
    lbl = 'NORMAL' if aid == 0 else f'ATTACK_{int(aid)}'
    print(f'  {lbl:15s}: {cnt:8,} rows  ({pct:.1f}%)')

# ── Class distribution visualisation ─────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 4))

atk_name_map = {
    1: 'Reconnaissance', 2: 'Replay',       3: 'pH Manipulation',
    4: 'Slow Ramp',      5: 'Pump Failure',  6: 'Valve Manip.',
    7: 'Multi-stage',    8: 'Sensor Spoof'
}
attack_map = {0: 'Normal'}
attack_map.update(atk_name_map)
labels = [attack_map.get(i, f'Class {i}') for i in atk_counts.index]
colors = ['#2ecc71' if i == 0 else '#e74c3c' for i in atk_counts.index]

axes[0].bar(labels, atk_counts.values, color=colors, edgecolor='black', linewidth=0.5)
axes[0].set_title('Sample Count per Class')
axes[0].set_xlabel('Class')
axes[0].set_ylabel('Count')
axes[0].tick_params(axis='x', rotation=30)

normal_count = atk_counts.get(0, 0)
attack_total = atk_counts[atk_counts.index != 0].sum()
axes[1].pie([normal_count, attack_total],
            labels=['Normal', 'Attack'],
            colors=['#2ecc71', '#e74c3c'],
            autopct='%1.1f%%', startangle=90)
axes[1].set_title('Normal vs Attack Split')

plt.suptitle('Dataset Class Distribution', fontsize=14, fontweight='bold')
plt.tight_layout()
plt.show()


# =============================================================================
# STEP 2 — FEATURE ENGINEERING
# =============================================================================
# Five feature groups engineered specifically for 10 Hz CPS data:
#   1. Temporal   — timing anomalies (jitter, delay, dropout)
#   2. Physical   — mass balance, pressure spikes, pH deviation
#   3. Control    — PLC rule violations, actuator consistency
#   4. Statistical— rolling mean/std windows
#   5. Derived    — rate-of-change, lag features

# ── Identify column groups ────────────────────────────────────────────────────
all_cols = df.columns.tolist()

# Columns explicitly excluded from the feature set:
#   - Timestamp / label columns (always excluded)
#   - Energy columns  (Energy_P101, Energy_P301, Energy_P501, Energy_Total)
#     → not meaningful for detecting cyber attacks on the process
#   - Fouling-factor columns (any col containing 'Fouling')
#     → internal MATLAB state; not a PLC-observable physical sensor
#   - Chemical tank-level columns (Acid_Tank_Level, Chlorine_Tank, etc.)
exclude_cols = ['Timestamp', 'ATTACK_ID', 'ATTACK_NAME']

# Drop energy columns
energy_cols = [c for c in all_cols if c.startswith('Energy')]
exclude_cols += energy_cols

# Drop fouling-factor columns
fouling_cols = [c for c in all_cols if 'Fouling' in c or 'fouling' in c]
exclude_cols += fouling_cols

# Drop chemical tank-level columns (not core process sensors)
tank_level_cols = [c for c in all_cols
                   if any(kw in c for kw in
                          ['Acid_Tank', 'Chlorine_Tank', 'Coagulant_Tank',
                           'Bisulfate_Tank', 'Tank_Level'])]
exclude_cols += tank_level_cols

# Deduplicate
exclude_cols = list(dict.fromkeys(exclude_cols))

sensor_cols   = [c for c in all_cols if any(c.startswith(p) for p in ['LIT','PIT','AIT','DPIT','FIT'])]
actuator_cols = [c for c in all_cols if any(c.startswith(p) for p in ['P_','MV_','UV_'])]
numeric_cols  = [c for c in all_cols
                 if c not in exclude_cols and df[c].dtype in ['float64','int64','int32','float32']]

print(f'Sensor columns   : {len(sensor_cols)}')
print(f'Actuator columns : {len(actuator_cols)}')
print(f'Total numeric    : {len(numeric_cols)}')
print(f'Excluded ({len(exclude_cols)} cols): '
      f'energy={len(energy_cols)}, fouling={len(fouling_cols)}, '
      f'tank_level={len(tank_level_cols)}, labels=3')

# ── GROUP 1 — TEMPORAL FEATURES  (10 Hz = 0.1 s expected delta) ──────────────
print('Engineering temporal features...')

if 'Timestamp' in df.columns and pd.api.types.is_datetime64_any_dtype(df['Timestamp']):
    df['delta_t'] = df['Timestamp'].diff().dt.total_seconds().fillna(EXPECTED_DT)
else:
    df['delta_t'] = EXPECTED_DT

dt_mean = df['delta_t'].mean()
dt_std  = df['delta_t'].std() + 1e-9
df['delta_t_zscore']       = (df['delta_t'] - dt_mean) / dt_std
df['delta_t_rolling_mean'] = df['delta_t'].rolling(50, min_periods=1).mean()
df['delay_anomaly']        = (df['delta_t'] > 0.2).astype(int)
df['delay_severe']         = (df['delta_t'] > 0.5).astype(int)
df['jitter']               = (df['delta_t'] - df['delta_t_rolling_mean']).abs()
df['jitter_high']          = (df['jitter'] > 0.05).astype(int)

temporal_feat = ['delta_t','delta_t_zscore','delta_t_rolling_mean',
                 'delay_anomaly','delay_severe','jitter','jitter_high']
print(f'  ✅ {len(temporal_feat)} temporal features')

# ── GROUP 2 — PHYSICAL FEATURES  (mass balance, pressure, pH) ─────────────────
print('Engineering physical features...')
physical_feat = []

for a, b in [('LIT_101','LIT_301'), ('LIT_301','LIT_401'), ('LIT_401','LIT_501')]:
    if a in df.columns and b in df.columns:
        feat = f'level_diff_{a}_{b}'
        df[feat] = df[a] - df[b]
        physical_feat.append(feat)

flow_pairs = [
    ('FIT_101','FIT_201'), ('FIT_201','FIT_301'),
    ('FIT_301','FIT_401'), ('FIT_401','FIT_501'), ('FIT_501','FIT_601'),
]
for a, b in flow_pairs:
    if a in df.columns and b in df.columns:
        feat = f'flow_balance_{a}_{b}'
        df[feat] = df[a] - df[b]
        physical_feat.append(feat)

if 'PIT_501' in df.columns:
    df['pressure_spike'] = (df['PIT_501'] > 1800).astype(int)
    physical_feat.append('pressure_spike')

if 'DPIT_301' in df.columns:
    df['dpit_roc']  = df['DPIT_301'].diff().fillna(0)
    df['dpit_roc2'] = df['dpit_roc'].diff().fillna(0)
    physical_feat += ['dpit_roc', 'dpit_roc2']

for ph_col in ['AIT_202', 'AIT_203', 'AIT_402']:
    if ph_col in df.columns:
        feat = f'{ph_col}_pH_deviation'
        df[feat] = ((df[ph_col] < 650) | (df[ph_col] > 850)).astype(int)
        physical_feat.append(feat)

if 'AIT_201' in df.columns:
    df['turbidity_high'] = (df['AIT_201'] > 800).astype(int)
    physical_feat.append('turbidity_high')

print(f'  ✅ {len(physical_feat)} physical features')

# ── GROUP 3 — CONTROL / PLC RULE FEATURES ─────────────────────────────────────
print('Engineering control / PLC rule features...')
control_feat = []

if 'P_101' in df.columns and 'FIT_101' in df.columns:
    fit_threshold = df['FIT_101'].quantile(0.10)
    df['pump_flow_inconsistency'] = (
        (df['P_101'] == 1) & (df['FIT_101'] < max(fit_threshold, 0.05))
    ).astype(int)
    control_feat.append('pump_flow_inconsistency')

if 'AIT_202' in df.columns and 'P_203' in df.columns:
    df['ph_pump_inconsistency'] = (
        (df['AIT_202'] > 750) & (df['P_203'] == 0)
    ).astype(int)
    control_feat.append('ph_pump_inconsistency')

for mv_col, fit_col in [('MV_101','FIT_101'), ('MV_201','FIT_201'), ('MV_301','FIT_301')]:
    if mv_col in df.columns and fit_col in df.columns:
        fit_thr = df[fit_col].quantile(0.05)
        feat = f'valve_flow_mismatch_{mv_col}'
        df[feat] = (
            (df[mv_col] == 0) & (df[fit_col] > max(fit_thr * 2, 0.1))
        ).astype(int)
        control_feat.append(feat)

for p_col in ['P_101', 'P_301', 'P_501']:
    if p_col in df.columns:
        feat = f'{p_col}_duty_60'
        df[feat] = df[p_col].rolling(60, min_periods=1).mean()
        control_feat.append(feat)

for s_col in sensor_cols:
    feat = f'{s_col}_roc'
    df[feat] = df[s_col].diff().fillna(0)
    control_feat.append(feat)

print(f'  ✅ {len(control_feat)} control features')

# ── GROUP 4 — STATISTICAL FEATURES  (rolling window=20 = 2 seconds) ───────────
print('Engineering rolling statistical features...')
stat_feat = []
W = 20   # 20 samples = 2 seconds at 10 Hz

for s_col in sensor_cols:
    df[f'{s_col}_roll_mean'] = df[s_col].rolling(W, min_periods=1).mean()
    df[f'{s_col}_roll_std']  = df[s_col].rolling(W, min_periods=1).std().fillna(0)
    roll_std = df[f'{s_col}_roll_std'].replace(0, 1e-9)
    df[f'{s_col}_roll_zscore'] = (df[s_col] - df[f'{s_col}_roll_mean']) / roll_std
    stat_feat += [f'{s_col}_roll_mean', f'{s_col}_roll_std', f'{s_col}_roll_zscore']

print(f'  ✅ {len(stat_feat)} statistical features')

# ── GROUP 5 — LAG FEATURES  (temporal context for tree models) ────────────────
print('Engineering lag features...')
lag_feat = []
lag_cols = ['LIT_101', 'AIT_202', 'FIT_101', 'DPIT_301', 'PIT_501']
lag_cols = [c for c in lag_cols if c in df.columns]
lags = [5, 10, 30]   # 0.5 s, 1 s, 3 s

for col in lag_cols:
    for lag in lags:
        feat = f'{col}_lag{lag}'
        df[feat] = df[col].shift(lag).fillna(method='bfill')
        lag_feat.append(feat)

print(f'  ✅ {len(lag_feat)} lag features')

all_engineered = temporal_feat + physical_feat + control_feat + stat_feat + lag_feat
print(f'\n━━ Total engineered features: {len(all_engineered)} ━━')

# ── Drop low-variance features  (std < 0.01) ──────────────────────────────────
print('Dropping low-variance features...')
candidate_cols = list(set(numeric_cols + all_engineered))
candidate_cols = [c for c in candidate_cols if c in df.columns]

std_series = df[candidate_cols].std()
low_var    = std_series[std_series < 0.01].index.tolist()

print(f'  Removed {len(low_var)} low-variance columns:')
if low_var:
    print(f'  {low_var[:10]}{"..." if len(low_var) > 10 else ""}')

feature_cols = [c for c in candidate_cols if c not in low_var]
print(f'  ✅ Final feature set: {len(feature_cols)} columns')


# =============================================================================
# STEP 3 — LABEL PREPARATION
# =============================================================================
df['label_binary'] = (df['ATTACK_ID'] > 0).astype(int)
df['label_multi']  = df['ATTACK_ID'].astype(int)

le = LabelEncoder()
df['label_encoded'] = le.fit_transform(df['label_multi'])
n_classes = len(le.classes_)

print(f'Binary labels  — 0: {(df["label_binary"]==0).sum():,}  |  1: {(df["label_binary"]==1).sum():,}')
print(f'Multi-class    — {n_classes} unique classes: {le.classes_.tolist()}')

X       = df[feature_cols].values.astype(np.float32)
y_bin   = df['label_binary'].values
y_multi = df['label_encoded'].values

print(f'\nFeature matrix X: {X.shape}')


# =============================================================================
# STEP 4 — TRAIN / VALIDATION / TEST SPLIT
# =============================================================================
# Stratified 70 / 15 / 15 split preserving class proportions.
# Scaling is fit on train only — no data leakage.

X_trainval, X_test, y_bin_trainval, y_bin_test, y_multi_trainval, y_multi_test = \
    train_test_split(X, y_bin, y_multi,
                     test_size=0.15, random_state=SEED, stratify=y_bin)

X_train, X_val, y_bin_train, y_bin_val, y_multi_train, y_multi_val = \
    train_test_split(X_trainval, y_bin_trainval, y_multi_trainval,
                     test_size=0.15/0.85, random_state=SEED, stratify=y_bin_trainval)

print(f'Train : {X_train.shape[0]:>8,} samples  ({X_train.shape[0]/len(X)*100:.1f}%)')
print(f'Val   : {X_val.shape[0]:>8,} samples  ({X_val.shape[0]/len(X)*100:.1f}%)')
print(f'Test  : {X_test.shape[0]:>8,} samples  ({X_test.shape[0]/len(X)*100:.1f}%)')

# ── RobustScaler (fit on train only) ──────────────────────────────────────────
scaler     = RobustScaler()
X_train_sc = scaler.fit_transform(X_train)
X_val_sc   = scaler.transform(X_val)
X_test_sc  = scaler.transform(X_test)

# Normal-only training data for Layer 1 (kept raw — Isolation Forest is unsupervised)
X_train_normal = X_train_sc[y_bin_train == 0]
print(f'\nNormal-only train : {X_train_normal.shape[0]:,} samples')

n_normal = (y_bin_train == 0).sum()
n_attack = (y_bin_train == 1).sum()
scale_pos_weight = n_normal / n_attack
print(f'scale_pos_weight  : {scale_pos_weight:.2f}')


# =============================================================================
# SMOTE — Over-sample minority attack classes on the TRAINING set only
# =============================================================================
# Applied AFTER scaling so synthetic samples stay in the normalised space.
# Val and Test sets are left untouched to give a realistic evaluation.
# X_train_normal is also unchanged — Layer 1 (IF) is trained on normal only.

print('\nApplying SMOTE to balance minority attack classes in the training set...')

unique_before, counts_before = np.unique(y_multi_train, return_counts=True)
print('Class distribution BEFORE SMOTE (multi-class):')
for cls, cnt in zip(unique_before, counts_before):
    lbl = le.inverse_transform([cls])[0]
    print(f'  Class {cls} ({lbl}): {cnt:,}')

# k_neighbors is capped to min_class_count - 1 to avoid errors on tiny classes
min_class_count = int(counts_before.min())
k_neighbors = max(1, min(5, min_class_count - 1))

smote = SMOTE(random_state=SEED, k_neighbors=k_neighbors)
X_train_sm, y_multi_train_sm = smote.fit_resample(X_train_sc, y_multi_train)

# Re-derive binary labels from the balanced multi-class labels
normal_encoded = le.transform([0])[0]
y_bin_train_sm = (y_multi_train_sm != normal_encoded).astype(int)

unique_after, counts_after = np.unique(y_multi_train_sm, return_counts=True)
print('\nClass distribution AFTER SMOTE (multi-class):')
for cls, cnt in zip(unique_after, counts_after):
    lbl = le.inverse_transform([cls])[0]
    print(f'  Class {cls} ({lbl}): {cnt:,}')

print(f'\nTraining set size: {X_train_sc.shape[0]:,} -> {X_train_sm.shape[0]:,} (after SMOTE)')

# Replace training arrays with the SMOTE-balanced versions
X_train_sc    = X_train_sm
y_bin_train   = y_bin_train_sm
y_multi_train = y_multi_train_sm

# Recompute scale_pos_weight for XGBoost with the balanced set
n_normal_sm  = (y_bin_train == 0).sum()
n_attack_sm  = (y_bin_train == 1).sum()
scale_pos_weight = n_normal_sm / max(n_attack_sm, 1)
print(f'scale_pos_weight (post-SMOTE): {scale_pos_weight:.4f}')


# =============================================================================
# LAYER 1 — ISOLATION FOREST (Pre-Filter)
# =============================================================================
# Trained EXCLUSIVELY on normal data.
# Flags samples with anomaly score > 0.6 for deeper inspection by Layer 2.
# Target: False Positive Rate < 3 % on validation normal data.

print('\nTraining Isolation Forest on normal data only...')

iso_forest = IsolationForest(
    n_estimators=200,
    contamination=0.05,
    max_samples='auto',
    random_state=SEED,
    n_jobs=-1
)
iso_forest.fit(X_train_normal)


def iso_anomaly_score(model, X):
    """Convert Isolation Forest decision_function to [0,1] anomaly score."""
    raw  = model.decision_function(X)   # negative = more anomalous
    norm = (raw - raw.min()) / (raw.max() - raw.min() + 1e-9)
    return 1.0 - norm


iso_score_train = iso_anomaly_score(iso_forest, X_train_sc)
iso_score_val   = iso_anomaly_score(iso_forest, X_val_sc)
iso_score_test  = iso_anomaly_score(iso_forest, X_test_sc)

print('✅ Isolation Forest trained and scores computed.')

# ── Threshold calibration on validation set (target FPR < 3 %) ───────────────
val_normal_mask    = y_bin_val == 0
val_scores_normal  = iso_score_val[val_normal_mask]

thresholds = np.linspace(0.4, 0.95, 200)
fprs       = [(val_scores_normal > t).mean() for t in thresholds]

TARGET_FPR   = 0.03
valid_thresh = [t for t, fpr in zip(thresholds, fprs) if fpr < TARGET_FPR]
IF_THRESHOLD = min(valid_thresh) if valid_thresh else 0.6

achieved_fpr = (val_scores_normal > IF_THRESHOLD).mean()
print(f'Selected IF threshold : {IF_THRESHOLD:.3f}')
print(f'FPR on normal val     : {achieved_fpr*100:.2f}%  (target < 3%)')

l1_flag_val  = (iso_score_val  > IF_THRESHOLD).astype(int)
l1_flag_test = (iso_score_test > IF_THRESHOLD).astype(int)

val_attack_mask = y_bin_val == 1
if val_attack_mask.sum() > 0:
    l1_recall = l1_flag_val[val_attack_mask].mean()
    print(f'Attack recall (val)   : {l1_recall*100:.1f}%')

# ── Visualise Isolation Forest score distributions ─────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

vis_val_normal = iso_score_val[val_normal_mask]
vis_val_attack = iso_score_val[~val_normal_mask]
axes[0].hist(vis_val_normal, bins=100, color='#2ecc71', alpha=0.7, label='Normal')
axes[0].hist(vis_val_attack, bins=100, color='#e74c3c', alpha=0.7, label='Attack')
axes[0].axvline(IF_THRESHOLD, color='black', linestyle='--', label=f'Threshold={IF_THRESHOLD:.3f}')
axes[0].set_title('IF Anomaly Score Distribution (Validation)')
axes[0].set_xlabel('Anomaly Score')
axes[0].set_ylabel('Count')
axes[0].legend()

_ = [axes[1].plot(thresholds, [(vs > t).mean()*100 for vs in [vis_val_normal]],
                  color='#2ecc71', label='FPR (Normal)')]
axes[1].plot(thresholds, [(vis_val_attack > t).mean()*100 for t in thresholds],
             color='#e74c3c', label='TPR (Attack)')
axes[1].axvline(IF_THRESHOLD, color='black', linestyle='--')
axes[1].axhline(TARGET_FPR*100, color='orange', linestyle=':', label=f'FPR target={TARGET_FPR*100:.0f}%')
axes[1].set_title('FPR / TPR vs. Threshold')
axes[1].set_xlabel('Threshold')
axes[1].set_ylabel('%')
axes[1].legend()

plt.tight_layout()
plt.show()


# =============================================================================
# LAYER 2 — XGBOOST CLASSIFIER  (GPU-accelerated)
# =============================================================================
# Trained on ALL labelled training data (post-SMOTE balanced).
# GPU is used via tree_method='hist' + device='cuda' (XGBoost >= 2.0).

print('\nTraining XGBoost (binary classification) ...')
print(f'  device = {XGB_DEVICE}')

xgb_model = xgb.XGBClassifier(
    n_estimators       = 500,
    max_depth          = 7,
    learning_rate      = 0.05,
    subsample          = 0.8,
    colsample_bytree   = 0.8,
    scale_pos_weight   = scale_pos_weight,
    eval_metric        = 'logloss',
    use_label_encoder  = False,
    random_state       = SEED,
    tree_method        = XGB_TREE_METHOD,
    device             = XGB_DEVICE,
    early_stopping_rounds = 30,
    verbosity          = 0,
)

xgb_model.fit(
    X_train_sc, y_bin_train,
    eval_set=[(X_val_sc, y_bin_val)],
    verbose=False,
)

# Predictions on validation set
xgb_prob_val  = xgb_model.predict_proba(X_val_sc)[:, 1]
xgb_pred_val  = (xgb_prob_val > 0.5).astype(int)
xgb_prob_test = xgb_model.predict_proba(X_test_sc)[:, 1]
xgb_pred_test = (xgb_prob_test > 0.5).astype(int)

print(f'✅ XGBoost trained.  Best iteration: {xgb_model.best_iteration}')

# ── Threshold optimisation: maximise F1 on validation ─────────────────────────
thresholds_xgb = np.linspace(0.3, 0.9, 100)
f1_scores_xgb  = [f1_score(y_bin_val, (xgb_prob_val > t).astype(int)) for t in thresholds_xgb]

XGB_THRESHOLD = thresholds_xgb[np.argmax(f1_scores_xgb)]
xgb_pred_val_opt  = (xgb_prob_val  > XGB_THRESHOLD).astype(int)
xgb_pred_test_opt = (xgb_prob_test > XGB_THRESHOLD).astype(int)

print(f'Optimal XGB threshold (max F1): {XGB_THRESHOLD:.3f}')
print(f'Val  F1 @ optimal threshold   : {f1_score(y_bin_val,  xgb_pred_val_opt):.4f}')
print(f'Test F1 @ optimal threshold   : {f1_score(y_bin_test, xgb_pred_test_opt):.4f}')
print(f'Test ROC-AUC                  : {roc_auc_score(y_bin_test, xgb_prob_test):.4f}')

print('\nXGBoost Classification Report (Test, optimised threshold):')
print(classification_report(y_bin_test, xgb_pred_test_opt, target_names=['Normal','Attack']))

# ── Confusion matrix ──────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(6, 5))
ConfusionMatrixDisplay.from_predictions(y_bin_test, xgb_pred_test_opt,
                                        display_labels=['Normal','Attack'],
                                        cmap='Blues', ax=ax)
ax.set_title('XGBoost Confusion Matrix (Test)')
plt.tight_layout()
plt.show()


# =============================================================================
# LAYER 2b — SHAP EXPLAINABILITY
# =============================================================================
print('\nComputing SHAP values for XGBoost ...')

explainer    = shap.TreeExplainer(xgb_model)
# Use a sample to keep computation tractable for a large dataset
SHAP_SAMPLE  = min(5000, X_test_sc.shape[0])
X_shap       = X_test_sc[:SHAP_SAMPLE]
shap_values  = explainer.shap_values(X_shap)

plt.figure(figsize=(10, 7))
shap.summary_plot(shap_values, X_shap, feature_names=feature_cols,
                  max_display=20, show=False)
plt.title('SHAP Summary — Top 20 Features (XGBoost)')
plt.tight_layout()
plt.show()


# =============================================================================
# LAYER 3 — LSTM (Temporal Sequence Validation)  — GPU-accelerated
# =============================================================================
# Applied to samples flagged by Layers 1+2 for temporal validation.
# GPU is used automatically by TensorFlow when a CUDA device is available.
# Using Bidirectional LSTM for richer temporal context.

SEQ_LEN    = 30    # 3 seconds at 10 Hz
N_FEATURES = X_train_sc.shape[1]

def make_sequences(X, y, seq_len=SEQ_LEN):
    """Slide a window of length seq_len over X, return (X_seq, y_seq)."""
    Xs, ys = [], []
    for i in range(len(X) - seq_len):
        Xs.append(X[i:i + seq_len])
        ys.append(y[i + seq_len])
    return np.array(Xs, dtype=np.float32), np.array(ys)


print(f'\nBuilding LSTM sequences (window={SEQ_LEN} steps) ...')
X_train_seq, y_train_seq = make_sequences(X_train_sc, y_multi_train)
X_val_seq,   y_val_seq   = make_sequences(X_val_sc,   y_multi_val)
X_test_seq,  y_test_seq  = make_sequences(X_test_sc,  y_multi_test)

y_train_cat = to_categorical(y_train_seq, num_classes=n_classes)
y_val_cat   = to_categorical(y_val_seq,   num_classes=n_classes)

print(f'Train sequences : {X_train_seq.shape}')
print(f'Val   sequences : {X_val_seq.shape}')
print(f'Test  sequences : {X_test_seq.shape}')

# ── Model definition — GPU-compatible ─────────────────────────────────────────
# TF/Keras uses the GPU automatically; no code change needed beyond the
# set_memory_growth call at the top.

def build_lstm(n_features, n_classes, seq_len=SEQ_LEN):
    inp = Input(shape=(seq_len, n_features), name='input')
    x   = Bidirectional(LSTM(128, return_sequences=True))(inp)
    x   = BatchNormalization()(x)
    x   = Dropout(0.3)(x)
    x   = Bidirectional(LSTM(64))(x)
    x   = BatchNormalization()(x)
    x   = Dropout(0.3)(x)
    x   = Dense(64, activation='relu')(x)
    x   = Dropout(0.2)(x)
    out = Dense(n_classes, activation='softmax', name='output')(x)
    model = Model(inp, out)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
        loss='categorical_crossentropy',
        metrics=['accuracy']
    )
    return model


lstm_model = build_lstm(N_FEATURES, n_classes)
lstm_model.summary()

callbacks = [
    EarlyStopping(monitor='val_loss', patience=7, restore_best_weights=True),
    ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3, min_lr=1e-5),
]

print('\nTraining LSTM ...')
history = lstm_model.fit(
    X_train_seq, y_train_cat,
    validation_data=(X_val_seq, y_val_cat),
    epochs=50,
    batch_size=512,    # larger batch = better GPU utilisation
    callbacks=callbacks,
    verbose=1,
)

# ── Training curves ───────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
axes[0].plot(history.history['loss'],     label='train')
axes[0].plot(history.history['val_loss'], label='val')
axes[0].set_title('LSTM — Loss')
axes[0].set_xlabel('Epoch')
axes[0].legend()

axes[1].plot(history.history['accuracy'],     label='train')
axes[1].plot(history.history['val_accuracy'], label='val')
axes[1].set_title('LSTM — Accuracy')
axes[1].set_xlabel('Epoch')
axes[1].legend()

plt.tight_layout()
plt.show()

# ── Evaluation ────────────────────────────────────────────────────────────────
lstm_probs = lstm_model.predict(X_test_seq, batch_size=512)
lstm_preds = np.argmax(lstm_probs, axis=1)

# Map back to binary
y_test_bin_seq = (y_test_seq != normal_encoded).astype(int)
lstm_preds_bin = (lstm_preds  != normal_encoded).astype(int)

lstm_f1  = f1_score(y_test_bin_seq, lstm_preds_bin)
lstm_auc = roc_auc_score(y_test_bin_seq, 1.0 - lstm_probs[:, normal_encoded])

print(f'\nLSTM Test Binary F1   : {lstm_f1:.4f}')
print(f'LSTM Test ROC-AUC     : {lstm_auc:.4f}')
print('\nLSTM Classification Report (Test, binary):')
print(classification_report(y_test_bin_seq, lstm_preds_bin, target_names=['Normal','Attack']))

# Multi-class report
print('\nLSTM Multi-class Classification Report (Test):')
target_names_mc = [str(c) for c in le.classes_]
print(classification_report(y_test_seq, lstm_preds, target_names=target_names_mc))


# =============================================================================
# ENSEMBLE DECISION FUSION
# =============================================================================
# Layer 1 (IF)     → binary flag (0/1)
# Layer 2 (XGBoost)→ probability [0,1]
# Layer 3 (LSTM)   → probability [0,1]
#
# Final alarm = majority vote: at least 2 of 3 layers must flag an anomaly.

print('\n─── Ensemble Fusion ───')

# Align lengths: LSTM sequences are (N - SEQ_LEN) rows
N_seq = X_test_seq.shape[0]

l1_test_aligned   = l1_flag_test[SEQ_LEN:]          # Layer 1 (IF flag)
xgb_pred_aligned  = xgb_pred_test_opt[SEQ_LEN:]     # Layer 2 (XGB, optimised thresh)
lstm_bin_aligned   = lstm_preds_bin                  # Layer 3
y_true_aligned     = y_test_bin_seq                  # Ground truth

# Majority vote (≥ 2 of 3)
vote_sum       = l1_test_aligned + xgb_pred_aligned + lstm_bin_aligned
ensemble_preds = (vote_sum >= 2).astype(int)

ens_f1  = f1_score(y_true_aligned, ensemble_preds)
ens_auc = roc_auc_score(y_true_aligned,
                         (l1_test_aligned * 0.3 +
                          xgb_pred_aligned * 0.4 +
                          lstm_bin_aligned * 0.3))

print(f'Ensemble Binary F1   : {ens_f1:.4f}')
print(f'Ensemble ROC-AUC     : {ens_auc:.4f}')

fpr_ens = ((ensemble_preds == 1) & (y_true_aligned == 0)).sum() / (y_true_aligned == 0).sum()
print(f'Ensemble FPR         : {fpr_ens*100:.2f}%  (target < 3%)')

print('\nEnsemble Classification Report (Test):')
print(classification_report(y_true_aligned, ensemble_preds, target_names=['Normal','Attack']))

# ── Layer-by-layer summary ────────────────────────────────────────────────────
print('\n─── Layer-by-Layer Summary (Test) ───')
print(f'  Layer 1 (IF)      F1 = {f1_score(y_true_aligned, l1_test_aligned):.4f}')
print(f'  Layer 2 (XGBoost) F1 = {f1_score(y_true_aligned, xgb_pred_aligned):.4f}')
print(f'  Layer 3 (LSTM)    F1 = {f1_score(y_true_aligned, lstm_bin_aligned):.4f}')
print(f'  Ensemble          F1 = {ens_f1:.4f}')

# ── ROC curve comparison ──────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 6))

for label, scores in [
    ('Isolation Forest',   iso_score_test[SEQ_LEN:]),
    ('XGBoost',            xgb_prob_test[SEQ_LEN:]),
    ('LSTM',               1.0 - lstm_probs[:, normal_encoded]),
    ('Ensemble (weighted)',
     l1_test_aligned * 0.3 + xgb_pred_aligned * 0.4 + lstm_bin_aligned * 0.3),
]:
    fpr_arr, tpr_arr, _ = roc_curve(y_true_aligned, scores)
    auc_val = roc_auc_score(y_true_aligned, scores)
    ax.plot(fpr_arr, tpr_arr, label=f'{label} (AUC={auc_val:.3f})')

ax.plot([0, 1], [0, 1], 'k--', linewidth=0.8)
ax.set_xlabel('False Positive Rate')
ax.set_ylabel('True Positive Rate')
ax.set_title('ROC Curve — All Layers vs. Ensemble')
ax.legend(loc='lower right')
plt.tight_layout()
plt.show()

print('\n✅ Pipeline complete.')


# =============================================================================
# MODEL SAVING — All layers + ensemble stacked model saved as joblib
# =============================================================================
import joblib
from pathlib import Path

MODELS_DIR = Path('models')
MODELS_DIR.mkdir(exist_ok=True)

print('\n' + '=' * 60)
print('SAVING MODELS')
print('=' * 60)

# ── Layer 1: Isolation Forest ─────────────────────────────────────────────────
IF_PATH = MODELS_DIR / 'layer1_isolation_forest.joblib'
joblib.dump(iso_forest, IF_PATH, compress=3)
print(f'[Layer 1] Isolation Forest → {IF_PATH}')

# ── Layer 2: XGBoost ──────────────────────────────────────────────────────────
XGB_PATH = MODELS_DIR / 'layer2_xgboost.joblib'
joblib.dump(xgb_model, XGB_PATH, compress=3)
print(f'[Layer 2] XGBoost         → {XGB_PATH}')

# ── Layer 3: LSTM (Keras SavedModel + slim joblib wrapper) ───────────────────
LSTM_DIR  = MODELS_DIR / 'layer3_lstm_savedmodel'
lstm_model.save(str(LSTM_DIR))   # TF SavedModel format (loadable with tf.keras.models.load_model)
print(f'[Layer 3] LSTM SavedModel → {LSTM_DIR}')

# ── Preprocessing artefacts ───────────────────────────────────────────────────
SCALER_PATH = MODELS_DIR / 'scaler.joblib'
joblib.dump(scaler, SCALER_PATH, compress=3)
print(f'[Prep]    RobustScaler    → {SCALER_PATH}')

LE_PATH = MODELS_DIR / 'label_encoder.joblib'
joblib.dump(le, LE_PATH, compress=3)
print(f'[Prep]    LabelEncoder    → {LE_PATH}')

# ── Feature / threshold config ────────────────────────────────────────────────
FEAT_CONFIG = {
    'feature_cols'         : feature_cols,
    'sensor_cols'          : sensor_cols,
    'n_classes'            : n_classes,
    'normal_encoded'       : int(normal_encoded),
    'SEQ_LEN'              : SEQ_LEN,
    'EXPECTED_DT'          : EXPECTED_DT,
    'SAMPLE_RATE_HZ'       : SAMPLE_RATE_HZ,
    'IF_THRESHOLD'         : float(IF_THRESHOLD),
    'XGB_THRESHOLD'        : float(XGB_THRESHOLD),
    'scale_pos_weight'     : float(scale_pos_weight),
    # Attack ID → human-readable name mapping (for the dashboard)
    'attack_names'         : {
        0: 'Normal',           1: 'Reconnaissance',   2: 'Replay Attack',
        3: 'pH Manipulation',  4: 'Slow Ramp',         5: 'Pump Failure',
        6: 'Valve Manipulation', 7: 'Multi-Stage',     8: 'Sensor Spoofing',
        9: 'DoS Attack',       10: 'Covert Channel',
    },
    # Rolling-window params used in feature engineering
    'ROLLING_WINDOW'       : 20,
    'LAG_STEPS'            : [5, 10, 30],
    'LAG_COLS'             : ['LIT_101', 'AIT_202', 'FIT_101', 'DPIT_301', 'PIT_501'],
    # dt stats for temporal features
    'dt_mean'              : float(dt_mean),
    'dt_std'               : float(dt_std),
    # Ensemble weights (Layer1 × 0.3 + Layer2 × 0.4 + Layer3 × 0.3)
    'ensemble_weights'     : [0.3, 0.4, 0.3],
    # Baseline stats for each sensor (used in anomaly scoring by the inference server)
    'sensor_baselines'     : {
        c: {'mean': float(df[c].mean()), 'std': float(df[c].std() + 1e-9)}
        for c in sensor_cols if c in df.columns
    },
}

FEAT_PATH = MODELS_DIR / 'feature_config.joblib'
joblib.dump(FEAT_CONFIG, FEAT_PATH, compress=3)
print(f'[Config]  Feature config  → {FEAT_PATH}')


# ── Full stacked ensemble wrapper class ───────────────────────────────────────
class SWaTEnsembleModel:
    """
    Self-contained 3-layer ensemble model for SWaT anomaly detection.

    Usage
    -----
    Load from disk after training:
        ens = SWaTEnsembleModel.load('models/')

    Inference on a single scaled, feature-engineered sample (1-D numpy array):
        result = ens.predict_sample(x_scaled)
        # returns dict with keys: is_attack, attack_prob, layer1_score,
        #   layer2_prob, xgb_label, lstm_label, verdict

    Inference on a batch (N × n_features numpy array, already scaled):
        result = ens.predict_batch(X_scaled)
    """

    def __init__(self, iso_forest, xgb_model, lstm_path: str,
                 scaler, le, config: dict):
        self.iso_forest   = iso_forest
        self.xgb_model    = xgb_model
        self.lstm_path    = lstm_path      # path to TF SavedModel directory
        self._lstm        = None           # lazy-loaded
        self.scaler       = scaler
        self.le           = le
        self.config       = config
        self._lstm_buffer = []             # rolling buffer for LSTM sequences

    # ── LSTM lazy-load (avoids TF import at pickle time) ──────────────────────
    @property
    def lstm(self):
        if self._lstm is None:
            import tensorflow as tf
            self._lstm = tf.keras.models.load_model(self.lstm_path)
        return self._lstm

    # ── Internal: anomaly score from IF ───────────────────────────────────────
    @staticmethod
    def _if_score(model, X):
        raw  = model.decision_function(X)
        norm = (raw - raw.min()) / (raw.max() - raw.min() + 1e-9)
        return 1.0 - norm

    # ── Single sample inference (used by real-time server) ────────────────────
    def predict_sample(self, x_scaled: 'np.ndarray') -> dict:
        """
        Parameters
        ----------
        x_scaled : 1-D numpy array of shape (n_features,), already RobustScaled.

        Returns
        -------
        dict with inference results for this single time-step.
        """
        import numpy as np
        cfg = self.config
        x2d = x_scaled.reshape(1, -1)

        # Layer 1 — Isolation Forest
        raw_if    = self.iso_forest.decision_function(x2d)[0]
        l1_score  = float(np.clip(1.0 - (raw_if + 0.5), 0, 1))  # rough normalisation
        l1_flag   = int(l1_score > cfg['IF_THRESHOLD'])

        # Layer 2 — XGBoost
        l2_prob   = float(self.xgb_model.predict_proba(x2d)[0, 1])
        l2_flag   = int(l2_prob > cfg['XGB_THRESHOLD'])

        # Layer 3 — LSTM (need SEQ_LEN samples in buffer)
        self._lstm_buffer.append(x_scaled)
        if len(self._lstm_buffer) > cfg['SEQ_LEN']:
            self._lstm_buffer.pop(0)

        l3_prob  = 0.0
        l3_flag  = 0
        lstm_cls = cfg['normal_encoded']
        if len(self._lstm_buffer) == cfg['SEQ_LEN']:
            import numpy as np
            seq     = np.array(self._lstm_buffer, dtype=np.float32)[np.newaxis]
            probs   = self.lstm.predict(seq, verbose=0)[0]  # (n_classes,)
            l3_prob = float(1.0 - probs[cfg['normal_encoded']])
            lstm_cls = int(np.argmax(probs))
            l3_flag = int(lstm_cls != cfg['normal_encoded'])

        # Majority vote (≥ 2 of 3)
        vote_sum    = l1_flag + l2_flag + l3_flag
        is_attack   = bool(vote_sum >= 2)
        attack_prob = float(l1_score * 0.3 + l2_prob * 0.4 + l3_prob * 0.3)

        # Attack type from LSTM (most informative for multi-class)
        attack_id   = int(self.le.inverse_transform([lstm_cls])[0])
        attack_name = cfg['attack_names'].get(attack_id, f'Attack {attack_id}')

        return {
            'is_attack'   : is_attack,
            'attack_prob' : round(attack_prob, 4),
            'layer1_score': round(l1_score, 4),
            'layer1_flag' : l1_flag,
            'layer2_prob' : round(l2_prob, 4),
            'layer2_flag' : l2_flag,
            'layer3_prob' : round(l3_prob, 4),
            'layer3_flag' : l3_flag,
            'vote_sum'    : vote_sum,
            'attack_id'   : attack_id,
            'attack_name' : attack_name if is_attack else 'Normal',
            'verdict'     : 'ATTACK' if is_attack else 'NORMAL',
        }

    # ── Batch inference ───────────────────────────────────────────────────────
    def predict_batch(self, X_scaled: 'np.ndarray') -> dict:
        import numpy as np
        cfg = self.config
        N   = len(X_scaled)

        # Layer 1
        raw     = self.iso_forest.decision_function(X_scaled)
        l1_sc   = 1.0 - (raw - raw.min()) / (raw.max() - raw.min() + 1e-9)
        l1_flag = (l1_sc > cfg['IF_THRESHOLD']).astype(int)

        # Layer 2
        l2_prob = self.xgb_model.predict_proba(X_scaled)[:, 1]
        l2_flag = (l2_prob > cfg['XGB_THRESHOLD']).astype(int)

        # Layer 3 — sequences
        SL = cfg['SEQ_LEN']
        l3_prob = np.zeros(N)
        l3_flag = np.zeros(N, dtype=int)
        if N >= SL:
            seqs = np.array([X_scaled[i:i+SL] for i in range(N - SL)], dtype=np.float32)
            probs = self.lstm.predict(seqs, batch_size=512, verbose=0)
            l3p   = 1.0 - probs[:, cfg['normal_encoded']]
            l3_prob[SL:] = l3p
            l3_flag[SL:] = (l3p > 0.5).astype(int)

        vote_sum  = l1_flag + l2_flag + l3_flag
        ens_pred  = (vote_sum >= 2).astype(int)
        ens_prob  = l1_sc * 0.3 + l2_prob * 0.4 + l3_prob * 0.3

        return {
            'is_attack'   : ens_pred,
            'attack_prob' : ens_prob,
            'layer1_score': l1_sc,
            'layer2_prob' : l2_prob,
            'layer3_prob' : l3_prob,
            'vote_sum'    : vote_sum,
        }

    # ── Serialise / deserialise ───────────────────────────────────────────────
    def save(self, models_dir: str = 'models') -> None:
        import joblib
        from pathlib import Path
        p = Path(models_dir)
        p.mkdir(exist_ok=True)
        # Save lightweight wrapper (excludes LSTM weights — loaded lazily)
        _lstm_bak, self._lstm = self._lstm, None
        joblib.dump(self, p / 'ensemble_model.joblib', compress=3)
        self._lstm = _lstm_bak
        print(f'[Ensemble] Stacked model → {p / "ensemble_model.joblib"}')

    @staticmethod
    def load(models_dir: str = 'models') -> 'SWaTEnsembleModel':
        import joblib
        return joblib.load(Path(models_dir) / 'ensemble_model.joblib')


# ── Instantiate and save the full ensemble ────────────────────────────────────
ensemble = SWaTEnsembleModel(
    iso_forest  = iso_forest,
    xgb_model   = xgb_model,
    lstm_path   = str(LSTM_DIR),
    scaler      = scaler,
    le          = le,
    config      = FEAT_CONFIG,
)
ensemble.save(str(MODELS_DIR))

print('\n' + '=' * 60)
print('ALL MODELS SAVED:')
for p in sorted(MODELS_DIR.rglob('*')):
    if p.is_file():
        sz = p.stat().st_size / 1024
        print(f'  {p.relative_to(MODELS_DIR)}  ({sz:.1f} KB)')
print('=' * 60)
print('\n✅ Pipeline + model saving complete.')
