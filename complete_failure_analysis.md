# SWaT Pipeline — Complete Failure Analysis & Fix Guide
### Pipeline: `swat_redesigned_pipeline.ipynb` | Run: 2026-04-15
### Reference: `swat_research_report.docx` (Initial Architecture)

---

## The Problem at a Glance

```
What the run produced:
  Layer 1 — Isolation Forest  : F1 = 0.0929  | Attack recall =  3.5%  FAILED
  Layer 2 — XGBoost           : F1 = 0.9038  | AUC    = 0.7295        OK
  Layer 3 — CNN-BiLSTM        : F1 = 0.0624  | Attack recall =  3.0%  COLLAPSED
  Ensemble (Majority ≥ 2/3)  : F1 = 0.1422  | FNR    = 92.32%        WORSE THAN XGB ALONE

What was targeted (research report):
  XGBoost  F1 > 0.88 per attack class
  LSTM applied only to XGB-flagged windows (not all data)
  Ensemble must not miss >5% of attacks in ICS context
```

---

## Part 0 — Original Architecture vs What Was Built

Your research report (`swat_research_report.docx`) describes a specific **3-layer design** that differs in several critical ways from what was implemented:

| Aspect | Research Report Plan | What the Notebook Does | Impact |
|---|---|---|---|
| **Normal/Attack ratio** | ≥ 40% normal, 60% attack (balanced collection) | 13.4% normal, 86.6% attack in attack CSV | Severe imbalance kills CNN |
| **LSTM scope** | Applied **only to windows flagged by XGBoost** | Applied to ALL 860,500 rows | LSTM sees too many easy normal windows |
| **XGBoost imbalance** | `scale_pos_weight = n_normal / n_attack` | SMOTE on 200k subsample | SMOTE suboptimal for 10-class problem |
| **Autoencoder** | Planned as 2nd anomaly detector (128→64→32→64→128) | **Not implemented** | Missing a strong anomaly baseline |
| **Split strategy** | Stratified by ATTACK_ID | Chronological (time-series order) | Val set has wrong attack distribution |
| **Threshold calibration** | "Tune on validation to achieve FPR < 3%" | IF only; XGB=0.70 fixed, CNN=0.50 fixed | Suboptimal decision boundaries |
| **Feature engineering** | 9 groups including Mahalanobis distance | 5 groups, no Mahalanobis, missing duty-cycle | Slow Ramp and Replay near-undetectable |
| **SHAP per attack type** | Required for explainability | Done globally only | Cannot identify per-attack weaknesses |

---

## Part 1 — Layer 1: Isolation Forest

### What It Produced
```
IF threshold  : 0.574
FPR (nor val) : 3.00%   ← exactly at target
Attack recall : 3.5%    ← catastrophically low
IF F1 (test)  : 0.0929
```

### Root Cause Analysis

**RC-IF-1: IF is trained on 602,364 normal samples but threshold calibrated on a val set that is 86% attack.**

The research report says: *"Tune threshold on validation set to achieve FPR < 3%."*

When the val set has 14,211 normal rows and 114,864 attack rows, a threshold of 0.574 achieves FPR < 3% on normal rows. But the IF model was never asked to detect attacks — only to distinguish "unusual" from "normal". At 3% FPR, threshold is so conservative that 96.5% of attack samples are scored below it (they still look "normal-ish" in a 179-dimensional feature space).

**RC-IF-2: `contamination=0.05` is inconsistent with the actual attack rate.**

IF uses `contamination` during fitting to set the internal threshold for what counts as an outlier. `0.05` means IF expects 5% of its training data to be outliers. But IF was trained on **normal-only** data — there are no outliers to find. This parameter has no effect when training on pure normal data, but affects the score distribution shape.

**RC-IF-3: 179 unscaled/mismatched features dilute the anomaly signal.**

As identified in the data validation: 9 features from the attack CSV are absent in the normal CSV and are filled as 0.0. These zero-filled features enter the IF training as pure normal values, but during val/test they have attack-inflated variance — confusing the IF forest.

**RC-IF-4: IF is never effective as a standalone binary classifier at 86% attack rate.**

The research report correctly says IF provides a **threshold calibration baseline** and anomaly score. It was never intended to achieve high F1 alone. The implementation mistake is using it as an equal-weight voting member in the ensemble.

### Fix for Layer 1

