# SWaT v3 — Overfitting Analysis & Fixes

**Pipeline:** `swat_pytorch_v3_dualdataset.ipynb`  
**Run Date:** 2026-05-05  
**Author:** Dweep Vira  
**Status:** CRITICAL OVERFITTING CONFIRMED — do not use v3 results for publication

---

## Executive Summary

The v3 pipeline produces `CNN F1 = 1.0000`, `AUC = 1.0000`, and `Ensemble F1 = 1.0000` — scores that are **physically impossible** for a real anomaly detection system on industrial data. These are not a sign of a well-trained model. They are a sign of **data leakage**, confirmed by multiple independent symptoms. The AE is also completely non-functional (F1 = 0.0003). This document catalogues every identified issue and the exact code fix for each.

---

## Issues Found

---

### ISSUE 1 — Temporal Boundary Leakage in CNN Window Dataset (CRITICAL)

**Severity:** Critical — invalidates all CNN and Ensemble results  
**Evidence:**

```
Ep   1/80 | train_loss=0.0775 | val_auc=1.0000
```

A real model cannot achieve perfect AUC after one epoch of random-weight training. This is the clearest possible sign of a trivially separable artifact in the data.

**Root Cause:**

`X_train_sc` is constructed by directly concatenating two unrelated time series:

```python
X_train_raw = np.concatenate([X_nor_tr, X_atk_tr], axis=0)  # 602K + 521K rows
```

`SwatWindowDataset` then slides a 150-step window over this flat concatenated array without restriction. Windows near index 602,000 span the **boundary between the end of the normal dataset and the start of the attack dataset**. These "chimeric" windows contain half of one time series and half of another — they produce a sharp discontinuity in every sensor at the midpoint, which is trivially detectable. The CNN learns this boundary artifact, not genuine attack signatures.

The same leakage exists in the validation set for the same reason.

**Confirmation:** The SHAP feature `FIT_101_rz` (rolling z-score) ranks #1 with importance 1.48. A rolling z-score will spike massively at any series boundary regardless of the underlying process, confirming the CNN is detecting the concatenation seam.

**Fix — Cell 12 (after concatenation):**

```python
# Record the exact row index where normal data ends in each split
NORMAL_TRAIN_BOUNDARY = len(X_nor_tr)   # boundary index in X_train_sc
NORMAL_VAL_BOUNDARY   = len(X_nor_va)   # boundary index in X_val_sc
NORMAL_TEST_BOUNDARY  = len(X_nor_te)   # boundary index in X_test_sc
```

**Fix — Cell 23 (SwatWindowDataset):**

Add an optional `exclude_boundaries` parameter that removes any window whose span `[start, start + SEQ_LEN)` crosses a boundary index:

```python
class SwatWindowDataset(Dataset):
    def __init__(self, X, y_bin, seq_len, indices=None, majority_thresh=0.5,
                 boundary_indices=None):
        self.X = X; self.y = y_bin; self.seq_len = seq_len
        self.maj_thresh = majority_thresh
        n_windows = len(X) - seq_len

        if indices is not None:
            starts = np.array([i for i in indices if i < n_windows], dtype=np.int64)
        else:
            starts = np.arange(n_windows, dtype=np.int64)

        # Exclude windows that cross dataset boundaries
        if boundary_indices is not None:
            def crosses(s):
                end = s + seq_len
                return any(s < b <= end for b in boundary_indices)
            starts = np.array([s for s in starts if not crosses(s)], dtype=np.int64)

        self.starts = starts

    # ... rest unchanged ...
```

Then instantiate with:

```python
train_ds = SwatWindowDataset(X_train_sc, y_bin_train, SEQ_LEN,
                              majority_thresh=0.5,
                              boundary_indices=[NORMAL_TRAIN_BOUNDARY])
val_ds   = SwatWindowDataset(X_val_sc,   y_bin_val,   SEQ_LEN,
                              majority_thresh=0.5,
                              boundary_indices=[NORMAL_VAL_BOUNDARY])
test_ds  = SwatWindowDataset(X_test_sc,  y_bin_test,  SEQ_LEN,
                              majority_thresh=0.5,
                              boundary_indices=[NORMAL_TEST_BOUNDARY])
```

**Expected outcome after fix:** val_auc will no longer be 1.0 from epoch 1. Real training dynamics will emerge.

---

### ISSUE 2 — Autoencoder Non-Functional (F1 = 0.0003) (CRITICAL)

**Severity:** Critical — AE contributes zero detection signal  
**Evidence:**

