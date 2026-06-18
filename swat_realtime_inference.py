#!/usr/bin/env python3
"""
swat_realtime_inference.py
==========================
Real-time ML inference server for the SWaT Digital Twin.

Architecture
------------
                ┌──────────────────────────────────┐
  MATLAB/CODESYS│  ws_server.py  ws://0.0.0.0:8765 │
                └────────────────┬─────────────────┘
                                 │ JSON sensor frames every 100 ms
               ┌─────────────────▼──────────────────────────────────────┐
               │  swat_realtime_inference.py  (this file)               │
               │                                                        │
               │  FeatureEngine ──► 4-Layer Ensemble Pipeline           │
               │   L1a IsolationForest  │  L1b Autoencoder              │
               │   L2  XGBoost          │  L3  CNN-BiLSTM               │
               │                                                        │
               │  serves ML results on  ws://0.0.0.0:8766               │
               │  also accepts attack commands from dashboard           │
               └─────────────────┬──────────────────────────────────────┘
                                 │ JSON ML results every 100 ms
               ┌─────────────────▼──────────────────────────┐
               │  swat_ml_dashboard.html (browser client)   │
               └────────────────────────────────────────────┘

Usage
-----
  # Real mode (requires models/ and upstream WS):
  python swat_realtime_inference.py --plc-host 192.168.5.195 --plc-port 1502

  # Demo mode (no models or upstream WS needed — simulated data):
  python swat_realtime_inference.py --demo

Arguments
---------
  --plc-host      CODESYS PLC IP (used for attack injection via Modbus)
  --plc-port      CODESYS Modbus TCP port (default: 1502)
  --src-ws        Upstream digital-twin WebSocket URL (default: ws://localhost:8765)
  --ml-port       Port for the ML inference WebSocket server (default: 8766)
  --models-dir    Path to saved models directory (default: models)
  --no-attack-inj Disable Modbus attack injection (safe mode, ML only)
  --demo          Enable demo mode with simulated sensor data and ML inference
"""

from __future__ import annotations

import asyncio
import argparse
import json
import logging
import math
import random
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("SWaT-ML")