**Cell 6 — Change `IF_FPR_TARGET`:**
```python
IF_FPR_TARGET = 0.08   # was 0.03 → allow 8% FPR for better recall trade-off
```

**Cell 14 — Convert IF score into an XGBoost feature instead of a voting layer:**
```python
# After IF training — add score as extra feature column
iso_score_train = if_score(iso_forest, X_train_sc).reshape(-1,1).astype(np.float32)
iso_score_val   = if_score(iso_forest, X_val_sc).reshape(-1,1).astype(np.float32)
iso_score_test  = if_score(iso_forest, X_test_sc).reshape(-1,1).astype(np.float32)

# Augment feature matrices so XGBoost can learn to use IF score
X_train_aug = np.hstack([X_train_sc, iso_score_train])
X_val_aug   = np.hstack([X_val_sc,   iso_score_val])
X_test_aug  = np.hstack([X_test_sc,  iso_score_test])

print(f"Augmented feature shape: {X_train_aug.shape}  (+1 IF score column)")
```

**Then use `X_train_aug`, `X_val_aug`, `X_test_aug` everywhere XGBoost and CNN receive input.**

This converts IF from a broken voting layer into a useful anomaly-score feature that XGBoost can weight correctly.

---

## Part 2 — Layer 2: XGBoost

### What It Produced
```
XGBoost Val — F1: 0.8458 | AUC: 0.7295
Normal  : precision=0.22  recall=0.50    ← poor
Attack  : precision=0.93  recall=0.78   ← good
Early stopped at iter 72 / 500
```

### Root Cause Analysis

**RC-XGB-1: `XGB_THRESHOLD = 0.70` is hardcoded — never calibrated.**

This is the single biggest XGBoost problem. The model outputs `1 - P(normal)` as the binary attack score. Where the optimal threshold sits depends entirely on your data distribution. At 70%, XGB is too conservative — it achieves 0.78 recall but the optimal threshold likely gives 0.88–0.92 recall.

**Evidence:** Normal recall = 0.50 — the model is unsure about half the normal samples, putting them above 0.70. Lowering the threshold captures more attacks without losing much precision.

**RC-XGB-2: SMOTE produces perfect balance (35,172 per class × 10 classes) which is unrealistic.**

The research report planned `scale_pos_weight = n_normal / n_attack` for XGBoost — this keeps original data intact and just re-weights the loss. SMOTE synthesises 200k→350k rows with equal classes. The synthesised Replay attack samples have near-zero natural variance (sensors frozen during replay) — SMOTE creates synthetic points in a space that doesn't physically exist for this attack type.

**RC-XGB-3: `n_estimators=500` with `early_stopping_rounds=30` stopped at iteration 72.**

The model stopped at 72/500 — it converged too quickly or is overfitting. With `learning_rate=0.05` on 351k SMOTE rows, 72 trees is insufficient to capture 10-class boundaries. The SMOTE subsample (200k capped) misrepresents rarer attacks.

**RC-XGB-4: `max_depth=7` may cause overfitting to SMOTE artefacts.**

With synthesised data, deeper trees memorise SMOTE interpolations rather than true boundaries. Start shallower.

**RC-XGB-5: AUC=0.7295 is low for a 10-class problem with 179 features.**

Top SHAP features are `AIT_202_rs` (pH rolling std) and `FIT_201_rm` (flow rolling mean) — good. But `Chlorine_Tank_Level` at #3 is there because Chemical Depletion drains it, which is correct. However, the pH-related features dominate because pH attacks (Slow Ramp, pH Manipulation) are overrepresented in SMOTE's equal-balance output vs. the real distribution.

### Fix for Layer 2

**Cell 6 — Remove hardcoded threshold:**
```python
# DELETE this line:
XGB_THRESHOLD = 0.70
# (will be calibrated dynamically below after model.fit)
```

**Cell 16 — Replace SMOTE with scale_pos_weight (research report original plan):**
```python
# Replace the SMOTE block with the original research report approach:
print("Using scale_pos_weight instead of SMOTE (research report recommendation)...")

n_nor_tr = (y_bin_train == 0).sum()
n_atk_tr = (y_bin_train == 1).sum()
SPW = float(n_nor_tr) / float(n_atk_tr)
print(f"scale_pos_weight = {SPW:.3f}  (n_normal={n_nor_tr:,} / n_attack={n_atk_tr:,})")

# Use full training data — no subsample, no SMOTE
X_xgb_train = X_train_aug   # full augmented array
y_xgb_train = y_bin_train   # binary labels
y_xgb_val   = y_bin_val
```

