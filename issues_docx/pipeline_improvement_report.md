# SWaT Redesigned Pipeline — Audit & Improvement Report
### File: `swat_redesigned_pipeline.ipynb` (34 cells)
### Reviewed: 2026-04-15

---

## Executive Summary

The pipeline is **architecturally sound** — chunked loading, RobustScaler on normal-only data, chronological split, Focal Loss, custom attention, and majority-vote ensemble are all correct choices. The notebook has no fatal bugs. However, there are **18 concrete improvements** split into:

- **5 Critical fixes** — likely causing silent accuracy loss right now
- **7 High-impact upgrades** — expected +3–10% F1
- **6 Medium improvements** — robustness and production-readiness

---

## Part 1 — Critical Fixes (Do These First)

### C-1 — `normal_mask` Never Isolates Normal Rows

**Where:** Cell 12 (Split & Scaling)

**Problem:** The scaler is fitted on `X_nor[:int(N_nor*TRAIN_FRAC)]` which is correct. But `y_bin_atk` is derived from `df_attack["ATTACK_ID"] > 0`, meaning the 115,621 `ATTACK_ID=0` rows in the attack CSV are labelled **Normal** and mixed into `X_train_sc` without separation. When IF trains on `X_nor_train_sc` (from the separate normal CSV), that is correct — but the XGB/CNN train split at `X_atk[:n_train]` includes normal rows from the attack CSV mixed chronologically with attack rows. This means the training set is implicitly imbalanced in an unexpected way.

**Fix:**
```python
# After loading df_attack, separate normal from attack
df_atk_only = df_attack[df_attack["ATTACK_ID"] > 0].reset_index(drop=True)
df_nor_from_atk = df_attack[df_attack["ATTACK_ID"] == 0].reset_index(drop=True)

# Append normal rows from attack CSV to df_normal
df_normal = pd.concat([df_normal, df_nor_from_atk], ignore_index=True)
df_normal = df_normal.sort_values("Timestamp").reset_index(drop=True)
```

**Expected impact:** Cleaner class boundary for XGBoost and CNN-BiLSTM; reduces false negatives on normal rows that look like mild attacks.

---

### C-2 — `ATTACK_ID → attack_type` Mapping Missing

**Where:** Cell 8 (loading) — confirmed MISSING from entire notebook

**Problem:** There is no string `attack_type` column. The `ATTACK_NAME` column exists but is never used. Per the data validation report, ATTACK_ID values are: `{0:Normal, 8:TankOverflow, 9:ValveManip, 10:Recon, 11:pHManip, 12:MembrDamage, 13:ChemDepletion, 14:SlowRamp, 15:Replay, 16:DoS}`. Without per-type labels, you cannot:
- Compute per-attack-type F1 scores
- Apply attack-specific SMOTE strategies
- Debug which attack class the model misses

**Fix:** Add immediately after `load_dataset`:
```python
ATTACK_TYPE_MAP = {
    0: "normal",       8: "tank_overflow",   9: "valve_manipulation",
    10: "reconnaissance", 11: "ph_manipulation", 12: "membrane_damage",
    13: "chemical_depletion", 14: "slow_ramp", 15: "replay", 16: "dos_flood"
}
df_attack["attack_type"] = df_attack["ATTACK_ID"].map(ATTACK_TYPE_MAP)
```

**Expected impact:** Enables per-class reporting, targeted SMOTE, and attack-type confusion matrix — essential for ICS safety validation.

---

### C-3 — `Chlorine_Residual` Used Raw as Feature (Silent Poison)

**Where:** Cell 10 (feature engineering) — `Chlorine_Residual` is in `sensor_cols` and gets `_rm`, `_rs`, `_rz`, `_roc` engineered on it

**Problem:** Per the data validation report, `Chlorine_Residual < 2.0 mg/L` (register < 20) for **75% of all rows** — including large fractions of non-attack periods because Chemical Depletion attacks drain the Chlorine_Tank before normal recording resumes. The rolling mean/std of this column is therefore nearly constant near 0 across all attack types, making it a **zero-discriminating feature** that adds noise.