# =============================================================================
# NEURAL NETWORK ARCHITECTURES  (must match training code exactly)
# =============================================================================

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    TORCH_AVAILABLE = True

    class SWaTAutoencoder(nn.Module):
        """Autoencoder for anomaly detection via reconstruction error."""

        def __init__(self, n_features: int) -> None:
            super().__init__()
            self.encoder = nn.Sequential(
                nn.Linear(n_features, 128), nn.ReLU(), nn.Dropout(0.10),
                nn.Linear(128, 64),         nn.ReLU(),
                nn.Linear(64, 32),          nn.ReLU(),
            )
            self.decoder = nn.Sequential(
                nn.Linear(32, 64),          nn.ReLU(),
                nn.Linear(64, 128),         nn.ReLU(),
                nn.Linear(128, n_features),
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.decoder(self.encoder(x))

    class TemporalAttention(nn.Module):
        """Bahdanau-style temporal attention for sequence models."""

        def __init__(self, feat_dim: int) -> None:
            super().__init__()
            self.W = nn.Linear(feat_dim, 1, bias=False)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            e = torch.tanh(self.W(x))
            a = torch.softmax(e, dim=1)
            return (x * a).sum(dim=1)

    class SWaTCNNBiLSTM(nn.Module):
        """CNN-BiLSTM with temporal attention for sequence classification."""

        def __init__(self, n_features: int, seq_len: int) -> None:
            super().__init__()
            self.conv1    = nn.Conv1d(n_features, 64, kernel_size=3, padding=2)
            self.bn1      = nn.BatchNorm1d(64)
            self.conv2    = nn.Conv1d(64, 128, kernel_size=3, padding=2)
            self.bn2      = nn.BatchNorm1d(128)
            self.drop_cnn = nn.Dropout(0.15)
            self.pool     = nn.MaxPool1d(2)
            self.bilstm1  = nn.LSTM(128, 128, batch_first=True, bidirectional=True)
            self.bn3      = nn.BatchNorm1d(256)
            self.drop1    = nn.Dropout(0.20)
            self.bilstm2  = nn.LSTM(256, 64, batch_first=True, bidirectional=True)
            self.drop2    = nn.Dropout(0.15)
            self.attention = TemporalAttention(128)
            self.fc1      = nn.Linear(128, 64)
            self.drop3    = nn.Dropout(0.15)
            self.fc2      = nn.Linear(64, 1)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            h = x.permute(0, 2, 1)
            h = F.relu(self.bn1(self.conv1(h)))
            h = h[:, :, :x.size(1)]
            h = self.drop_cnn(F.relu(self.bn2(self.conv2(h))))
            h = h[:, :, :x.size(1)]
            h = self.pool(h)
            h = h.permute(0, 2, 1)
            h, _ = self.bilstm1(h)
            h = self.bn3(h.permute(0, 2, 1)).permute(0, 2, 1)
            h = self.drop1(h)
            h, _ = self.bilstm2(h)
            h = self.drop2(h)
            h = self.attention(h)
            h = self.drop3(F.relu(self.fc1(h)))
            return torch.sigmoid(self.fc2(h))

except ImportError:
    TORCH_AVAILABLE = False
    log.warning("PyTorch not available — neural network layers will use demo fallback")

# Optional imports (graceful degradation)
try:
    import joblib
    JOBLIB_AVAILABLE = True
except ImportError:
    JOBLIB_AVAILABLE = False
    log.warning("joblib not available — model loading disabled")

try:
    import websockets
    import websockets.exceptions
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    log.error("websockets package is required: pip install websockets")
    sys.exit(1)


# =============================================================================
# PIPELINE CONFIGURATION DEFAULTS
# =============================================================================
# These values match the saved pipeline_config.joblib and are used as fallbacks.

DEFAULT_PIPELINE_CONFIG: dict[str, Any] = {
    "N_FEATURES": 244,
    "AE_INPUT_DIM": 245,
    "SEQ_LEN": 150,
    "IF_THRESHOLD": 0.4,
    "AE_THRESHOLD": 1.0,
    "AE_THRESHOLD_RAW": 127.166,
    "AE_THRESHOLD_PERC": 0.0114,
    "AE_MIN": 0.00021,
    "AE_MAX": 2543.32,
    "XGB_THRESHOLD": 0.2696,
    "CNN_THRESHOLD": 9.06e-06,
    "ENS_THRESHOLD": 0.7071,
    "ENS_WEIGHTS": [0.00655, 0.00049, 0.9488, 0.0441],
    "EXPECTED_DT": 0.1,
    "HZ": 10.0,
    "n_classes": 10,
    "ROLLING_WINDOW": 20,
    "LAG_STEPS": [5, 10, 30],
    "LAG_COLS": [],
    "dt_mean": 0.1,
    "dt_std": 0.02,
    "sensor_cols": [],
    "feature_cols": [],
}


# =============================================================================
# FEATURE ENGINE
# =============================================================================

class FeatureEngine:
    """
    Stateful real-time feature engine.

    Maintains rolling buffers for:
      - delta_t / jitter (temporal)
      - rolling mean / std per sensor (statistical)
      - lag values per lag column
      - previous sensor values (rate-of-change)
    """

    def __init__(self, config: dict) -> None:
        self.cfg          = config
        self.feature_cols = config.get("feature_cols", [])
        self.sensor_cols  = config.get("sensor_cols", [])
        self.scaler       = None  # set externally after load
        self._last_ts: float | None = None
        self._dt_buf      = deque(maxlen=50)
        EXPECTED_DT       = config.get("EXPECTED_DT", 0.1)
        self._dt_buf.extend([EXPECTED_DT] * 50)

        W = config.get("ROLLING_WINDOW", 20)
        self._roll_bufs   = {c: deque(maxlen=W) for c in self.sensor_cols}

        lags    = config.get("LAG_STEPS", [5, 10, 30])
        lagcols = config.get("LAG_COLS", [])
        maxlag  = max(lags) if lags else 30
        self._lag_bufs    = {c: deque(maxlen=maxlag + 1) for c in lagcols}

        self._prev_vals: dict[str, Any] = {}

    def process(self, raw: dict) -> np.ndarray | None:
        """
        Convert one raw sensor dict to a scaled numpy feature vector.
        Returns None until there is enough data (lag buffer warm-up).
        """
        cfg = self.cfg
        ts  = time.time()

        # ── Temporal ──────────────────────────────────────────────────────────
        dt = (ts - self._last_ts) if self._last_ts else cfg.get("EXPECTED_DT", 0.1)
        self._last_ts = ts
        self._dt_buf.append(dt)
        dt_arr  = np.array(self._dt_buf)
        dt_mean = dt_arr.mean()
        dt_roll = dt_mean
        dt_z    = (dt - cfg.get("dt_mean", 0.1)) / max(cfg.get("dt_std", 0.02), 1e-9)
        jitter  = abs(dt - dt_roll)

        features: dict[str, float] = {
            "delta_t":              dt,
            "delta_t_zscore":       dt_z,
            "delta_t_rolling_mean": dt_roll,
            "delay_anomaly":        float(dt > 0.2),
            "delay_severe":         float(dt > 0.5),
            "jitter":               jitter,
            "jitter_high":          float(jitter > 0.05),
        }

        # ── Raw sensor values ─────────────────────────────────────────────────
        for c in self.sensor_cols:
            v = float(raw.get(c, 0))
            features[c] = v
            self._roll_bufs[c].append(v)

        # ── Physical ──────────────────────────────────────────────────────────
        def _get(k: str) -> float:
            return float(raw.get(k, 0))

        for a, b in [("LIT_101", "LIT_301"), ("LIT_301", "LIT_401"),
                      ("LIT_401", "LIT_501")]:
            features[f"level_diff_{a}_{b}"] = _get(a) - _get(b)

        for a, b in [("FIT_101", "FIT_201"), ("FIT_201", "FIT_301"),
                      ("FIT_301", "FIT_401"), ("FIT_401", "FIT_501"),
                      ("FIT_501", "FIT_601")]:
            features[f"flow_balance_{a}_{b}"] = _get(a) - _get(b)

        features["pressure_spike"] = float(_get("PIT_501") > 1800)

        dpit = _get("DPIT_301")
        prev_dpit = self._prev_vals.get("DPIT_301", dpit)
        dpit_roc  = dpit - prev_dpit
        prev_dpit_roc = self._prev_vals.get("dpit_roc", dpit_roc)
        features["dpit_roc"]  = dpit_roc
        features["dpit_roc2"] = dpit_roc - prev_dpit_roc
        self._prev_vals["DPIT_301"] = dpit
        self._prev_vals["dpit_roc"] = dpit_roc

        for ph_col in ["AIT_202", "AIT_203", "AIT_402"]:
            v = _get(ph_col)
            features[f"{ph_col}_pH_deviation"] = float(v < 650 or v > 850)

        features["turbidity_high"] = float(_get("AIT_201") > 800)

        # ── Control / PLC rules ───────────────────────────────────────────────
        p101   = float(raw.get("P_101", 0))
        fit101 = _get("FIT_101")
        features["pump_flow_inconsistency"] = float(p101 == 1 and fit101 < 0.05)

        features["ph_pump_inconsistency"] = float(
            _get("AIT_202") > 750 and float(raw.get("P_203", 0)) == 0
        )

        for mv_col, fit_col in [("MV_101", "FIT_101"), ("MV_201", "FIT_201"),
                                  ("MV_301", "FIT_301")]:
            mv  = float(raw.get(mv_col, 0))
            fit = _get(fit_col)
            features[f"valve_flow_mismatch_{mv_col}"] = float(mv == 0 and fit > 0.1)

        # Pump duty cycles (rolling mean of recent state)
        for p_col in ["P_101", "P_301", "P_501"]:
            pv = float(raw.get(p_col, 0))
            buf_key = f"duty_{p_col}"
            if buf_key not in self._prev_vals:
                self._prev_vals[buf_key] = deque([pv] * 60, maxlen=60)
            self._prev_vals[buf_key].append(pv)
            features[f"{p_col}_duty_60"] = float(np.mean(self._prev_vals[buf_key]))

        # Rate of change per sensor
        for c in self.sensor_cols:
            prev = self._prev_vals.get(c, float(raw.get(c, 0)))
            features[f"{c}_roc"] = float(raw.get(c, 0)) - prev
            self._prev_vals[c] = float(raw.get(c, 0))

        # ── Statistical (rolling window) ──────────────────────────────────────
        for c in self.sensor_cols:
            buf = np.array(self._roll_bufs[c])
            mu  = buf.mean()
            sig = buf.std() + 1e-9
            val = float(raw.get(c, 0))
            features[f"{c}_roll_mean"]   = mu
            features[f"{c}_roll_std"]    = sig
            features[f"{c}_roll_zscore"] = (val - mu) / sig

        # ── Lag features ──────────────────────────────────────────────────────
        lags    = cfg.get("LAG_STEPS", [5, 10, 30])
        lagcols = cfg.get("LAG_COLS", [])
        for c in lagcols:
            self._lag_bufs[c].append(float(raw.get(c, 0)))
            buf = self._lag_bufs[c]
            for lag in lags:
                key = f"{c}_lag{lag}"
                if len(buf) > lag:
                    features[key] = buf[-lag - 1]
                else:
                    features[key] = buf[0] if buf else 0.0

        # ── Build feature vector (aligned to training feature_cols) ───────────
        vec = np.array(
            [features.get(col, 0.0) for col in self.feature_cols],
            dtype=np.float32,
        )

        # ── Scale ─────────────────────────────────────────────────────────────
        if self.scaler is not None:
            vec = self.scaler.transform(vec.reshape(1, -1))[0].astype(np.float32)

        return vec


# =============================================================================
# INFERENCE ENGINE  (individual model loading, 4-layer ensemble)
# =============================================================================

class InferenceEngine:
    """
    Loads individual model files and runs the 4-layer ensemble pipeline.

    Layer 1a: IsolationForest  → anomaly score
    Layer 1b: Autoencoder      → reconstruction error
    Layer 2:  XGBoost          → attack probability (on augmented 246-dim features)
    Layer 3:  CNN-BiLSTM       → attack probability (on 150-step sequences)

    Final: weighted ensemble of all four scores.
    """

    def __init__(self, models_dir: str = "models") -> None:
        self.models_dir = Path(models_dir)
        self.config: dict[str, Any] = {}
        self.scaler = None
        self.label_encoder = None
        self.feature_engine: FeatureEngine | None = None

        # Individual models (None = not loaded / demo fallback)
        self.isolation_forest = None
        self.autoencoder = None
        self.xgb_model = None
        self.cnn_lstm = None

        # Sequence buffer for CNN-BiLSTM
        self._seq_buffer: deque = deque(maxlen=150)

        # Device for PyTorch models
        self._device = "cpu"

        # Track which layers are in demo fallback
        self._layer_status: dict[str, str] = {
            "layer1a_if": "not_loaded",
            "layer1b_ae": "not_loaded",
            "layer2_xgb": "not_loaded",
            "layer3_cnn": "not_loaded",
        }

    def load(self) -> bool:
        """
        Load all model components individually.
        Returns True if at least one model loaded successfully.
        """
        if not JOBLIB_AVAILABLE:
            log.error("joblib not available — cannot load models")
            return False

        models = self.models_dir
        if not models.exists():
            log.error(f"Models directory not found: {models}")
            return False

        # 1. Pipeline config
        cfg_path = models / "pipeline_config.joblib"
        if cfg_path.exists():
            try:
                self.config = joblib.load(cfg_path)
                log.info(f"  Pipeline config loaded: {len(self.config)} keys")
            except Exception as e:
                log.warning(f"  Failed to load pipeline_config.joblib: {e}")
                self.config = dict(DEFAULT_PIPELINE_CONFIG)
        else:
            log.warning("  pipeline_config.joblib not found — using defaults")
            self.config = dict(DEFAULT_PIPELINE_CONFIG)

        # Merge any missing keys from defaults
        for k, v in DEFAULT_PIPELINE_CONFIG.items():
            self.config.setdefault(k, v)

        # 2. Scaler
        scaler_path = models / "scaler.joblib"
        if scaler_path.exists():
            try:
                self.scaler = joblib.load(scaler_path)
                log.info("  Scaler loaded (RobustScaler)")
            except Exception as e:
                log.warning(f"  Failed to load scaler.joblib: {e}")

        # 3. Label encoder
        le_path = models / "label_encoder.joblib"
        if le_path.exists():
            try:
                self.label_encoder = joblib.load(le_path)
                log.info(f"  Label encoder loaded ({len(self.label_encoder.classes_)} classes)")
            except Exception as e:
                log.warning(f"  Failed to load label_encoder.joblib: {e}")

        # 4. Layer 1a — IsolationForest
        if_path = models / "layer1a_if.joblib"
        if if_path.exists():
            try:
                self.isolation_forest = joblib.load(if_path)
                self._layer_status["layer1a_if"] = "loaded"
                log.info("  Layer 1a: IsolationForest loaded ✅")
            except Exception as e:
                log.warning(f"  Layer 1a: IsolationForest failed — {e} (demo fallback)")
                self._layer_status["layer1a_if"] = "demo_fallback"
        else:
            log.warning("  Layer 1a: layer1a_if.joblib not found (demo fallback)")
            self._layer_status["layer1a_if"] = "demo_fallback"

        # 5. Layer 1b — Autoencoder (PyTorch)
        if TORCH_AVAILABLE:
            ae_input_dim = self.config.get("AE_INPUT_DIM", 245)
            for ae_name in ["layer1b_autoencoder.pt", "layer1b_autoencoder_best_v5.pt"]:
                ae_path = models / ae_name
                if ae_path.exists():
                    try:
                        self.autoencoder = SWaTAutoencoder(ae_input_dim)
                        state = torch.load(ae_path, map_location="cpu", weights_only=False)
                        self.autoencoder.load_state_dict(state)
                        self.autoencoder.eval()
                        self._layer_status["layer1b_ae"] = "loaded"
                        log.info(f"  Layer 1b: Autoencoder loaded from {ae_name} ✅")
                        break
                    except Exception as e:
                        log.warning(f"  Layer 1b: Failed to load {ae_name} — {e}")
                        self.autoencoder = None

            if self.autoencoder is None:
                log.warning("  Layer 1b: No autoencoder loaded (demo fallback)")
                self._layer_status["layer1b_ae"] = "demo_fallback"
        else:
            log.warning("  Layer 1b: PyTorch not available (demo fallback)")
            self._layer_status["layer1b_ae"] = "demo_fallback"

        # 6. Layer 2 — XGBoost
        xgb_path = models / "layer2_xgb.joblib"
        if xgb_path.exists():
            try:
                self.xgb_model = joblib.load(xgb_path)
                self._layer_status["layer2_xgb"] = "loaded"
                log.info("  Layer 2: XGBoost loaded ✅")
            except Exception as e:
                log.warning(f"  Layer 2: XGBoost failed — {e} (demo fallback)")
                self._layer_status["layer2_xgb"] = "demo_fallback"
        else:
            log.warning("  Layer 2: layer2_xgb.joblib not found (demo fallback)")
            self._layer_status["layer2_xgb"] = "demo_fallback"

        # 7. Layer 3 — CNN-BiLSTM (PyTorch)
        if TORCH_AVAILABLE:
            n_feat  = self.config.get("N_FEATURES", 244)
            seq_len = self.config.get("SEQ_LEN", 150)
            for cnn_name in ["layer3_cnn_lstm.pt", "layer3_cnn_lstm_best.pt"]:
                cnn_path = models / cnn_name
                if cnn_path.exists():
                    try:
                        self.cnn_lstm = SWaTCNNBiLSTM(n_feat, seq_len)
                        state = torch.load(cnn_path, map_location="cpu", weights_only=False)
                        self.cnn_lstm.load_state_dict(state)
                        self.cnn_lstm.eval()
                        self._layer_status["layer3_cnn"] = "loaded"
                        log.info(f"  Layer 3: CNN-BiLSTM loaded from {cnn_name} ✅")
                        break
                    except Exception as e:
                        log.warning(f"  Layer 3: Failed to load {cnn_name} — {e}")
                        self.cnn_lstm = None

            if self.cnn_lstm is None:
                log.warning("  Layer 3: No CNN-BiLSTM loaded (demo fallback)")
                self._layer_status["layer3_cnn"] = "demo_fallback"
        else:
            log.warning("  Layer 3: PyTorch not available (demo fallback)")
            self._layer_status["layer3_cnn"] = "demo_fallback"

        # Initialise feature engine
        self.feature_engine = FeatureEngine(self.config)
        self.feature_engine.scaler = self.scaler

        # Update sequence buffer length
        self._seq_buffer = deque(maxlen=self.config.get("SEQ_LEN", 150))

        loaded_count = sum(1 for s in self._layer_status.values() if s == "loaded")
        log.info(f"  Models loaded: {loaded_count}/4 layers active")
        log.info(f"  Layer status: {self._layer_status}")

        return loaded_count > 0

    def infer(self, raw: dict) -> dict | None:
        """
        Run one sensor frame through the full 4-layer ensemble.

        Returns dict with ML inference results, or None if feature engine
        not yet warmed up.
        """
        if self.feature_engine is None:
            return None

        vec = self.feature_engine.process(raw)
        if vec is None:
            return None

        cfg = self.config
        n_features = cfg.get("N_FEATURES", 244)

        # ── Layer 1a: IsolationForest ─────────────────────────────────────────
        if self.isolation_forest is not None:
            try:
                raw_score = self.isolation_forest.decision_function(
                    vec[:n_features].reshape(1, -1)
                )[0]
                # Negate and normalize: more negative = more anomalous
                if_score = float(np.clip(-raw_score, 0.0, 1.0))
            except Exception:
                if_score = 0.0
        else:
            if_score = 0.0

        # ── Layer 1b: Autoencoder reconstruction error ────────────────────────
        if self.autoencoder is not None and TORCH_AVAILABLE:
            try:
                ae_input_dim = cfg.get("AE_INPUT_DIM", 245)
                ae_vec = vec[:ae_input_dim]
                with torch.no_grad():
                    x_t = torch.tensor(ae_vec, dtype=torch.float32).unsqueeze(0)
                    recon = self.autoencoder(x_t)
                    mse = F.mse_loss(recon, x_t, reduction="mean").item()

                ae_perc = cfg.get("AE_THRESHOLD_PERC", 0.0114)
                ae_score = float(np.clip(mse / max(ae_perc, 1e-9), 0.0, 1.0))
            except Exception:
                ae_score = 0.0
        else:
            ae_score = 0.0

        # ── Layer 2: XGBoost (augmented features: base + IF + AE scores) ─────
        if self.xgb_model is not None:
            try:
                augmented = np.concatenate([
                    vec[:n_features],
                    np.array([if_score, ae_score], dtype=np.float32),
                ])
                # XGBoost predict_proba -> attack probability
                proba = self.xgb_model.predict_proba(augmented.reshape(1, -1))
                # Binary: take probability of attack class (index 1 or last)
                xgb_prob = float(proba[0, -1]) if proba.shape[1] > 1 else float(proba[0, 0])
            except Exception:
                xgb_prob = 0.0
        else:
            xgb_prob = 0.0

        # ── Layer 3: CNN-BiLSTM (sequence of 150 steps) ──────────────────────
        self._seq_buffer.append(vec[:n_features].copy())
        seq_len = cfg.get("SEQ_LEN", 150)

        if self.cnn_lstm is not None and TORCH_AVAILABLE and len(self._seq_buffer) >= seq_len:
            try:
                seq = np.array(list(self._seq_buffer), dtype=np.float32)
                with torch.no_grad():
                    x_t = torch.tensor(seq, dtype=torch.float32).unsqueeze(0)
                    cnn_prob = float(self.cnn_lstm(x_t).item())
            except Exception:
                cnn_prob = 0.0
        else:
            cnn_prob = 0.0

        # ── Ensemble ──────────────────────────────────────────────────────────
        weights = cfg.get("ENS_WEIGHTS", [0.00655, 0.00049, 0.9488, 0.0441])
        ens_threshold = cfg.get("ENS_THRESHOLD", 0.7071)

        scores = [if_score, ae_score, xgb_prob, cnn_prob]
        weighted_sum = sum(w * s for w, s in zip(weights, scores))
        is_attack = weighted_sum >= ens_threshold

        # Layer-level flags
        if_threshold  = cfg.get("IF_THRESHOLD", 0.4)
        xgb_threshold = cfg.get("XGB_THRESHOLD", 0.2696)
        cnn_threshold = cfg.get("CNN_THRESHOLD", 9.06e-06)
        ae_threshold  = cfg.get("AE_THRESHOLD", 1.0)

        layer1_flag = int(if_score >= if_threshold or ae_score >= ae_threshold)
        layer2_flag = int(xgb_prob >= xgb_threshold)
        layer3_flag = int(cnn_prob >= cnn_threshold)

        vote_sum = layer1_flag + layer2_flag + layer3_flag
        layer1_combined = max(if_score, ae_score)

        return {
            "is_attack":    is_attack,
            "attack_prob":  round(float(weighted_sum), 6),
            "attack_name":  "Multi-Stage Attack" if is_attack else "Normal",
            "verdict":      "ATTACK" if is_attack else "NORMAL",
            "layer1_score": round(float(layer1_combined), 6),
            "layer1_flag":  layer1_flag,
            "layer2_prob":  round(float(xgb_prob), 6),
            "layer2_flag":  layer2_flag,
            "layer3_prob":  round(float(cnn_prob), 6),
            "layer3_flag":  layer3_flag,
            "vote_sum":     vote_sum,
        }


# =============================================================================
# DEMO MODE — Manual Inject/Clear from Dashboard
# =============================================================================
# No auto-cycling.  Starts in NORMAL.  Only changes state when the user clicks
# "Inject Attack" or "Clear / Return to Normal" on the dashboard sidebar.
# Each attack type produces distinct, realistic sensor effects.

# ── Per-attack-type sensor deltas ────────────────────────────────────────────
# Keys = sensor names, values = delta added to normal at full intensity (1.0).
# Only sensors listed here change; everything else stays at normal values.

ATTACK_PROFILES: dict[str, dict] = {
    "Sensor Spoofing": {
        "description": "Attacker spoofs LIT-101 to show tank overfill",
        "sensor_deltas": {
            "LIT_101": 430.0,     # 500 → 930  (spoofed high)
            "LIT_301": -80.0,     # 800 → 720
            "PIT_501": 350.0,     # 1500 → 1850
            "FIT_101": -0.8,      # 2.0 → 1.2
            "DPIT_301": 25.0,     # 30 → 55
        },
        "binary_overrides": {
            "High_Level_Alarm": 1,
        },
    },

    "pH Manipulation": {
        "description": "Acid injection attack — pH drops dangerously low",
        "sensor_deltas": {
            "AIT_202": -280.0,    # 720 → 440  → pH = 4.4 (< 5!)
            "AIT_402": -200.0,    # 680 → 480
            "Chlorine_Residual": -22.0,  # 35 → 13
            "LIT_101": 30.0,      # slight rise
            "FIT_201": -0.5,      # dosing flow affected
        },
        "binary_overrides": {
            "P_203": 0,           # acid dosing pump forced off
            "Chemical_Low_Alarm": 1,
        },
    },

    "Slow Ramp": {
        "description": "Tank LIT-101 slowly fills — level ramps up over time",
        "sensor_deltas": {
            "LIT_101": 480.0,     # 500 → 980  (overflows slowly)
            "LIT_301": 120.0,     # 800 → 920
            "FIT_101": 0.6,       # flow slightly higher
            "PIT_501": 150.0,     # pressure rising
            "DPIT_301": 15.0,     # differential pressure rising
        },
        "binary_overrides": {
            "MV_101": 1,          # valve stuck open
            "High_Level_Alarm": 1,
        },
        "slow_ramp": True,        # special: intensity ramps 0→1 over 15s
    },

    "Pump Failure": {
        "description": "P-101 pump fails — flow drops to near zero",
        "sensor_deltas": {
            "FIT_101": -1.95,     # 2.0 → 0.05 (near zero)
            "FIT_201": -1.2,      # 1.8 → 0.6
            "FIT_301": -0.9,      # 1.5 → 0.6
            "LIT_101": -120.0,    # 500 → 380 (tank draining)
            "LIT_301": -200.0,    # 800 → 600 (drops)
            "DPIT_301": -20.0,    # 30 → 10 (pressure drop)
        },
        "binary_overrides": {
            "P_101": 0,           # pump OFF
            "P_102": 0,           # backup also off
        },
    },

    "Valve Manipulation": {
        "description": "MV-101 forced closed — blocks water flow",
        "sensor_deltas": {
            "FIT_101": -1.8,      # 2.0 → 0.2
            "FIT_201": -1.0,      # 1.8 → 0.8
            "LIT_101": 200.0,     # 500 → 700 (water backs up)
            "PIT_501": 300.0,     # 1500 → 1800 (pressure rises)
            "PIT_502": 200.0,     # pressure rises
            "DPIT_301": 40.0,     # 30 → 70 (diff pressure spikes)
        },
        "binary_overrides": {
            "MV_101": 0,          # valve CLOSED
            "MV_201": 0,          # downstream also closed
            "High_Pressure_Alarm": 1,
        },
    },

    "Multi-Stage": {
        "description": "Combined pump + pH + sensor attack",
        "sensor_deltas": {
            "LIT_101": 400.0,     # 500 → 900
            "AIT_202": -250.0,    # 720 → 470  (pH ~4.7)
            "FIT_101": -1.6,      # 2.0 → 0.4
            "FIT_201": -1.0,
            "PIT_501": 380.0,     # 1500 → 1880
            "DPIT_301": 50.0,     # 30 → 80
            "Chlorine_Residual": -25.0,  # 35 → 10
            "LIT_301": -150.0,    # 800 → 650
        },
        "binary_overrides": {
            "P_101": 0,
            "MV_101": 0,
            "High_Level_Alarm": 1,
            "High_Pressure_Alarm": 1,
            "Chemical_Low_Alarm": 1,
        },
    },

    "DoS Attack": {
        "description": "Network flood — sensor readings freeze/jitter",
        "sensor_deltas": {
            "FIT_101": -0.3,      # slight flow instability
            "FIT_201": -0.2,
            "LIT_101": 15.0,      # minor drift
            "DPIT_301": 10.0,
            "PIT_501": 80.0,
        },
        "binary_overrides": {},
    },

    "Normal": {
        "description": "Normal operation",
        "sensor_deltas": {},
        "binary_overrides": {},
    },
}

# Fallback profile for unknown attack names
_DEFAULT_ATTACK_PROFILE = {
    "description": "Generic attack",
    "sensor_deltas": {
        "LIT_101": 300.0,
        "FIT_101": -1.0,
        "PIT_501": 250.0,
        "AIT_202": -150.0,
    },
    "binary_overrides": {"P_101": 0},
}

# Transition speed (seconds to ramp from 0→1 or 1→0)
TRANSITION_SECONDS = 3.0

# Slow Ramp specific: how long for the ramp to reach full intensity
SLOW_RAMP_SECONDS = 15.0


class DemoSimulator:
    """
    Generates realistic SWaT sensor data and simulated ML inference results.

    Starts in NORMAL mode.  Only changes when inject_attack() / clear_attack()
    are called from the dashboard.  Each attack type has distinct sensor effects.
    """

    # Normal operating values for key sensors
    NORMAL_VALUES: dict[str, float] = {
        "LIT_101": 500.0,   "LIT_301": 800.0,   "LIT_401": 600.0,
        "LIT_501": 400.0,   "FIT_101": 2.0,     "FIT_201": 1.8,
        "FIT_301": 1.5,     "FIT_401": 1.3,     "FIT_501": 1.1,
        "FIT_601": 0.9,     "DPIT_301": 30.0,   "PIT_501": 1500.0,
        "PIT_502": 1400.0,  "PIT_503": 1300.0,  "AIT_201": 200.0,
        "AIT_202": 720.0,   "AIT_203": 500.0,   "AIT_401": 1.5,
        "AIT_402": 680.0,   "AIT_501": 50.0,    "AIT_502": 350.0,
        "AIT_503": 10.0,    "AIT_504": 710.0,   "FIT_502": 0.8,
        "FIT_503": 0.6,     "FIT_504": 0.4,     "Chlorine_Residual": 35.0,
        "Turbidity_Raw": 150.0,  "Turbidity_UF": 50.0,
        "Water_Temperature": 250.0,  "Ambient_Temperature": 280.0,
        "TDS_Feed": 500.0,  "TDS_Permeate": 20.0,
        "Acid_Tank_Level": 85.0,     "Chlorine_Tank_Level": 80.0,
        "Coagulant_Tank_Level": 75.0, "Bisulfate_Tank_Level": 70.0,
        "UF_Runtime": 3600.0,  "UF_Fouling_Factor": 15.0,
        "UF_Last_Backwash": 300.0,   "RO_Runtime": 7200.0,
        "RO_Fouling_Factor": 10.0,   "RO_Last_Cleaning": 600.0,
    }

    # Normal binary states
    NORMAL_BINARY: dict[str, int] = {
        "P_101": 1, "P_102": 0, "P_201": 1, "P_202": 0,
        "P_203": 1, "P_204": 0, "P_205": 1, "P_206": 0,
        "P_301": 1, "P_302": 0, "P_401": 1, "P_402": 0,
        "P_403": 0, "P_404": 0, "P_501": 1, "P_502": 0,
        "P_601": 1, "P_602": 0, "P_603": 0,
        "UV_401": 1,
        "MV_101": 1, "MV_201": 1, "MV_301": 1, "MV_302": 0,
        "MV_303": 0, "MV_304": 0, "MV_501": 1,
        "UF_Backwash_Active": 0, "RO_Cleaning_Active": 0,
        "Chemical_Low_Alarm": 0, "High_Fouling_Alarm": 0,
        "Energy_Monitor_Enable": 1, "High_Level_Alarm": 0,
        "High_Pressure_Alarm": 0, "System_Run": 1,
    }

    def __init__(self) -> None:
        self._msg_count  = 0
        # Per-sensor noise state for smooth variation
        self._noise_state: dict[str, float] = {}

        # ── Attack state ──────────────────────────────────────────
        self._current_attack: str | None = None   # None = Normal
        self._attack_profile: dict = ATTACK_PROFILES["Normal"]
        self._inject_time: float | None = None    # when attack was injected
        self._clear_time: float | None = None     # when clear was pressed
        self._intensity: float = 0.0              # current interpolated intensity
        self._is_slow_ramp: bool = False           # Slow Ramp special mode

    # ── Public API (called from dashboard_handler) ────────────────────────────

    def inject_attack(self, attack_name: str) -> None:
        """Start an attack — called when user clicks Inject on dashboard."""
        if attack_name == "Normal":
            self.clear_attack()
            return

        profile = ATTACK_PROFILES.get(attack_name, _DEFAULT_ATTACK_PROFILE)
        self._current_attack = attack_name
        self._attack_profile = profile
        self._inject_time = time.time()
        self._clear_time = None
        self._is_slow_ramp = profile.get("slow_ramp", False)
        log.info(f"[DEMO] Attack injected: {attack_name} — {profile.get('description', '')}")

    def clear_attack(self) -> None:
        """Return to normal — called when user clicks Clear on dashboard."""
        if self._current_attack is not None:
            log.info(f"[DEMO] Attack cleared: {self._current_attack} → Normal")
            self._clear_time = time.time()
            self._current_attack = None
            self._is_slow_ramp = False

    # ── Intensity computation ─────────────────────────────────────────────────

    def _compute_intensity(self) -> float:
        """
        Compute current attack intensity (0.0 = normal, 1.0 = full attack).
        Smoothly transitions over TRANSITION_SECONDS.
        Slow Ramp mode: ramps gradually over SLOW_RAMP_SECONDS.
        """
        now = time.time()

        if self._current_attack is not None and self._inject_time is not None:
            # Attacking — ramp UP
            elapsed = now - self._inject_time
            if self._is_slow_ramp:
                # Slow ramp: gradually 0→1 over SLOW_RAMP_SECONDS
                raw = min(1.0, elapsed / SLOW_RAMP_SECONDS)
            else:
                # Normal attack: quick 0→1 over TRANSITION_SECONDS
                raw = min(1.0, elapsed / TRANSITION_SECONDS)
            self._intensity = _smooth_ramp(raw)

        elif self._clear_time is not None:
            # Clearing — ramp DOWN
            elapsed = now - self._clear_time
            ramp_down = min(1.0, elapsed / TRANSITION_SECONDS)
            self._intensity = max(0.0, self._intensity * (1.0 - _smooth_ramp(ramp_down)))

            # Fully cleared
            if ramp_down >= 1.0:
                self._intensity = 0.0
                self._clear_time = None
                self._attack_profile = ATTACK_PROFILES["Normal"]

        else:
            # No attack, no clearing — normal
            self._intensity = max(0.0, self._intensity * 0.95)  # decay any residual

        return self._intensity

    # ── Noise generation ──────────────────────────────────────────────────────

    def _get_sensor_noise(self, key: str, scale: float = 1.0) -> float:
        """Smooth, correlated noise per sensor (exponential smoothing)."""
        alpha = 0.15
        innovation = random.gauss(0, scale)
        prev = self._noise_state.get(key, 0.0)
        smoothed = alpha * innovation + (1 - alpha) * prev
        self._noise_state[key] = smoothed
        return smoothed

    # ── Frame generation (called at 10 Hz) ────────────────────────────────────

    def generate_frame(self) -> dict:
        """Generate one complete sensor + ML inference payload for the dashboard."""
        self._msg_count += 1
        intensity = self._compute_intensity()
        profile = self._attack_profile
        sensor_deltas = profile.get("sensor_deltas", {})
        binary_overrides = profile.get("binary_overrides", {})

        # ── Build sensor data ─────────────────────────────────────────────────
        sensor_data: dict[str, float] = {}

        # Continuous sensors
        for key, normal_val in self.NORMAL_VALUES.items():
            delta = sensor_deltas.get(key, 0.0) * intensity
            noise_scale = abs(normal_val) * 0.003 + 0.01
            noise = self._get_sensor_noise(key, noise_scale)
            sensor_data[key] = round(normal_val + delta + noise, 2)

        # Binary sensors (pumps, valves, alarms)
        for key, normal_val in self.NORMAL_BINARY.items():
            if key in binary_overrides and intensity > 0.5:
                sensor_data[key] = binary_overrides[key]
            else:
                sensor_data[key] = normal_val

        # ── Simulate ML inference ─────────────────────────────────────────────
        ml_result = self._simulate_ml_result(intensity)

        # Select sensors to send to dashboard
        ml_result["sensor_data"] = {
            k: sensor_data[k]
            for k in [
                "LIT_101", "LIT_301", "LIT_401", "LIT_501",
                "AIT_202", "AIT_203", "FIT_101", "FIT_201",
                "FIT_301", "DPIT_301", "PIT_501", "PIT_502",
                "P_101", "P_102", "P_301", "P_501",
                "MV_101", "MV_201", "MV_301", "MV_501",
                "Chlorine_Residual",
            ]
            if k in sensor_data
        }
        ml_result["ready"]     = True
        ml_result["timestamp"] = time.strftime("%H:%M:%S")
        ml_result["msg_count"] = self._msg_count

        return ml_result

    def _simulate_ml_result(self, intensity: float) -> dict:
        """
        Generate realistic ML layer scores from attack intensity.
        intensity = 0 → all scores ≈ 0 (normal)
        intensity = 1 → all layers flag (attack)
        """
        # Layer 1 (IF) — responds first, most sensitive
        l1_base = intensity * 0.92
        l1_noise = self._get_sensor_noise("ml_l1", 0.02)
        layer1_score = float(np.clip(l1_base + l1_noise, 0.0, 1.0))

        # Layer 2 (XGB) — slightly delayed, high confidence when active
        l2_raw = max(0.0, intensity - 0.08) / 0.92
        l2_base = l2_raw * 0.95
        l2_noise = self._get_sensor_noise("ml_l2", 0.015)
        layer2_prob = float(np.clip(l2_base + l2_noise, 0.0, 1.0))

        # Layer 3 (CNN-LSTM) — needs sequence buildup, responds last
        l3_raw = max(0.0, intensity - 0.15) / 0.85
        l3_base = l3_raw * 0.88
        l3_noise = self._get_sensor_noise("ml_l3", 0.018)
        layer3_prob = float(np.clip(l3_base + l3_noise, 0.0, 1.0))

        # Layer flags (using real thresholds)
        layer1_flag = int(layer1_score >= 0.4)
        layer2_flag = int(layer2_prob >= 0.2696)
        layer3_flag = int(layer3_prob >= 0.01)

        # Ensemble weighted sum (using real weights from pipeline config)
        weights = DEFAULT_PIPELINE_CONFIG["ENS_WEIGHTS"]
        ens_threshold = DEFAULT_PIPELINE_CONFIG["ENS_THRESHOLD"]
        attack_prob = (
            weights[0] * layer1_score
            + weights[1] * layer1_score   # AE ≈ IF in demo
            + weights[2] * layer2_prob
            + weights[3] * layer3_prob
        )
        is_attack = attack_prob >= ens_threshold

        vote_sum = layer1_flag + layer2_flag + layer3_flag

        # Determine attack name for display
        if is_attack and self._current_attack:
            attack_name = self._current_attack
        elif intensity > 0.3 and self._current_attack:
            attack_name = self._current_attack
        else:
            attack_name = "Normal"

        return {
            "is_attack":    is_attack,
            "attack_prob":  round(attack_prob, 6),
            "attack_name":  attack_name,
            "verdict":      "ATTACK" if is_attack else "NORMAL",
            "layer1_score": round(layer1_score, 6),
            "layer1_flag":  layer1_flag,
            "layer2_prob":  round(layer2_prob, 6),
            "layer2_flag":  layer2_flag,
            "layer3_prob":  round(layer3_prob, 6),
            "layer3_flag":  layer3_flag,
            "vote_sum":     vote_sum,
        }


def _smooth_ramp(t: float) -> float:
    """
    Smooth sigmoid ramp from 0 to 1 as t goes from 0 to 1.
    Uses a logistic function for natural transitions.
    """
    t = max(0.0, min(1.0, t))
    return 1.0 / (1.0 + math.exp(-10.0 * (t - 0.5)))


# =============================================================================
# ATTACK INJECTION via Modbus (CODESYS)
# =============================================================================

ATTACK_INJECTION_MAP: dict[str, list[tuple[str, int, int]]] = {
    "Sensor Spoofing":    [("holding", 0, 9999)],
    "pH Manipulation":    [("holding", 5, 300)],
    "Slow Ramp":          [("holding", 0, 600)],
    "Pump Failure":       [("coil", 0, 0)],
    "Valve Manipulation": [("coil", 4, 0)],
    "Multi-Stage":        [("coil", 0, 0), ("holding", 5, 300)],
    "Reconnaissance":     [],
    "Replay Attack":      [],
    "DoS Attack":         [],
    "Covert Channel":     [],
    "Normal":             [],
}


class AttackInjector:
    """Sends Modbus writes to CODESYS to inject / clear attacks."""

    def __init__(self, host: str, port: int, enabled: bool = True) -> None:
        self.host    = host
        self.port    = port
        self.enabled = enabled
        self._client = None

    def _connect(self) -> None:
        try:
            from pymodbus.client import ModbusTcpClient
            self._client = ModbusTcpClient(self.host, port=self.port, timeout=3)
            self._client.connect()
            log.info(f"Modbus connected to {self.host}:{self.port}")
        except Exception as e:
            log.warning(f"Modbus connect failed: {e}")
            self._client = None

    def inject(self, attack_name: str) -> bool:
        if not self.enabled:
            log.info(f"[SAFE MODE] Attack injection disabled. Would inject: {attack_name}")
            return True
        if self._client is None:
            self._connect()
        if self._client is None:
            return False

        ops = ATTACK_INJECTION_MAP.get(attack_name, [])
        for reg_type, addr, val in ops:
            try:
                if reg_type == "coil":
                    self._client.write_coil(addr, bool(val))
                else:
                    self._client.write_register(addr, int(val))
            except Exception as e:
                log.warning(f"Modbus write failed ({reg_type} @{addr}={val}): {e}")
                return False

        log.info(f"Attack injected: {attack_name} ({len(ops)} Modbus writes)")
        return True

    def clear(self) -> bool:
        return self.inject("Normal")


# =============================================================================
# WEBSOCKET SERVER  (serves the dashboard on port 8766)
# =============================================================================

# Shared state between coroutines
_latest_ml_result: dict[str, Any] = {
    "ready":       False,
    "is_attack":   False,
    "attack_prob": 0.0,
    "attack_name": "Normal",
    "verdict":     "NORMAL",
    "layer1_score": 0.0,
    "layer1_flag": 0,
    "layer2_prob": 0.0,
    "layer2_flag": 0,
    "layer3_prob": 0.0,
    "layer3_flag": 0,
    "vote_sum":    0,
    "sensor_data": {},
    "timestamp":   "",
    "msg_count":   0,
}
_dashboard_clients: set = set()
_inference_engine: InferenceEngine | None = None
_attack_injector:  AttackInjector  | None = None
_demo_simulator:   DemoSimulator   | None = None
_is_demo_mode: bool = False


async def dashboard_handler(websocket) -> None:
    """Handle a single HTML dashboard client connection."""
    _dashboard_clients.add(websocket)
    addr = getattr(websocket, "remote_address", "?")
    log.info(f"Dashboard client connected: {addr}  (total: {len(_dashboard_clients)})")

    try:
        # Push current state immediately so the dashboard is not blank on load
        await websocket.send(json.dumps(_latest_ml_result))

        # Listen for commands from the dashboard
        async for raw_msg in websocket:
            try:
                cmd = json.loads(raw_msg)
                action = cmd.get("action", "")

                if action == "inject_attack":
                    attack_name = cmd.get("attack_name", "Normal")
                    log.info(f"Attack injection requested: {attack_name}")

                    if _is_demo_mode and _demo_simulator is not None:
                        # Demo mode: switch simulator to attack phase
                        _demo_simulator.inject_attack(attack_name)
                        ok = True
                    elif _attack_injector is not None:
                        ok = _attack_injector.inject(attack_name)
                    else:
                        ok = False

                    ack = {
                        "type": "ack",
                        "action": "inject_attack",
                        "attack_name": attack_name,
                        "success": ok,
                    }
                    await websocket.send(json.dumps(ack))

                elif action == "clear_attack":
                    log.info("Attack clear requested")

                    if _is_demo_mode and _demo_simulator is not None:
                        _demo_simulator.clear_attack()
                        ok = True
                    elif _attack_injector is not None:
                        ok = _attack_injector.clear()
                    else:
                        ok = False

                    ack = {"type": "ack", "action": "clear_attack", "success": ok}
                    await websocket.send(json.dumps(ack))

                elif action == "ping":
                    await websocket.send(json.dumps({"type": "pong"}))

            except json.JSONDecodeError:
                pass
            except Exception as e:
                log.warning(f"Error handling dashboard message: {e}")

    except websockets.exceptions.ConnectionClosedOK:
        pass
    except Exception as e:
        log.warning(f"Dashboard client error: {e}")
    finally:
        _dashboard_clients.discard(websocket)
        log.info(f"Dashboard client disconnected (remaining: {len(_dashboard_clients)})")


async def broadcast_to_dashboard(payload: dict) -> None:
    """Push an ML result to all connected dashboard clients."""
    global _dashboard_clients
    if not _dashboard_clients:
        return
    msg = json.dumps(payload)
    dead: set = set()
    for ws in list(_dashboard_clients):
        try:
            await ws.send(msg)
        except Exception:
            dead.add(ws)
    _dashboard_clients -= dead


# =============================================================================
# UPSTREAM DIGITAL TWIN CONSUMER  (subscribes to ws://localhost:8765)
# =============================================================================

# Sensors to forward to the dashboard
DASHBOARD_SENSOR_KEYS: list[str] = [
    "LIT_101", "LIT_301", "LIT_401", "LIT_501",
    "AIT_202", "AIT_203", "FIT_101", "FIT_201",
    "FIT_301", "DPIT_301", "PIT_501", "PIT_502",
    "P_101", "P_102", "P_301", "P_501",
    "MV_101", "MV_201", "MV_301", "MV_501",
    "Chlorine_Residual",
]


async def consume_digital_twin(src_ws_url: str) -> None:
    """
    Subscribe to the existing digital-twin WebSocket (ws_server.py on :8765),
    run each frame through the ML ensemble, and push results to dashboard clients.
    """
    global _latest_ml_result

    RECONNECT_DELAY = 5
    msg_count = 0

    log.info(f"Connecting to digital twin at {src_ws_url} ...")

    while True:
        try:
            async with websockets.connect(
                src_ws_url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
            ) as ws:
                log.info(f"Connected to digital twin: {src_ws_url}")

                async for raw_msg in ws:
                    try:
                        sensor_data = json.loads(raw_msg)
                    except json.JSONDecodeError:
                        continue

                    # Run ML inference
                    ml_result: dict | None = None
                    if _inference_engine is not None:
                        try:
                            ml_result = _inference_engine.infer(sensor_data)
                        except Exception as e:
                            log.warning(f"Inference error: {e}")

                    msg_count += 1

                    # Build payload for dashboard
                    payload: dict[str, Any] = {
                        "ready":     ml_result is not None,
                        "timestamp": time.strftime("%H:%M:%S"),
                        "msg_count": msg_count,
                        "sensor_data": {
                            k: sensor_data.get(k)
                            for k in DASHBOARD_SENSOR_KEYS
                            if sensor_data.get(k) is not None
                        },
                    }

                    if ml_result:
                        payload.update(ml_result)
                    else:
                        payload.update({
                            "is_attack":    False,
                            "attack_prob":  0.0,
                            "attack_name":  "Warming up...",
                            "verdict":      "NORMAL",
                            "layer1_score": 0.0,
                            "layer1_flag":  0,
                            "layer2_prob":  0.0,
                            "layer2_flag":  0,
                            "layer3_prob":  0.0,
                            "layer3_flag":  0,
                            "vote_sum":     0,
                        })

                    _latest_ml_result = payload
                    await broadcast_to_dashboard(payload)

        except (websockets.exceptions.ConnectionClosed,
                ConnectionRefusedError, OSError) as e:
            log.warning(
                f"Upstream WS disconnected: {e}. "
                f"Reconnecting in {RECONNECT_DELAY}s ..."
            )
            await asyncio.sleep(RECONNECT_DELAY)
        except Exception as e:
            log.error(f"Unexpected error in consume_digital_twin: {e}")
            await asyncio.sleep(RECONNECT_DELAY)


# =============================================================================
# DEMO MODE LOOP  (replaces consume_digital_twin when --demo is used)
# =============================================================================

async def demo_data_loop() -> None:
    """
    Generate simulated sensor data and ML inference at 10 Hz.
    Runs instead of the upstream WebSocket consumer in demo mode.
    """
    global _latest_ml_result

    if _demo_simulator is None:
        log.error("Demo simulator not initialised")
        return

    log.info("Demo data loop started — generating data at 10 Hz")
    log.info("Waiting for attack injection from dashboard...")

    interval = 0.1  # 100 ms = 10 Hz
    next_tick = time.monotonic()

    while True:
        try:
            payload = _demo_simulator.generate_frame()
            _latest_ml_result = payload
            await broadcast_to_dashboard(payload)
        except Exception as e:
            log.warning(f"Demo frame generation error: {e}")

        # Precise 10 Hz timing using monotonic clock
        next_tick += interval
        sleep_for = next_tick - time.monotonic()
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)
        else:
            # Fell behind — reset timing baseline
            next_tick = time.monotonic()