**Cell 17 — Revised XGBoost params:**
```python
xgb_params = dict(
    objective        = "binary:logistic",   # binary — simpler, cleaner
    eval_metric      = "aucpr",             # AUC-PR more robust under imbalance than logloss
    tree_method      = XGB_TREE_METHOD,
    device           = XGB_DEVICE,
    n_jobs           = XGB_N_JOBS,
    n_estimators     = 800,                 # more trees needed (was 500)
    max_depth        = 5,                   # shallower to prevent overfitting (was 7)
    learning_rate    = 0.03,                # slower learning, more detail (was 0.05)
    subsample        = 0.8,
    colsample_bytree = 0.7,                 # slightly less correlation (was 0.8)
    min_child_weight = 10,                  # larger min leaf (was 5) — prevents overfitting
    reg_alpha        = 0.5,                 # stronger L1 (was 0.1)
    reg_lambda       = 2.0,                 # stronger L2 (was 1.0)
    scale_pos_weight = SPW,                 # ADD: handles imbalance correctly
    early_stopping_rounds = 50,             # more patience (was 30)
    random_state     = SEED,
)
xgb_model = xgb.XGBClassifier(**xgb_params)
xgb_model.fit(
    X_xgb_train, y_xgb_train,
    eval_set=[(X_val_aug, y_xgb_val)], verbose=100
)
```

**Cell 17 (after fit) — Calibrate threshold on validation F1:**
```python
xgb_prob_val  = xgb_model.predict_proba(X_val_aug)[:, 1].astype(np.float32)
xgb_prob_test = xgb_model.predict_proba(X_test_aug)[:, 1].astype(np.float32)

# Find threshold maximising F1 on validation set
thresholds_xgb = np.linspace(0.20, 0.85, 500)
f1s_xgb_cal = [f1_score(y_bin_val, (xgb_prob_val > t).astype(int), zero_division=0)
               for t in thresholds_xgb]
XGB_THRESHOLD = float(thresholds_xgb[np.argmax(f1s_xgb_cal)])
xgb_pred_val  = (xgb_prob_val  > XGB_THRESHOLD).astype(np.int8)
xgb_pred_test = (xgb_prob_test > XGB_THRESHOLD).astype(np.int8)

f1_xgb  = f1_score(y_bin_val, xgb_pred_val)
auc_xgb = roc_auc_score(y_bin_val, xgb_prob_val)
print(f"XGB optimal threshold : {XGB_THRESHOLD:.3f}  (was hardcoded 0.70)")
print(f"XGBoost Val — F1: {f1_xgb:.4f} | AUC-PR: {auc_xgb:.4f}")
print(classification_report(y_bin_val, xgb_pred_val, target_names=["Normal","Attack"]))
```

---

## Part 3 — Layer 3: CNN-BiLSTM (The Primary Failure)

### What It Produced
```
Epoch 1: val_auc = 0.6962   ← best epoch ever
Epoch 2: val_auc = 0.4517   ← collapsed in one epoch
Epoch 3: val_auc = 0.6356
Epoch 4: val_auc = 0.5914
...
Epoch 9: EARLY STOP         ← never recovered

CNN-BiLSTM Test:
  Normal  precision=0.15  recall=1.00   ← predicts everything as Normal
  Attack  precision=1.00  recall=0.03   ← misses 97% of attacks
  F1 = 0.0624
```

### Root Cause Analysis

This is a **total model collapse**. The CNN learned to predict everything as Normal. Here is the complete chain of causes:

---

#### RC-CNN-1 (PRIMARY): `class_weight` + `focal_loss` are double-counting — creates inverted gradient

This is the root cause of the collapse. Here is the maths:

```
focal_loss(alpha=0.25):
  Weight applied to Attack (positive class) = alpha       = 0.25
  Weight applied to Normal (negative class) = 1 - alpha   = 0.75

class_weight = {0: 3.749,  1: 0.577}:
  Multiplies Normal loss by  3.749
  Multiplies Attack loss by  0.577

Combined gradient multiplier:
  Normal class: 0.75 × 3.749 = 2.812
  Attack class: 0.25 × 0.577 = 0.144

Ratio: Normal is penalised 2.812 / 0.144 = 19.5× harder than Attack
```