**Fix:**
```python
# Replace raw Chlorine_Residual features with tank-level rate-of-change
if "Chlorine_Residual" in df.columns:
    df["cl_res_roc"] = df["Chlorine_Residual"].diff().fillna(0).astype(np.float32)
if "Chlorine_Tank_Level" in df.columns:
    df["cl_tank_drain_rate"] = df["Chlorine_Tank_Level"].diff().fillna(0).astype(np.float32)
    # Strong signal: all 4 tanks draining simultaneously = Chemical Depletion
    df["all_tanks_drain"] = ((df["Acid_Tank_Level"].diff() < -0.03) &
                              (df["Chlorine_Tank_Level"].diff() < -0.03) &
                              (df["Coagulant_Tank_Level"].diff() < -0.03)).astype(np.int8)
```

**Expected impact:** Eliminates noise feature; adds `all_tanks_drain` which is a near-perfect Chemical Depletion signature (should give +2–4% F1 on that class).

---

### C-4 — SMOTE Applied to Multi-class Before Binarisation (Wrong Label Space)

**Where:** Cell 16 (SMOTE)

**Problem:** SMOTE is applied on `y_sm_multi` (multi-class: 10 classes). Then XGBoost is trained with `multi:softprob`. The `normal_encoded` hack converts multi-class probabilities to binary by `1 - proba[normal_encoded]`. This is correct, but the SMOTE is balancing across all 10 sub-classes equally — meaning rare ATTACK_ID=15 (Replay, 3.4%) gets severely oversampled to match ATTACK_ID=16 (16.7%), which distorts the feature space for Replay (it has near-zero variance per the validation report when sensors are frozen).

**Fix:** Use `SMOTEENN` (combined over+under-sampling) instead of vanilla SMOTE, and set a minimum minority threshold rather than full balance:
```python
from imblearn.combine import SMOTEENN
from imblearn.over_sampling import BorderlineSMOTE

# BorderlineSMOTE: only synthesises near the decision boundary (safer for replay)
smote = BorderlineSMOTE(
    random_state=SEED,
    k_neighbors=min(5, int(counts_c.min())-1),
    kind="borderline-1"
)
```

**Expected impact:** Prevents nonsensical synthetic Replay samples (when all sensors should be frozen, new SMOTE points will have artificial variation). Better generalisation for minority classes.

---

### C-5 — XGB Threshold Fixed at 0.70 (Too Conservative)

**Where:** Cell 6 (config) `XGB_THRESHOLD = 0.70`

**Problem:** Unlike IF (which calibrates threshold to FPR < 3%), XGB uses a hardcoded 0.70. For a multi-class `softprob` output converted to binary (`1 - P(normal)`), the effective operating point depends entirely on the class distribution — there is no guarantee 0.70 is optimal. If the true optimal is 0.50–0.55, you lose substantial recall on slow/subtle attacks.

**Fix:** Calibrate XGB threshold the same way IF does — on validation set, maximising F1:
```python
from sklearn.metrics import f1_score
thresholds = np.linspace(0.30, 0.90, 300)
f1s = [f1_score(y_bin_val, (xgb_prob_val > t).astype(int)) for t in thresholds]
XGB_THRESHOLD = float(thresholds[np.argmax(f1s)])
print(f"Optimal XGB threshold (max val F1): {XGB_THRESHOLD:.3f}")
```

**Expected impact:** Direct +1–5% F1 depending on current suboptimality of 0.70.

---

## Part 2 — High-Impact Upgrades

### H-1 — `SEQ_LEN = 30` (3 s) Too Short for Slow Ramp Detection

**Where:** Cell 6 config