# =============================================================================
# MAIN
# =============================================================================

async def main_async(args: argparse.Namespace) -> None:
    global _inference_engine, _attack_injector, _demo_simulator, _is_demo_mode

    _is_demo_mode = args.demo

    if _is_demo_mode:
        # ── Demo mode: no models or upstream WS needed ────────────────────────
        log.info("=" * 60)
        log.info("  DEMO MODE — Simulated sensor data & ML inference")
        log.info("  No upstream WebSocket or model files required")
        log.info("=" * 60)
        _demo_simulator = DemoSimulator()
        _attack_injector = AttackInjector(
            host=args.plc_host, port=args.plc_port, enabled=False,
        )
    else:
        # ── Real mode: load models individually ───────────────────────────────
        log.info("Loading models individually from %s ...", args.models_dir)
        _inference_engine = InferenceEngine(models_dir=args.models_dir)
        success = _inference_engine.load()

        if not success:
            log.warning("No models loaded — ML inference will return zeros")

        # ── Set up attack injector ────────────────────────────────────────────
        _attack_injector = AttackInjector(
            host=args.plc_host,
            port=args.plc_port,
            enabled=not args.no_attack_inj,
        )

    # ── Start WebSocket server for the HTML dashboard (port 8766) ─────────────
    log.info(f"Starting ML inference WebSocket server on ws://0.0.0.0:{args.ml_port}")
    ml_server = await websockets.serve(
        dashboard_handler,
        "0.0.0.0",
        args.ml_port,
        ping_interval=20,
        ping_timeout=10,
    )

    log.info("─" * 60)
    log.info(f"ML server ready at  ws://localhost:{args.ml_port}")
    if _is_demo_mode:
        log.info("Mode: DEMO (simulated data)")
    else:
        log.info(f"Mode: REAL (upstream: {args.src_ws})")
    log.info("Open swat_ml_dashboard.html in your browser.")
    log.info("─" * 60)

    # ── Start the appropriate data loop ───────────────────────────────────────
    if _is_demo_mode:
        await asyncio.gather(
            demo_data_loop(),
            asyncio.Future(),   # run forever
        )
    else:
        await asyncio.gather(
            consume_digital_twin(args.src_ws),
            asyncio.Future(),   # run forever
        )

    ml_server.close()
    await ml_server.wait_closed()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SWaT Real-Time ML Inference WebSocket Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--plc-host", default="192.168.5.195",
        help="CODESYS PLC IP for attack injection (default: 192.168.5.195)",
    )
    parser.add_argument(
        "--plc-port", type=int, default=1502,
        help="CODESYS Modbus TCP port (default: 1502)",
    )
    parser.add_argument(
        "--src-ws", default="ws://localhost:8765",
        help="Upstream digital-twin WebSocket URL (default: ws://localhost:8765)",
    )
    parser.add_argument(
        "--ml-port", type=int, default=8766,
        help="ML inference WebSocket server port (default: 8766)",
    )
    parser.add_argument(
        "--models-dir", default="models",
        help="Path to saved models directory (default: models)",
    )
    parser.add_argument(
        "--no-attack-inj", action="store_true",
        help="Disable Modbus attack injection (safe mode, ML only)",
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Enable demo mode with simulated sensor data and ML inference",
    )

    args = parser.parse_args()

    mode_str = "DEMO" if args.demo else "REAL"
    log.info("SWaT Real-Time ML Inference Server")
    log.info(f"  Mode        : {mode_str}")
    if not args.demo:
        log.info(f"  Upstream WS : {args.src_ws}")
        log.info(f"  Models dir  : {args.models_dir}")
        log.info(f"  PLC host    : {args.plc_host}:{args.plc_port}")
        log.info(f"  Attack inj  : "
                 f'{"DISABLED (safe mode)" if args.no_attack_inj else "ENABLED"}')
    log.info(f"  ML port     : {args.ml_port}")

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        log.info("Shutdown requested.")


if __name__ == "__main__":
    main()