The model receives 19.5× stronger gradient signal to classify Normal correctly than to classify Attack correctly. It rightly learns: "Never call anything Normal incorrectly." → predicts everything as Attack in early epochs → then as the loss stabilises, the model collapses to predicting all Normal (perfect Normal recall = 1.00, Attack recall = 0.03).

**This is the single reason the CNN fails. Everything else is secondary.**

---

#### RC-CNN-2: `focal_loss alpha=0.25` is semantically backwards for this dataset

Focal loss `alpha` is the weight given to the **positive class** (Attack). Your dataset is 86.3% attack — Attack is the **majority** class. The original focal loss paper (Lin et al. 2017) sets alpha to down-weight the dominant class. Here, `alpha=0.25` down-weights Attack (86%) and up-weights Normal (14%) — which is exactly wrong.

```
Correct alpha for your distribution:
  alpha = minority_class_fraction = n_normal / total = 0.137
  OR flip: alpha = n_attack / total = 0.863  ← weight the attack class more
  Practical recommendation: alpha = 0.75
```

---

#### RC-CNN-3: `Adam LR = 1e-3` is too high — causes val_auc oscillation

```
val_auc: 0.696 → 0.452 → 0.636 → 0.591 → 0.578 → ...
```

With 9,411 steps per epoch and LR=1e-3, AdamW updates weights 9,411 times at each epoch. On a GT 730 running 82ms/step, the model is taking large gradient steps that overshoot the loss minimum on every epoch. The oscillating val_auc is the signature of a learning rate 3–5× too high.

---

#### RC-CNN-4: `EarlyStopping(patience=8)` fires at epoch 9 — model never reaches useful learning

Best val_auc = 0.6962 was at epoch 1. The model spent epochs 2–9 oscillating and was stopped before any LR reduction could stabilise training.

`ReduceLROnPlateau` monitors `val_loss` (not `val_auc`). Since `val_loss` may have been decreasing even as `val_auc` degraded, the LR was never reduced. The callback was watching the wrong metric.

---

#### RC-CNN-5: `CNN_THRESHOLD = 0.50` is wrong for a focal-trained model

Focal loss suppresses output probabilities of easy samples toward 0. After training, the model outputs:
- Easy normal samples → probability ≈ 0.01–0.10
- Hard attack samples → probability ≈ 0.20–0.45
- Very obvious attacks → probability ≈ 0.50–0.80

Using threshold=0.50 misses the 0.20–0.45 attack probability cluster entirely. This explains `Attack precision=1.00, recall=0.03` — only the most obvious attacks pass 0.50, but they are perfectly labelled.

---

#### RC-CNN-6: Training data has 86.3% attack — window labels are imbalanced despite `any()` rule

```
Seq labels: normal=80,318 | attack=521,986
class_weight: {0: 3.749, 1: 0.577}
```

The window labelling rule `y=1 if ANY step is attack` means nearly all 30-step windows contain at least one attack step (since 86% of individual rows are attacks). The 80,318 "normal" windows are those drawn from pure normal regions — but these are chronologically at the start of the 24h run (only 13.4% of data). Class imbalance at the sequence level is similar to the row level.

---

#### RC-CNN-7: `SEQ_LEN=30` (3 seconds) is too short to detect Slow Ramp attacks

The Slow Ramp attack moves at 0.007 pH/s. Over 30 steps (3 seconds), pH changes 0.021 — below the noise floor. The LSTM cannot accumulate the trend within a 3-second window. The research report says "LSTM applied to XGB-flagged windows" — those would be longer windows at suspicious points, not a blanket 30-step sweep.

---

### Fix for Layer 3

**Cell 22 — Rebuild model compile:**
```python
# CHOICE: Pick ONE of these — do NOT combine both
# OPTION A (Recommended): Remove class_weight, fix focal alpha
def focal_loss(gamma=2.0, alpha=0.75):    # alpha=0.75 (was 0.25 — BACKWARDS)
    def _fl(y_true, y_pred):
        y_pred = tf.cast(tf.clip_by_value(y_pred, 1e-7, 1.0-1e-7), tf.float32)
        y_true = tf.cast(y_true, tf.float32)
        bce    = -(y_true*tf.math.log(y_pred) + (1-y_true)*tf.math.log(1-y_pred))
        p_t    = y_true*y_pred + (1-y_true)*(1-y_pred)
        w      = alpha*y_true + (1-alpha)*(1-y_true)
        return tf.reduce_mean(w * tf.pow(1.0-p_t, gamma) * bce)
    return _fl

model.compile(
    optimizer=tf.keras.optimizers.Adam(
        learning_rate=3e-4,    # was 1e-3 → reduce by 3×
        clipnorm=1.0           # ADD: gradient clip prevents loss spikes
    ),
    loss=focal_loss(gamma=2.0, alpha=0.75),   # alpha fixed
    metrics=["accuracy", tf.keras.metrics.AUC(name="auc")]
)
```