**Problem:** The logic doc states the Slow Ramp attack moves at 0.007 pH/s. Over 3 seconds (30 steps), pH moves only `3 × 0.007 = 0.021` — well within noise. The LSTM window captures no accumulation. The doc explicitly says "only temporal accumulation over 30+ samples reveals the trend" — but that is 30 **seconds** (300 steps at 10 Hz), not 30 steps.

**Fix:**
```python
SEQ_LEN = 150   # 15 s at 10 Hz — captures slow ramp trend
BATCH_SIZE = 32  # reduce from 64 to stay within GT 730 VRAM (150×184×32×4 = ~3.5 MB/batch)
```

Or alternatively, add a **stride-based downsampling** to keep memory feasible:
```python
SEQ_LEN  = 100    # 100 steps, stride=2 → effective 20 s window
STRIDE   = 2      # in LSTMSequenceGenerator, step by 2 not 1
```

**Expected impact:** Slow Ramp F1 likely to increase significantly (currently near-undetectable at 3 s). At least +5% overall F1 if Slow Ramp is currently missed.

---

### H-2 — Roll Window `ROLL_W = 20` (2 s) Too Narrow for Duty-Cycle Features

**Where:** Cell 6 config + Cell 10 feature engineering

**Problem:** The logic doc says P_203 duty cycle should be measured over **60 seconds (600 rows)** and P_403 over **30 seconds (300 rows)** to discriminate attacks. Current `ROLL_W = 20` (2 s) is too narrow to capture duty-cycle anomalies — it measures instantaneous state not sustained pattern.

**Fix:** Add multi-window rolling features for the critical actuator columns:
```python
# Add to engineer_features(), Group 3:
for pump, w in [("P_203", 600), ("P_403", 300), ("P_101", 200), ("P_301", 200)]:
    if pump in df.columns:
        df[f"{pump}_duty{w}"] = df[pump].rolling(w, min_periods=1).mean().astype(np.float32)

# Also add the key logic-doc-specified discriminators:
if "P_203" in df.columns:
    df["p203_duty_60s"]  = df["P_203"].rolling(600, min_periods=1).mean().astype(np.float32)
if "P_403" in df.columns:
    df["p403_duty_30s"]  = df["P_403"].rolling(300, min_periods=1).mean().astype(np.float32)
```

**Expected impact:** P_203 duty rising from 46% → 73% is the strongest Slow Ramp/pH discriminator per the logic doc. Missing this means L2/L3 cannot distinguish it. Estimated +3–5% F1.

---

### H-3 — `LAG_COLS` Missing Critical Attack-Specific Sensors

**Where:** Cell 6 config: `LAG_COLS = ["LIT_101","AIT_202","FIT_101","DPIT_301","PIT_501"]`

**Problem:** Missing lags for:
- `UF_Backwash_Active` — key for Membrane Damage (DPIT rises without backwash)
- `UF_Fouling_Factor` — monotonic rise is Membrane Damage signature
- `Acid_Tank_Level`, `Chlorine_Tank_Level` — depletion rate for Chemical attack
- `MV_101`, `MV_301` — valve state transitions for Valve Manipulation

**Fix:**
```python
LAG_COLS = [
    "LIT_101", "AIT_202", "FIT_101", "DPIT_301", "PIT_501",
    # New additions:
    "UF_Fouling_Factor", "UF_Backwash_Active", "UF_Last_Backwash",
    "Acid_Tank_Level", "Chlorine_Tank_Level", "Bisulfate_Tank_Level",
    "MV_101", "MV_301", "AIT_402",
]
LAG_STEPS = [1, 5, 10, 30, 100]  # add 1 (1-step lag = adjacent state) and 100 (10s lookback)
```

**Expected impact:** Membrane Damage and Chemical Depletion F1 should improve by 5–10% as the model can now see the accumulation trend in lagged features.

---

### H-4 — Missing MITRE-Aligned "Physics Inconsistency" Features

**Where:** Cell 10 (feature engineering Group 3)

**Problem:** The logic doc's Section 9 explicitly lists the exact sensor combinations that define each attack as "physically impossible" in normal operation. These are the strongest ML features and most are not in the notebook:

**Fix:** Add these binary inconsistency flags:
```python
# Valve Manipulation signature (Section 9.6)
if "P_101" in df.columns and "FIT_101" in df.columns:
    df["pump_on_zero_flow"] = ((df["P_101"]==1) & (df["FIT_101"] < 0.2)).astype(np.int8)

# Tank Overflow signature (Section 9.5)
if all(c in df.columns for c in ["P_101","P_102","MV_101","LIT_101"]):
    df["overflow_pattern"] = ((df["P_101"]==0) & (df["P_102"]==0) &
                               (df["MV_101"]==1) & (df["LIT_101"] > 700)).astype(np.int8)

# pH manipulation signature (Section 9.3): pH low + acid pump OFF sustained
if "AIT_202" in df.columns and "P_203" in df.columns:
    df["low_ph_no_acid"] = ((df["AIT_202"] < 550) & (df["P_203"] == 0)).astype(np.int8)

# Chemical Depletion: all 4 dosing pumps ON simultaneously (Section 9.8)
pump_cols = ["P_203","P_205","P_206","P_403"]
if all(c in df.columns for c in pump_cols):
    df["all_dosing_on"] = (df[pump_cols].sum(axis=1) == 4).astype(np.int8)

# Membrane Damage: DPIT high + backwash blocked (Section 9.7)
if "DPIT_301" in df.columns and "UF_Backwash_Active" in df.columns:
    df["membrane_attack_sig"] = ((df["DPIT_301"] > 60) & (df["UF_Backwash_Active"]==0)).astype(np.int8)

# Replay signature: rolling std near zero across multiple sensors (Section 9.2)
std_sensors = ["LIT_101","AIT_202","FIT_101","DPIT_301"]
for s in std_sensors:
    if s in df.columns:
        df[f"{s}_rs10"] = df[s].rolling(100, min_periods=10).std().fillna(0).astype(np.float32)
df["multi_frozen"] = ((df[[f"{s}_rs10" for s in std_sensors if f"{s}_rs10" in df.columns]] < 0.5)
                       .all(axis=1)).astype(np.int8)
```

**Expected impact:** These features are hand-designed attack signatures from the physics model. Each is a near-zero false-positive indicator in normal data. Expected +5–12% F1 on specific attack types (especially Replay and Valve Manipulation which currently have no dedicated features).

---

### H-5 — Ensemble Weights Hardcoded (0.20/0.45/0.35) Without Validation

**Where:** Cell 6 config + Cell 28 ensemble fusion

**Problem:** Weights `W_IF=0.20, W_XGB=0.45, W_CNN=0.35` are fixed. If CNN achieves higher AUC than XGB on your actual data, the XGB-heavy weighting is suboptimal. Layer performance is data-dependent.

**Fix:** Learn weights on validation set via constrained optimisation:
```python
from scipy.optimize import minimize

def neg_auc(w):
    w = np.array(w)
    w = np.clip(w, 0, 1)
    w = w / w.sum()
    score = w[0]*if_al_val + w[1]*xgb_prob_val + w[2]*cnn_probs_val
    return -roc_auc_score(y_bin_val, score)

res = minimize(neg_auc, [0.20, 0.45, 0.35],
               method="SLSQP",
               bounds=[(0.05,0.60)]*3,
               constraints={"type":"eq","fun":lambda w: sum(w)-1})
W_IF, W_XGB, W_CNN = res.x
print(f"Optimal weights: IF={W_IF:.3f} XGB={W_XGB:.3f} CNN={W_CNN:.3f}")
```

**Expected impact:** +1–3% AUC on ensemble with negligible compute cost.

---

### H-6 — Per-Attack-Type F1 Report Missing

**Where:** Cell 28/33 (ensemble evaluation)

**Problem:** Only binary (Normal vs Attack) F1 is reported. For ICS safety, you need to know which **attack type** is missed. A model with F1=0.95 binary but F1=0.20 on Replay is dangerously misleading.