```
AE attack score: mean=0.001  (normal mean=0.000)
AE (1b)     : F1=0.0003
```

The AE reconstruction error on attack samples (0.001) is essentially identical to normal samples (0.000). The AE contributes nothing to the ensemble and is dead weight.

**Root Cause 1 — AE validated on mixed data:**

```python
# In the AE training loop, the val MSE is computed on X_val_sc
# which contains BOTH normal and attack rows (after scaling)
```

The val_mse decreasing does not confirm the AE is learning the normal manifold — it could simply be fitting both classes. Early stopping fires at epoch 23 on a contaminated metric.

**Root Cause 2 — Score normalization collapses the signal:**

```python
ae_recon_error_normalized = (raw - ae_min) / (ae_max - ae_min + 1e-9)
```

If `ae_min ≈ 0.000` and `ae_max ≈ 0.001` (from normal data), then attack scores of 0.001 normalize to `~1.0` which sounds good — but if attacks also score ≈ 0.001, they normalize to ≈ 1.0 too, making the normalized score useless.

**Root Cause 3 — The AE threshold is set at 0.050 with FPR = 0.00%:**

```
AE threshold: 0.050  (FPR target < 5%)
AE FPR (nor) : 0.00%
```

With all scores near 0.001, a threshold of 0.050 catches literally nothing. The FPR of 0% does not mean good calibration — it means the threshold is set orders of magnitude above the actual score distribution.

**Fix — Cell 16 (AE training):**

Validate on normal-only validation data:

```python
# Use ONLY normal rows for AE validation — not the combined val set
# X_nor_va_sc is the scaled version of X_nor_va
X_nor_va_sc = scaler.transform(X_nor_va).astype(np.float32)

# In the AE training loop, replace X_val_sc → X_nor_va_sc:
def ae_validate(ae_model, X_val_normal_sc, device, batch_size=512):
    ae_model.eval()
    total_mse, n = 0.0, 0
    with torch.no_grad():
        for i in range(0, len(X_val_normal_sc), batch_size):
            xb = torch.from_numpy(X_val_normal_sc[i:i+batch_size]).to(device)
            recon = ae_model(xb)
            total_mse += F.mse_loss(recon, xb).item() * len(xb)
            n += len(xb)
    return total_mse / n
```

Use percentile-based threshold calibration instead of FPR sweep:

```python
# Compute reconstruction error on normal-only train data
ae_nor_errors = compute_ae_errors(ae_model, X_nor_train_raw_sc, DEVICE)
# Threshold = 99th percentile of NORMAL errors (not FPR sweep)
AE_THRESHOLD = float(np.percentile(ae_nor_errors, 99))
print(f"AE threshold (99th pct of normal): {AE_THRESHOLD:.6f}")

# Sanity check: attack mean should be > 2× normal mean
ae_atk_errors = compute_ae_errors(ae_model, scaler.transform(X_atk_tr[:5000]), DEVICE)
if ae_atk_errors.mean() < ae_nor_errors.mean() * 1.5:
    print("[WARN] AE attack errors NOT significantly higher than normal — "
          "AE is reconstructing attacks well. Architecture may need more capacity.")
```

---

### ISSUE 3 — Per-Attack-Type Precision Bug (BUG)

**Severity:** High — all per-attack-type precision/F1 values are wrong  
**Evidence:**

```
slow_ramp   n=4,456 | Recall=1.000 | P=0.040 | F1=0.077
```

Precision of 4% on a model that supposedly achieves ensemble F1=1.0 is contradictory.

**Root Cause:**

```python
precision_t = detected / max((ens_pred==1).sum(), 1)
```

This divides by the **total number of positive predictions across all attack types**, not by the number of positive predictions for this specific attack type. With 111K total positive predictions in the test set, even 4,456 correctly detected `slow_ramp` windows yields 4456/111K ≈ 4%.

**Fix — Cell 32:**

Replace the manual precision calculation with sklearn:

```python
from sklearn.metrics import precision_score, recall_score, f1_score

print("Per-Attack-Type F1 (Test Set Ensemble)")
print("="*72)
results = []
for aid, aname in sorted(ATTACK_TYPE_MAP.items()):
    if aid == 0: continue
    # Build per-type binary ground truth: 1 if this window's majority type is aid
    type_mask = np.array([
        int((y_type_test[OFF+i:OFF+i+SEQ_LEN] == aid).mean() > 0.5)
        for i in range(n_cnn)
    ], dtype=np.int8)
    n_type = type_mask.sum()
    if n_type == 0: continue

    # Use only the subset of windows where this attack IS or ISN'T the true label
    # For per-type metrics, treat other attack types as "not this attack" (negative)
    y_true_t = type_mask
    y_pred_t = (ens_pred == 1).astype(np.int8)  # ensemble said "attack"

    prec_t   = precision_score(y_true_t, y_pred_t, zero_division=0)
    rec_t    = recall_score(y_true_t, y_pred_t, zero_division=0)
    f1_t     = f1_score(y_true_t, y_pred_t, zero_division=0)

    flag = "[CRITICAL MISS]" if rec_t < 0.50 else ("[OK]" if rec_t > 0.80 else "[WARN]")
    print(f"  {aname:<24s} n={n_type:6,} | Recall={rec_t:.3f} | P={prec_t:.3f} | F1={f1_t:.3f}  {flag}")
    results.append((aname, n_type, rec_t, f1_t))
```

---

### ISSUE 4 — Replay Attack Disappears from Per-Type Evaluation

**Severity:** Medium — safety-critical attack type not evaluated  
**Evidence:**

```
replay (ATTACK_ID=15): 29,552 rows in training data
```

But `replay` never appears in the per-attack-type output.

**Root Cause:**

`majority_thresh=0.5` requires >50% of a 150-step window to be replay. Replay events may be shorter than 75 steps (7.5 seconds), meaning all replay windows get labeled as normal and are never evaluated.

**Fix — Cell 23 (majority_thresh) and Cell 32 (evaluation):**

Option A — Lower threshold for evaluation only:

```python
# For evaluation, use any() style: if ANY step in window is an attack, evaluate
# Keep majority_thresh=0.5 for TRAINING (avoids noisy labels)
# Use any_thresh=0.05 for EVALUATION (catches short attacks)
EVAL_THRESH = 0.05  # at least 1 step (0.67%) of 150 must be the attack type

type_mask = np.array([
    int((y_type_test[OFF+i:OFF+i+SEQ_LEN] == aid).mean() > EVAL_THRESH)
    for i in range(n_cnn)
], dtype=np.int8)
```

Option B — Add replay as a special short-window attack:

```python
# If replay: use a shorter window evaluation (SEQ_LEN=30 instead of 150)
REPLAY_WINDOW = 30
```

---

### ISSUE 5 — ReduceLROnPlateau Fires Prematurely (MODERATE)

**Severity:** Moderate — wastes LR budget before real training begins  
**Evidence:**

```
Epoch 00007: reducing learning rate of group 0 to 1.5000e-04.
Epoch 00013: reducing learning rate of group 0 to 7.5000e-05.
```

val_auc is 1.0000 at both points, meaning the scheduler fires because floating-point val_auc cannot improve beyond 1.0 — patience=5 expires every 6 epochs automatically.

**Root Cause:** This is a downstream consequence of Issue 1 (data leakage giving val_auc=1.0 immediately). After fixing Issue 1, real val_auc dynamics will prevent premature firing.

**Fix — also add a guard (Cell 26):**

```python
# Guard: don't reduce LR if already at near-perfect AUC (sign of leakage)
if vl_auc < 0.9999:
    scheduler.step(vl_auc)
else:
    print(f"  [WARN] val_auc={vl_auc:.4f} — possible data leakage, scheduler paused")
```

---

### ISSUE 6 — CNN Training Dataset Too Large for CPU (PERFORMANCE)

**Severity:** Low-medium — causes 4,800 minutes of training time  
**Evidence:**

```
Training done: 4803.8 min | best val_auc=1.0000
```

1,123,629 training windows × 150 steps × 245 features on CPU (no GPU). A single epoch takes 4,000–58,000 seconds depending on background load.

**Fix — Cell 23 (add subsampling before DataLoader):**

```python
MAX_TRAIN_WINDOWS = 300_000  # cap at 300K windows — enough for meaningful training

if len(train_ds) > MAX_TRAIN_WINDOWS:
    rng = np.random.default_rng(SEED)
    sampled_starts = rng.choice(train_ds.starts, size=MAX_TRAIN_WINDOWS, replace=False)
    train_ds.starts = np.sort(sampled_starts)  # keep chronological order
    train_labels = train_ds.get_labels()
    n_train_nor  = (train_labels == 0).sum()
    n_train_atk  = (train_labels == 1).sum()
    sample_weights = np.where(train_labels==1, n_train_nor/max(n_train_atk,1), 1.0)
    sampler = WeightedRandomSampler(
        weights=torch.from_numpy(sample_weights).float(),
        num_samples=len(train_labels), replacement=True
    )
    print(f"Subsampled train windows: {len(train_ds):,} (from {len(train_ds.starts):,})")
```