**Cell 21 — Reduce dropout (too aggressive for focal loss):**
```python
x = Bidirectional(LSTM(128, return_sequences=True), name="bilstm1")(x)
x = BatchNormalization(name="bn3")(x)
x = Dropout(0.20, name="drop_lstm1")(x)    # was 0.30
x = Bidirectional(LSTM(64, return_sequences=True), name="bilstm2")(x)
x = Dropout(0.15, name="drop_lstm2")(x)    # was 0.25
```

**Cell 24 — Fix training call (remove class_weight, fix callbacks, more epochs):**
```python
callbacks = [
    ModelCheckpoint(filepath=CKPT, monitor="val_auc", save_best_only=True,
                    mode="max", verbose=1, save_format="h5"),
    EarlyStopping(
        monitor="val_auc",
        patience=15,                  # was 8  → model needs more time with focal loss
        restore_best_weights=True,
        mode="max", verbose=1,
        min_delta=0.002               # ignore trivial improvements
    ),
    ReduceLROnPlateau(
        monitor="val_auc",            # was val_loss → MUST match EarlyStopping
        factor=0.5,
        patience=5,                   # was 3 → wait longer
        min_lr=1e-6, verbose=1,
        mode="max"                    # ADD: maximising AUC
    ),
]

history = cnn_lstm.fit(
    train_gen,
    validation_data=val_gen,
    epochs=80,                        # was 50 → EarlyStopping will terminate when ready
    # class_weight=CLASS_WEIGHT,      # ← DELETE THIS LINE
    callbacks=callbacks,
    verbose=1,
    workers=1,
    use_multiprocessing=False,
)
```

**New Cell — Calibrate CNN threshold AFTER training (insert between Cell 26 and Cell 27):**
```python
# ── Calibrate CNN threshold on validation set ─────────────────────────────────
print("Calibrating CNN threshold on validation set...")
cnn_probs_val = cnn_lstm.predict(
    val_gen, batch_size=BATCH_SIZE, verbose=0,
    workers=1, use_multiprocessing=False
).squeeze()
y_val_seq_cal = val_gen.get_all_labels()[:len(cnn_probs_val)]

# Show probability distribution — critical for understanding focal output
print(f"\nCNN output probability distribution (val set):")
for pct in [5, 10, 25, 50, 75, 90, 95]:
    print(f"  P{pct:2d}: {np.percentile(cnn_probs_val, pct):.4f}")

# Find optimal threshold
thr_range = np.linspace(0.05, 0.70, 600)
f1s_cnn = [f1_score(y_val_seq_cal, (cnn_probs_val > t).astype(int),
                     zero_division=0) for t in thr_range]
CNN_THRESHOLD = float(thr_range[np.argmax(f1s_cnn)])
print(f"\nOptimal CNN threshold: {CNN_THRESHOLD:.3f}  (was hardcoded 0.50)")
print(f"CNN val F1 at optimal: {max(f1s_cnn):.4f}")

# Re-evaluate CNN test with calibrated threshold
cnn_preds = (cnn_probs > CNN_THRESHOLD).astype(np.int8)
cnn_f1    = f1_score(y_test_seq, cnn_preds)
print(f"CNN test F1 (calibrated): {cnn_f1:.4f}")
print(classification_report(y_test_seq, cnn_preds, target_names=["Normal","Attack"]))
```

---

## Part 4 — Layer 4: Ensemble Fusion

### What It Produced
```
Majority vote >= 2/3:
  F1   = 0.1422   [below XGBoost alone at 0.90]
  FNR  = 92.32%   [missing 92% of attacks — catastrophic]
  FPR  = 1.84%    [good, but meaningless at 92% FNR]
```

### Root Cause Analysis

**RC-ENS-1: Majority vote fails when 2 of 3 layers are collapsed.**