**Fix:** Add after ensemble evaluation:
```python
# Per-attack-type evaluation
print("\nPer-Attack-Type F1 (test set)")
print("-" * 45)
for aid, aname in ATTACK_TYPE_MAP.items():
    if aid == 0:
        continue
    mask = (y_bin_test[OFF:OFF+n_cnn] == 1)   # true attacks
    # Narrow to this attack type using ATTACK_ID from df_attack
    # (need to preserve ATTACK_ID through the pipeline — see M-1)
    type_mask = (y_type_test[OFF:OFF+n_cnn] == aid) if "y_type_test" in dir() else None
    if type_mask is not None and type_mask.sum() > 0:
        f1_t = f1_score(y_ens[type_mask], ens_pred[type_mask], zero_division=0)
        print(f"  {aname:<25s}: F1={f1_t:.4f} (n={type_mask.sum():,})")
```

**Expected impact:** Not a metric improvement — but critical for identifying which attack is underperforming. Undetected attack types are a safety failure in ICS.

---

### H-7 — CNN Threshold Fixed at 0.50 with Focal Loss

**Where:** Cell 6 config `CNN_THRESHOLD = 0.50`

**Problem:** Focal Loss with `alpha=0.25` deliberately suppresses easy negatives. The output probability distribution is **not** calibrated to 0.50 = 50% chance of attack. Focal-trained models typically output probabilities clustered near 0 (confident normal) or 1 (confident attack) with very few values near 0.50. Using 0.50 may work but is not the optimal F1 threshold.

**Fix:** Calibrate on validation set (same as IF/XGB):
```python
# After CNN val prediction:
cnn_probs_val = cnn_lstm.predict(val_gen, ...).squeeze()
f1s_cnn = [f1_score(y_val_seq, (cnn_probs_val > t).astype(int)) for t in np.linspace(0.1, 0.9, 200)]
CNN_THRESHOLD = float(np.linspace(0.1, 0.9, 200)[np.argmax(f1s_cnn)])
print(f"Optimal CNN threshold: {CNN_THRESHOLD:.3f}")
```

---

## Part 3 — Medium Improvements

### M-1 — Preserve `ATTACK_ID` Through Arrays for Per-Type Evaluation

**Where:** Cell 12 — only `y_bin_atk` and `y_multi_atk` are extracted; `ATTACK_ID` per-row is lost

```python
# Add this line in Cell 12, alongside y_bin_atk:
y_type_atk = df_attack["ATTACK_ID"].values.astype(np.int32)
y_type_train = y_type_atk[:n_train]
y_type_val   = y_type_atk[n_train:n_train+n_val]
y_type_test  = y_type_atk[n_train+n_val:]
```

---

### M-2 — `LSTMSequenceGenerator` Label Rule Should be `seq_window.any()`, Not `y[i:i+seq_len].any()`

**Where:** Cell 21 `get_all_labels()`:
```python
return np.array([int(self.y[i:i+self.seq_len].any()) for i in range(n)], dtype=np.int8)
```

**Problem:** A window is labelled "attack" if **any** of the 30 steps contains an attack sample. In the early seconds of a Tank Overflow, the first 1–2 steps may be normal (system responding), making the window label "attack" but most features look normal. This creates noisy labels for transition windows.

**Fix:** Require majority vote (>50%) of window to be attack:
```python
# Stricter window label — reduces transition noise
return np.array([int(self.y[i:i+self.seq_len].mean() > 0.5) for i in range(n)], dtype=np.int8)
```

Or alternatively mark the first `SEQ_LEN` rows of each attack segment as "transition" and exclude them from loss computation.

---

### M-3 — `EarlyStopping` Monitors `val_auc` but `ReduceLROnPlateau` Monitors `val_loss`

**Where:** Callbacks in Cell 24

**Problem:** If val_loss improves but val_auc degrades (common with focal loss), `EarlyStopping` stops training while `ReduceLROnPlateau` is still reducing LR. These should monitor the same metric.