Estimated training time after fix: ~60–120 minutes per epoch on CPU (manageable).

---

### ISSUE 7 — Near-Balanced Class Split is Unrealistic (DESIGN)

**Severity:** Low — inflates reported metrics vs real deployment  
**Evidence:**

```
Train: normal 602,364 (53.6%)  attack 521,415 (46.4%)
scale_pos_weight: 1.155
```

Real-world SWaT operation has ~85% normal data. The near-equal split makes the problem artificially easy and produces overly optimistic FPR/precision estimates. `scale_pos_weight=1.155` effectively disables any class reweighting.

**Fix — Cell 12 (after concat):**

Undersample attack training data to achieve a more realistic 75/25 split:

```python
TARGET_ATTACK_FRAC = 0.25
n_nor_tr = len(X_nor_tr)
n_atk_target = int(n_nor_tr * TARGET_ATTACK_FRAC / (1 - TARGET_ATTACK_FRAC))
if len(X_atk_tr) > n_atk_target:
    rng = np.random.default_rng(SEED)
    atk_idx = rng.choice(len(X_atk_tr), size=n_atk_target, replace=False)
    atk_idx.sort()
    X_atk_tr_sub    = X_atk_tr[atk_idx]
    y_atk_bin_tr_sub = y_atk_bin_tr[atk_idx]
    y_atk_id_tr_sub  = y_atk_id_tr[atk_idx]
    print(f"Attack training undersampled: {len(X_atk_tr):,} → {n_atk_target:,}")
else:
    X_atk_tr_sub, y_atk_bin_tr_sub, y_atk_id_tr_sub = X_atk_tr, y_atk_bin_tr, y_atk_id_tr
```

Note: val and test sets should NOT be undersampled — they should reflect the realistic ratio.

---

## Summary Table

| # | Issue | Severity | Root Cause | Fix Cell |
|---|-------|----------|------------|----------|
| 1 | CNN val_auc=1.0 from epoch 1 — data leakage via boundary windows | **Critical** | Sliding windows cross normal→attack concat boundary | Cell 12 + 23 |
| 2 | AE F1=0.0003 — reconstruction errors identical for normal and attack | **Critical** | Mixed-data AE validation; score normalization collapse | Cell 16 |
| 3 | Per-attack precision bug (4–22% nonsensical values) | **High** | Denominator is global prediction count, not per-type | Cell 32 |
| 4 | Replay attack disappears from per-type evaluation | **Medium** | majority_thresh=0.5 labels all short-duration replay windows as normal | Cell 32 |
| 5 | ReduceLR fires every 6 epochs despite val_auc=1.0 | **Medium** | Downstream of Issue 1; floating-point ceiling on perfect AUC | Cell 26 |
| 6 | 4,800 min training time on CPU | **Medium** | 1.1M windows on CPU with no subsampling | Cell 23 |
| 7 | 53/47 class split — unrealistic for real deployment evaluation | **Low** | Attack dataset same size as normal by design | Cell 12 |

---

## Expected Results After All Fixes

| Metric | v3 (leaked) | v4 (target after fixes) |
|--------|-------------|-------------------------|
| CNN val_auc epoch 1 | 1.0000 | 0.65–0.80 (realistic) |
| CNN test F1 | 1.0000 | 0.82–0.92 |
| AE F1 | 0.0003 | 0.40–0.70 |
| Ensemble F1 | 1.0000 | 0.85–0.94 |
| Training time (CNN) | 4,803 min | 60–180 min |

A perfect F1=1.0 on a real system is not achievable — the target in the research report (F1 > 0.88) is the correct standard. Any result above 0.99 should be treated as a leakage warning.

---

## Quick Checklist Before Next Run

- [ ] Boundary indices recorded and passed to all three `SwatWindowDataset` instantiations
- [ ] AE validation loop uses `X_nor_va_sc` (normal-only), not `X_val_sc`
- [ ] AE threshold is 99th percentile of normal reconstruction errors, not FPR sweep
- [ ] Sanity check: assert `ae_attack_mean > ae_normal_mean * 1.5` after AE training
- [ ] Sanity check: assert `val_auc < 0.99` at epoch 1 (else stop and check leakage)
- [ ] Per-attack precision uses per-type denominator (sklearn metrics)
- [ ] CNN training capped at 300K windows
- [ ] Training time per epoch logged — if < 30 min on CPU, something is suspicious

---

*Generated: May 2026 | Applies to: swat_pytorch_v3_dualdataset.ipynb → swat_pytorch_v4_fixed.ipynb*