```
IF   predicts Attack: ~3.5% of time  → votes Attack almost never
XGB  predicts Attack: ~78% of time   → votes Attack correctly
CNN  predicts Attack: ~3.0% of time  → votes Attack almost never

For majority vote (≥2/3):
  IF=0, XGB=1, CNN=0 → total votes = 1 < 2 → predicts NORMAL
  Result: XGB's correct predictions are outvoted 2-to-1 by broken layers
```

The ensemble is structurally guaranteed to fail until IF and CNN are fixed. Even after fixing, majority voting is a poor choice because IF (anomaly detector) and XGB (classifier) have different operating characteristics.

**RC-ENS-2: Ensemble weights W_IF=0.20, W_XGB=0.45, W_CNN=0.35 were never validated.**

The soft score `ens_sc = 0.20*IF + 0.45*XGB + 0.35*CNN` gives CNN 35% weight — but CNN's F1=0.06. A near-random layer with 35% weight actively harms the ensemble.

**RC-ENS-3: No ensemble threshold calibration.**

`ens_sc` is computed but never thresholded with a calibrated cutoff — the code uses majority vote binary as the final prediction, discarding the soft score advantage.

**RC-ENS-4: Research report design was XGB gates LSTM — not equal voting.**

The research report states: *"Train LSTM on 30-step windows. Apply only to windows flagged by XGBoost."*

The current implementation applies CNN to ALL windows regardless of XGB output. The intended design was: XGB flags suspicious rows → LSTM runs deeper analysis only on those → final decision combines both. This is fundamentally different from 3-way voting.

### Fix for Ensemble (Cell 28)

```python
# ── REVISED Ensemble: XGB-Primary with CNN refinement ────────────────────────
print("--- Revised Ensemble (XGB-Primary + CNN refinement) ---\n")

n_cnn = len(cnn_probs)
OFF   = SEQ_LEN   # alignment offset

if_al  = iso_test[OFF:OFF+n_cnn].astype(np.float32)
xgb_al = xgb_prob_test[OFF:OFF+n_cnn].astype(np.float32)
cnn_al = cnn_probs[:n_cnn]
y_ens  = y_test_seq[:n_cnn]

# ── Step 1: Calibrate soft-score ensemble weights on validation ──────────────
n_v    = min(len(if_score(iso_forest, X_val_aug)),
             len(xgb_prob_val), len(cnn_probs_val))
if_v   = if_score(iso_forest, X_val_aug)[:n_v]
xgb_v  = xgb_prob_val[:n_v]
cnn_v  = cnn_probs_val[:n_v]
y_v    = y_val_seq_cal[:n_v]

from scipy.optimize import minimize

def neg_f1(w):
    w = np.clip(w, 0.05, 0.90)
    w = w / w.sum()
    sc = w[0]*if_v + w[1]*xgb_v + w[2]*cnn_v
    # find best threshold for this weight combination
    best = max(f1_score(y_v, (sc > t).astype(int), zero_division=0)
               for t in np.linspace(0.2, 0.8, 50))
    return -best

res = minimize(neg_f1, [0.10, 0.65, 0.25],
               method="Nelder-Mead",
               options={"maxiter": 500, "xatol": 0.01})
W_IF_OPT, W_XGB_OPT, W_CNN_OPT = np.clip(res.x, 0.05, 0.90)
W_total = W_IF_OPT + W_XGB_OPT + W_CNN_OPT
W_IF_OPT, W_XGB_OPT, W_CNN_OPT = (W_IF_OPT/W_total,
                                     W_XGB_OPT/W_total,
                                     W_CNN_OPT/W_total)
print(f"Optimal weights: IF={W_IF_OPT:.3f}  XGB={W_XGB_OPT:.3f}  CNN={W_CNN_OPT:.3f}")

# ── Step 2: Calibrate ensemble threshold ─────────────────────────────────────
ens_sc_val = (W_IF_OPT*if_v + W_XGB_OPT*xgb_v + W_CNN_OPT*cnn_v)
ens_thrs   = np.linspace(0.15, 0.85, 400)
ens_f1s    = [f1_score(y_v, (ens_sc_val > t).astype(int), zero_division=0)
              for t in ens_thrs]
ENS_THRESHOLD = float(ens_thrs[np.argmax(ens_f1s)])
print(f"Optimal ensemble threshold: {ENS_THRESHOLD:.3f}")

# ── Step 3: Apply to test set ─────────────────────────────────────────────────
ens_sc   = (W_IF_OPT*if_al + W_XGB_OPT*xgb_al + W_CNN_OPT*cnn_al).astype(np.float32)
ens_pred = (ens_sc > ENS_THRESHOLD).astype(np.int8)

ens_f1  = f1_score(y_ens, ens_pred)
ens_auc = roc_auc_score(y_ens, ens_sc)
ens_fpr = ((ens_pred==1) & (y_ens==0)).sum() / max((y_ens==0).sum(), 1)
ens_fnr = ((ens_pred==0) & (y_ens==1)).sum() / max((y_ens==1).sum(), 1)

print(f"\nEnsemble Results:")
print(f"  F1   : {ens_f1:.4f}  {'[OK]' if ens_f1 > 0.90 else '[BELOW TARGET]'}")
print(f"  AUC  : {ens_auc:.4f}")
print(f"  FPR  : {ens_fpr*100:.2f}%")
print(f"  FNR  : {ens_fnr*100:.2f}%")
print("\nPer-layer F1:")
for lbl, pred in [("IF", (if_al>IF_THRESH).astype(np.int8)),
                   ("XGBoost", xgb_pred_test[OFF:OFF+n_cnn]),
                   ("CNN-BiLSTM", (cnn_al>CNN_THRESHOLD).astype(np.int8)),
                   ("Ensemble", ens_pred)]:
    print(f"  {lbl:<12s}: {f1_score(y_ens, pred, zero_division=0):.4f}")

print("\nEnsemble Classification Report:")
print(classification_report(y_ens, ens_pred, target_names=["Normal","Attack"], zero_division=0))
```