**Fix:**
```python
callbacks = [
    ModelCheckpoint(filepath=CKPT, monitor="val_auc", save_best_only=True, mode="max"),
    EarlyStopping(monitor="val_auc", patience=10, restore_best_weights=True, mode="max"),
    ReduceLROnPlateau(monitor="val_auc", factor=0.5, patience=4, min_lr=1e-6, mode="max"),
]
```

Also increase `patience` from 8 → 10–12 since focal loss can have slow initial improvement.

---

### M-4 — `dropout=0.30` Between BiLSTM Layers May Be Too Aggressive for GT 730 Epoch Count

**Where:** Cell 22 model architecture

**Problem:** With only 50 epochs (often stopping earlier via EarlyStopping at patience=8), heavy dropout (0.30 + 0.25 + 0.20) may prevent convergence. Focal loss already reduces easy-sample contribution. Double regularisation can cause underfitting.

**Fix:** Reduce dropout slightly for faster convergence, or increase epochs:
```python
# Reduce dropout
x = Dropout(0.20, name="drop_lstm1")(x)   # was 0.30
x = Dropout(0.15, name="drop_lstm2")(x)   # was 0.25

# Increase max epochs
epochs = 80   # was 50; EarlyStopping will limit actual training
```

---

### M-5 — No Threshold Optimisation for Ensemble Score

**Where:** Cell 28 — ensemble uses majority vote `>= 2` but also computes a weighted score `ens_sc`

**Problem:** The weighted score `ens_sc` is never thresholded optimally — it's only used for AUC computation. If you add a threshold on `ens_sc` optimised for F1, the ensemble F1 could be higher than the majority-vote binary F1.

**Fix:**
```python
# Calibrate ensemble score threshold
ens_thresholds = np.linspace(0.20, 0.80, 300)
ens_f1s = [f1_score(y_ens, (ens_sc > t).astype(int)) for t in ens_thresholds]
ENS_THRESHOLD = float(ens_thresholds[np.argmax(ens_f1s)])
ens_pred_cal = (ens_sc > ENS_THRESHOLD).astype(np.int8)
print(f"Calibrated ensemble F1: {f1_score(y_ens, ens_pred_cal):.4f} @ threshold={ENS_THRESHOLD:.3f}")
print(f"vs Majority vote F1:    {ens_f1:.4f}")
```

---

### M-6 — No Mahalanobis Distance Feature (Recommended in Logic Doc)

**Where:** Feature engineering Cell 10 — missing entirely

**Problem:** The logic doc's Feature Engineering Reference explicitly lists **Mahalanobis distance from normal mean/cov** as a key multi-stage stealth attack detector. This is the strongest multi-variable anomaly score for detecting attacks that look superficially normal on any single sensor.

**Fix:** Compute on a rolling window using the normal-data covariance:
```python
# After scaler is fitted, compute rolling Mahalanobis on val/test
from numpy.linalg import inv

# Fit covariance on normal training data
cov_inv = inv(np.cov(X_nor_train_sc.T) + 1e-6 * np.eye(N_FEATURES))

def mahalanobis_batch(X, mu, cov_inv):
    diff = X - mu
    return np.array([np.sqrt(max(d @ cov_inv @ d, 0)) for d in diff]).astype(np.float32)

mu_normal = X_nor_train_sc.mean(axis=0)
# Compute for train/val/test and add as feature column
mah_train = mahalanobis_batch(X_train_sc, mu_normal, cov_inv)
```

> Note: Full Mahalanobis on 184 features may be slow. Use PCA to reduce to 30 components first if needed for GT 730 memory.

---

## Part 4 — Configuration Quick-Reference

Current values vs recommended:

| Parameter | Current | Recommended | Reason |
|---|---|---|---|
| `SEQ_LEN` | 30 (3 s) | **150 (15 s)** | Slow Ramp needs 10+ s window |
| `BATCH_SIZE` | 64 | **32** (if SEQ_LEN=150) | VRAM constraint |
| `ROLL_W` | 20 (2 s) | **Keep + add 600/300** | P_203/P_403 duty cycle |
| `LAG_STEPS` | [5,10,30] | **[1,5,10,30,100]** | 1-step and 10 s lags |
| `XGB_THRESHOLD` | 0.70 (fixed) | **Calibrate on val** | Max F1 operating point |
| `CNN_THRESHOLD` | 0.50 (fixed) | **Calibrate on val** | Focal output not centred at 0.5 |
| `W_IF/W_XGB/W_CNN` | 0.20/0.45/0.35 | **Optimise on val (SLSQP)** | Data-driven weights |
| `n_estimators` (XGB) | 500 | **Keep** | Good baseline |
| `max_depth` (XGB) | 7 | **Keep** | Not over-deep |
| `EarlyStopping patience` | 8 | **10–12** | Focal loss warms up slowly |
| Dropout LSTM1 | 0.30 | **0.20** | Reduce for faster convergence |
| `SMOTE` | Vanilla | **BorderlineSMOTE** | Avoids frozen-sensor synthesis |
| `SMOTE_CAP` | 200,000 | **Keep** | Memory-safe |

---

## Part 5 — Priority Action Plan

### Immediate (< 1 hour of changes)
1. ✅ **C-2** — Add `ATTACK_TYPE_MAP` and `attack_type` column (5 lines)
2. ✅ **C-5** — Calibrate XGB threshold on validation F1 (10 lines)
3. ✅ **H-7** — Calibrate CNN threshold on validation F1 (10 lines)
4. ✅ **M-3** — Unify callback monitor metric to `val_auc` (2 lines)
5. ✅ **M-5** — Add calibrated ensemble threshold (10 lines)

### Short-term (< 2 hours, most impact)
6. 🔧 **H-2** — Add `p203_duty_60s` and `p403_duty_30s` rolling features
7. 🔧 **H-4** — Add 5 physics-inconsistency binary flag features
8. 🔧 **C-3** — Replace raw `Chlorine_Residual` with rate features + `all_tanks_drain`
9. 🔧 **H-3** — Extend `LAG_COLS` with UF/chemical/valve sensors

### Medium-term (architecture changes, retrain required)
10. 🔄 **H-1** — Increase `SEQ_LEN` to 150; reduce `BATCH_SIZE` to 32
11. 🔄 **C-4** — Switch to `BorderlineSMOTE`
12. 🔄 **H-5** — Optimise ensemble weights with SLSQP
13. 🔄 **H-6** — Add per-attack-type F1 reporting
14. 🔄 **M-1** — Preserve `ATTACK_ID` through train/val/test arrays
15. 🔄 **M-2** — Switch window label to majority-vote rule
16. 🔄 **M-4** — Reduce dropout to 0.20/0.15; increase max epochs to 80
17. 🔄 **M-6** — Add Mahalanobis distance as feature
18. 🔄 **C-1** — Separate ATTACK_ID=0 rows from attack CSV before splitting

---

## Part 6 — Expected Outcome

| Metric | Current (estimated) | After Immediate | After All |
|---|---|---|---|
| Overall binary F1 | Unknown (not run) | +2–4% | +8–15% |
| Slow Ramp F1 | Very low (3 s window) | +2% | +15–25% |
| Replay F1 | Low (no frozen-sensor feature) | +3% | +10–15% |
| Chemical Depletion F1 | Moderate | +5% | +8–12% |
| Ensemble AUC | Unknown | +1–2% | +3–6% |
| False Positive Rate | Unknown (calibrated IF only) | Stable | < 2% |

> All estimates assume a correct run completes. The pipeline has never been run to completion per the notebook (no output cells). Run with `ATTACK_ID=0` as the normal class in attack CSV first to establish baseline.

---

*Report generated from full static analysis of all 34 cells in `swat_redesigned_pipeline.ipynb`.*