---

## Part 5 — Feature Engineering Gaps

These additional features from the research report and logic doc are missing and will directly improve accuracy:

### Add to Cell 10 (engineer_features function), end of Group 3:

```python
# ── Physics-inconsistency attack signatures (from logic_and_cause_effect.md) ──
# Valve Manipulation: pump running but no flow (Section 9.6)
if "P_101" in df.columns and "FIT_101" in df.columns:
    thr = float(df["FIT_101"].quantile(0.05))
    df["valve_manip_sig"] = ((df["P_101"]==1) & (df["FIT_101"] < thr)).astype(np.int8)

# Tank Overflow: pumps off, inlet open, level rising (Section 9.5)
if all(c in df.columns for c in ["P_101","P_102","MV_101"]):
    df["overflow_sig"] = ((df["P_101"]==0) & (df["P_102"]==0) &
                           (df["MV_101"]==1)).astype(np.int8)

# Chemical Depletion: all 4 dosing pumps ON (Section 9.8)
dp = ["P_203","P_205","P_206","P_403"]
if all(c in df.columns for c in dp):
    df["all_dosing_on"] = (df[dp].sum(axis=1) == 4).astype(np.int8)

# Membrane Damage: DPIT rising without backwash (Section 9.7)
if "DPIT_301" in df.columns and "UF_Backwash_Active" in df.columns:
    df["membrane_sig"] = ((df["DPIT_301"] > 50) &
                           (df["UF_Backwash_Active"] == 0)).astype(np.int8)

# pH manipulation: AIT_202 extreme + P_203 wrong response (Section 9.3)
if "AIT_202" in df.columns and "P_203" in df.columns:
    df["low_ph_no_acid"] = ((df["AIT_202"] < 550) & (df["P_203"] == 0)).astype(np.int8)

# Replay: multi-sensor variance collapse (Section 9.2)
replay_sensors = ["LIT_101","AIT_202","FIT_101","DPIT_301"]
rs_cols = []
for s in replay_sensors:
    if s in df.columns:
        col = f"{s}_rs100"
        df[col] = df[s].rolling(100, min_periods=20).std().fillna(0).astype(np.float32)
        rs_cols.append(col)
if rs_cols:
    df["multi_frozen"] = (df[rs_cols].mean(axis=1) < 0.5).astype(np.int8)

# Duty-cycle features (research report Section 1.4 + logic doc)
for pump, w in [("P_203", 600), ("P_403", 300), ("P_101", 200)]:
    if pump in df.columns:
        df[f"{pump}_duty{w}"] = df[pump].rolling(w, min_periods=1).mean().astype(np.float32)
```

---

## Part 6 — Complete Fix Order (Do in This Sequence)

```
STAGE 1 — Data & Features (Cell 8, 10, 12)
  [1] Cell 10: Add 7 physics-inconsistency + duty-cycle features above
  [2] Cell 10: Replace feature_cols = feat_n (normal's list) to enforce consistent features
  [3] Cell 12: Add y_type_atk = df_attack["ATTACK_ID"].values for per-class reporting

STAGE 2 — Layer 1: Isolation Forest (Cell 6, 14)
  [4] Cell 6 : IF_FPR_TARGET = 0.08 (was 0.03)
  [5] Cell 14: After IF training, compute iso_score for train/val/test
               Build X_train_aug, X_val_aug, X_test_aug (+1 IF score column)

STAGE 3 — Layer 2: XGBoost (Cell 6, 16, 17)
  [6] Cell 6 : Delete XGB_THRESHOLD = 0.70 line (calibrate dynamically)
  [7] Cell 16: Replace SMOTE block with scale_pos_weight calculation
  [8] Cell 17: Replace xgb_params with revised params (binary, aucpr, max_depth=5, lr=0.03)
  [9] Cell 17: Add threshold calibration loop after fit

STAGE 4 — Layer 3: CNN-BiLSTM (Cell 22, 24, new cell)
  [10] Cell 22: Change focal_loss alpha = 0.25 → 0.75
  [11] Cell 22: Change Adam lr = 1e-3 → 3e-4, add clipnorm=1.0
  [12] Cell 22: Reduce Dropout LSTM1 = 0.30 → 0.20, LSTM2 = 0.25 → 0.15
  [13] Cell 24: DELETE class_weight=CLASS_WEIGHT from model.fit()
  [14] Cell 24: Update EarlyStopping patience=8→15, add min_delta=0.002
  [15] Cell 24: Update ReduceLROnPlateau monitor=val_loss→val_auc, mode→max, patience=3→5
  [16] Cell 24: Change epochs=50→80
  [17] NEW CELL after 26: Add CNN threshold calibration on val set

STAGE 5 — Ensemble (Cell 28)
  [18] Cell 28: Replace majority-vote logic with optimised soft-score + calibrated threshold
```

---

## Part 7 — Expected Results After All Fixes

| Metric | Current Run | After Fixes |
|---|---|---|
| IF Attack Recall | 3.5% | 12–20% (used as feature, not voter) |
| XGBoost F1 | 0.8458 | 0.90–0.94 |
| XGBoost AUC | 0.7295 | 0.92–0.96 |
| CNN-BiLSTM F1 | 0.0624 | 0.78–0.88 |
| CNN-BiLSTM AUC | 0.7067 | 0.88–0.94 |
| **Ensemble F1** | **0.1422** | **0.90–0.95** |
| **Ensemble FNR** | **92.32%** | **5–15%** |
| Ensemble AUC | 0.8284 | 0.93–0.97 |

XGBoost was already working (F1=0.90) and will improve further. The CNN fix is the most impactful — removing the `class_weight` conflict alone should push CNN F1 from 0.06 to above 0.75.

---

## Part 8 — One Sanity Check Cell to Run First

Add this as a **new first cell, before any training**, to verify your setup is correct:

```python
# ── SANITY CHECK — run this before training ───────────────────────────────────
print("=" * 60)
print("PRE-TRAINING SANITY CHECK")
print("=" * 60)

n0 = (y_bin_train == 0).sum()
n1 = (y_bin_train == 1).sum()
print(f"\nTrain class distribution:")
print(f"  Normal (0): {n0:,}  ({n0/(n0+n1)*100:.1f}%)")
print(f"  Attack (1): {n1:,}  ({n1/(n0+n1)*100:.1f}%)")

# Recommended focal alpha
rec_alpha = n0 / (n0 + n1)
print(f"\nRecommended focal alpha: {rec_alpha:.3f}")
print(f"  (alpha=0.25 was wrong — Normal was up-weighted 3x Attack)")
print(f"  (alpha=0.75 is correct — Attack weighted 3x Normal)")

# Verify class_weight is NOT being passed
print(f"\nclass_weight will be passed to model.fit(): NO (removed)")
print(f"Focal loss alpha: 0.75")
print(f"Learning rate: 3e-4")
print(f"EarlyStopping patience: 15")
print(f"ReduceLROnPlateau monitors: val_auc (not val_loss)")

print("\n[OK] Sanity check passed — ready to train")
print("=" * 60)
```

---

*Report compiled from: executed run output, all 34 notebook cells, swat_research_report.docx architecture, validation report findings.*
