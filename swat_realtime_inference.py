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
               │                                                         │
               │  FeatureEngine ──► SWaTEnsembleModel.predict_sample()  │
               │                                                         │
               │  serves ML results on  ws://0.0.0.0:8766              │
               │  also accepts attack commands from dashboard            │
               └─────────────────┬───────────────────────────────────────┘
                                 │ JSON ML results every 100 ms
               ┌─────────────────▼──────────────────────────┐
               │  swat_ml_dashboard.html (browser client)   │
               └────────────────────────────────────────────┘

Usage
-----
  # 1. Train models first (run swat_full_pipeline.py)
  # 2. Make sure ws_server.py is running (or start_system.py is running)
  # 3. Run this server:
  python swat_realtime_inference.py --plc-host 192.168.5.195 --plc-port 1502

  # 4. Open swat_ml_dashboard.html in a browser — it will connect automatically.

Arguments
---------
  --plc-host      CODESYS PLC IP (used for attack injection via Modbus)
  --plc-port      CODESYS Modbus port (default: 1502)
  --src-ws        Upstream digital-twin WebSocket URL (default: ws://localhost:8765)
  --ml-port       Port for the ML inference WebSocket server (default: 8766)
  --models-dir    Path to saved models directory (default: models)
  --no-attack-inj Disable Modbus attack injection (safe mode, ML only)
"""

import asyncio
import json
import logging
import argparse
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np
import joblib
import websockets

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('SWaT-ML')


# =============================================================================
# FEATURE ENGINE
# =============================================================================
# Stateful real-time feature engineering replicating the training pipeline.
# Accepts one raw sensor dict per call and returns a scaled feature vector.

class FeatureEngine:
    """
    Stateful real-time feature engine.

    Maintains rolling buffers for:
      - delta_t / jitter (temporal)
      - rolling mean / std per sensor (statistical)
      - lag values per lag column
      - previous sensor values (rate-of-change)
    """

    def __init__(self, config: dict):
        self.cfg          = config
        self.feature_cols = config['feature_cols']
        self.sensor_cols  = config['sensor_cols']
        self.scaler       = None           # set in InferenceEngine.load()
        self._last_ts     = None           # for delta_t
        self._dt_buf      = deque(maxlen=50)  # for rolling mean of delta_t
        EXPECTED_DT       = config['EXPECTED_DT']
        self._dt_buf.extend([EXPECTED_DT] * 50)

        W = config.get('ROLLING_WINDOW', 20)
        self._roll_bufs   = {c: deque(maxlen=W) for c in self.sensor_cols}

        lags    = config.get('LAG_STEPS', [5, 10, 30])
        lagcols = config.get('LAG_COLS',  [])
        maxlag  = max(lags) if lags else 30
        self._lag_bufs    = {c: deque(maxlen=maxlag + 1) for c in lagcols}

        self._prev_vals   = {}             # for rate-of-change
        self._prev_sensor = {}             # prev sensor values for PLC rules

    def process(self, raw: dict) -> np.ndarray | None:
        """
        Convert one raw sensor dict to a scaled numpy feature vector.
        Returns None until there is enough data (lag buffer warm-up).
        """
        cfg = self.cfg
        ts  = time.time()

        # ── Temporal ──────────────────────────────────────────────────────────
        dt = (ts - self._last_ts) if self._last_ts else cfg['EXPECTED_DT']
        self._last_ts = ts
        self._dt_buf.append(dt)
        dt_arr = np.array(self._dt_buf)
        dt_mean = dt_arr.mean()
        dt_roll = dt_mean
        dt_z    = (dt - cfg['dt_mean']) / cfg['dt_std']
        jitter  = abs(dt - dt_roll)

        features: dict = {
            'delta_t'              : dt,
            'delta_t_zscore'       : dt_z,
            'delta_t_rolling_mean' : dt_roll,
            'delay_anomaly'        : float(dt > 0.2),
            'delay_severe'         : float(dt > 0.5),
            'jitter'               : jitter,
            'jitter_high'          : float(jitter > 0.05),
        }

        # ── Raw sensor values ─────────────────────────────────────────────────
        for c in self.sensor_cols:
            v = float(raw.get(c, 0))
            features[c] = v
            self._roll_bufs[c].append(v)

        # ── Physical ──────────────────────────────────────────────────────────
        def _get(k): return float(raw.get(k, 0))

        for a, b in [('LIT_101','LIT_301'), ('LIT_301','LIT_401'), ('LIT_401','LIT_501')]:
            features[f'level_diff_{a}_{b}'] = _get(a) - _get(b)

        for a, b in [('FIT_101','FIT_201'), ('FIT_201','FIT_301'),
                     ('FIT_301','FIT_401'), ('FIT_401','FIT_501'), ('FIT_501','FIT_601')]:
            features[f'flow_balance_{a}_{b}'] = _get(a) - _get(b)

        features['pressure_spike'] = float(_get('PIT_501') > 1800)

        dpit = _get('DPIT_301')
        prev_dpit = self._prev_vals.get('DPIT_301', dpit)
        dpit_roc  = dpit - prev_dpit
        prev_dpit_roc = self._prev_vals.get('dpit_roc', dpit_roc)
        features['dpit_roc']  = dpit_roc
        features['dpit_roc2'] = dpit_roc - prev_dpit_roc
        self._prev_vals['DPIT_301'] = dpit
        self._prev_vals['dpit_roc'] = dpit_roc

        for ph_col in ['AIT_202', 'AIT_203', 'AIT_402']:
            v = _get(ph_col)
            features[f'{ph_col}_pH_deviation'] = float(v < 650 or v > 850)

        features['turbidity_high'] = float(_get('AIT_201') > 800)

        # ── Control / PLC rules ────────────────────────────────────────────────
        p101  = float(raw.get('P_101', 0))
        fit101= _get('FIT_101')
        features['pump_flow_inconsistency'] = float(p101 == 1 and fit101 < 0.05)

        features['ph_pump_inconsistency'] = float(
            _get('AIT_202') > 750 and float(raw.get('P_203', 0)) == 0
        )

        for mv_col, fit_col in [('MV_101','FIT_101'), ('MV_201','FIT_201'), ('MV_301','FIT_301')]:
            mv  = float(raw.get(mv_col, 0))
            fit = _get(fit_col)
            features[f'valve_flow_mismatch_{mv_col}'] = float(mv == 0 and fit > 0.1)

        # Pump duty cycles (approximated as rolling mean of recent state)
        for p_col in ['P_101', 'P_301', 'P_501']:
            pv = float(raw.get(p_col, 0))
            buf_key = f'duty_{p_col}'
            if buf_key not in self._prev_vals:
                self._prev_vals[buf_key] = deque([pv]*60, maxlen=60)
            self._prev_vals[buf_key].append(pv)
            features[f'{p_col}_duty_60'] = np.mean(self._prev_vals[buf_key])

        # Rate of change per sensor
        for c in self.sensor_cols:
            prev = self._prev_vals.get(c, float(raw.get(c, 0)))
            features[f'{c}_roc'] = float(raw.get(c, 0)) - prev
            self._prev_vals[c] = float(raw.get(c, 0))

        # ── Statistical (rolling window) ───────────────────────────────────────
        for c in self.sensor_cols:
            buf = np.array(self._roll_bufs[c])
            mu  = buf.mean()
            sig = buf.std() + 1e-9
            val = float(raw.get(c, 0))
            features[f'{c}_roll_mean'  ] = mu
            features[f'{c}_roll_std'   ] = sig
            features[f'{c}_roll_zscore'] = (val - mu) / sig

        # ── Lag features ───────────────────────────────────────────────────────
        lags    = cfg.get('LAG_STEPS', [5, 10, 30])
        lagcols = cfg.get('LAG_COLS', [])
        for c in lagcols:
            self._lag_bufs[c].append(float(raw.get(c, 0)))
            buf = self._lag_bufs[c]
            for lag in lags:
                key = f'{c}_lag{lag}'
                if len(buf) > lag:
                    features[key] = buf[-lag - 1]
                else:
                    features[key] = buf[0] if buf else 0.0

        # ── Build feature vector (aligned to training feature_cols) ─────────────
        vec = np.array(
            [features.get(col, 0.0) for col in self.feature_cols],
            dtype=np.float32
        )

        # ── Scale ─────────────────────────────────────────────────────────────
        if self.scaler is not None:
            vec = self.scaler.transform(vec.reshape(1, -1))[0].astype(np.float32)

        return vec


# =============================================================================
# INFERENCE ENGINE
# =============================================================================

class InferenceEngine:
    """Wraps the saved SWaTEnsembleModel for real-time use."""

    def __init__(self, models_dir: str = 'models'):
        self.models_dir = Path(models_dir)
        self.ensemble   = None
        self.feature_engine = None

    def load(self) -> None:
        log.info(f'Loading ensemble model from {self.models_dir} ...')
        self.ensemble = joblib.load(self.models_dir / 'ensemble_model.joblib')
        # Initialise feature engine with config from the ensemble
        cfg = self.ensemble.config
        self.feature_engine = FeatureEngine(cfg)
        self.feature_engine.scaler = self.ensemble.scaler
        log.info(f'  Feature cols  : {len(cfg["feature_cols"])}')
        log.info(f'  Classes       : {cfg["n_classes"]}')
        log.info(f'  IF threshold  : {cfg["IF_THRESHOLD"]:.3f}')
        log.info(f'  XGB threshold : {cfg["XGB_THRESHOLD"]:.3f}')
        log.info(f'  LSTM SEQ_LEN  : {cfg["SEQ_LEN"]}')
        log.info('Ensemble model loaded ✅')

    def infer(self, raw: dict) -> dict | None:
        """
        Run one sensor frame through the full 3-layer ensemble.

        Parameters
        ----------
        raw : dict   — Raw sensor values from the WebSocket (matching CODESYS registers)

        Returns
        -------
        dict with ML inference results, or None if feature engine not yet warmed up.
        """
        vec = self.feature_engine.process(raw)
        if vec is None:
            return None
        result = self.ensemble.predict_sample(vec)
        return result


# =============================================================================
# ATTACK INJECTION via Modbus (CODESYS)
# =============================================================================
# Maps attack names (from the dashboard dropdown) to Modbus write operations.
# Each attack overrides specific coils / holding registers in CODESYS.

ATTACK_INJECTION_MAP = {
    # attack_name : list of (register_type, address, value)
    # register_type: 'coil' or 'holding'
    'Sensor Spoofing'     : [('holding', 0,  9999)],   # LIT_101 spoofed high
    'pH Manipulation'     : [('holding', 5,  300)],    # AIT_202 spoofed low (acid attack)
    'Slow Ramp'           : [('holding', 0,  600)],    # LIT_101 slow ramp up
    'Pump Failure'        : [('coil',    0,  0)],      # P_101 coil OFF
    'Valve Manipulation'  : [('coil',    4,  0)],      # MV_101 coil OFF
    'Multi-Stage'         : [('coil',    0,  0),       # P_101 OFF
                              ('holding', 5, 300)],    # AIT_202 low
    'Reconnaissance'      : [],                        # passive — no coil write
    'Replay Attack'       : [],                        # handled by separate replay module
    'DoS Attack'          : [],                        # network layer only
    'Covert Channel'      : [],                        # network layer only
    'Normal'              : [],                        # clear all overrides
}


class AttackInjector:
    """Sends Modbus writes to CODESYS to inject / clear attacks."""

    def __init__(self, host: str, port: int, enabled: bool = True):
        self.host    = host
        self.port    = port
        self.enabled = enabled
        self._client = None

    def _connect(self):
        try:
            from pymodbus.client import ModbusTcpClient
            self._client = ModbusTcpClient(self.host, port=self.port, timeout=3)
            self._client.connect()
            log.info(f'Modbus connected to {self.host}:{self.port}')
        except Exception as e:
            log.warning(f'Modbus connect failed: {e}')
            self._client = None

    def inject(self, attack_name: str) -> bool:
        if not self.enabled:
            log.info(f'[SAFE MODE] Attack injection disabled. Would inject: {attack_name}')
            return True
        if self._client is None:
            self._connect()
        if self._client is None:
            return False

        ops = ATTACK_INJECTION_MAP.get(attack_name, [])
        for reg_type, addr, val in ops:
            try:
                if reg_type == 'coil':
                    self._client.write_coil(addr, bool(val))
                else:
                    self._client.write_register(addr, int(val))
            except Exception as e:
                log.warning(f'Modbus write failed ({reg_type} @{addr}={val}): {e}')
                return False

        log.info(f'Attack injected: {attack_name} ({len(ops)} Modbus writes)')
        return True

    def clear(self) -> bool:
        return self.inject('Normal')


# =============================================================================
# WEBSOCKET INFERENCE SERVER  (serves the HTML dashboard on port 8766)
# =============================================================================

# Shared state between coroutines
_latest_ml_result: dict = {
    'ready'       : False,
    'is_attack'   : False,
    'attack_prob' : 0.0,
    'attack_name' : 'Normal',
    'verdict'     : 'NORMAL',
    'layer1_score': 0.0,
    'layer1_flag' : 0,
    'layer2_prob' : 0.0,
    'layer2_flag' : 0,
    'layer3_prob' : 0.0,
    'layer3_flag' : 0,
    'vote_sum'    : 0,
    'sensor_data' : {},
    'timestamp'   : '',
    'msg_count'   : 0,
}
_dashboard_clients: set = set()
_inference_engine: InferenceEngine | None = None
_attack_injector:  AttackInjector  | None = None


async def dashboard_handler(websocket) -> None:
    """Handle a single HTML dashboard client connection."""
    _dashboard_clients.add(websocket)
    addr = getattr(websocket, 'remote_address', '?')
    log.info(f'Dashboard client connected: {addr}  (total: {len(_dashboard_clients)})')

    try:
        # Push current state immediately so the dashboard is not blank on load
        await websocket.send(json.dumps(_latest_ml_result))

        # Listen for attack commands from the dashboard
        async for raw_msg in websocket:
            try:
                cmd = json.loads(raw_msg)
                action = cmd.get('action', '')

                if action == 'inject_attack':
                    attack_name = cmd.get('attack_name', 'Normal')
                    log.info(f'Attack injection requested: {attack_name}')
                    ok = _attack_injector.inject(attack_name)
                    ack = {'type': 'ack', 'action': 'inject_attack',
                           'attack_name': attack_name, 'success': ok}
                    await websocket.send(json.dumps(ack))

                elif action == 'clear_attack':
                    log.info('Attack clear requested')
                    ok = _attack_injector.clear()
                    ack = {'type': 'ack', 'action': 'clear_attack', 'success': ok}
                    await websocket.send(json.dumps(ack))

                elif action == 'ping':
                    await websocket.send(json.dumps({'type': 'pong'}))

            except json.JSONDecodeError:
                pass
            except Exception as e:
                log.warning(f'Error handling dashboard message: {e}')

    except websockets.exceptions.ConnectionClosedOK:
        pass
    except Exception as e:
        log.warning(f'Dashboard client error: {e}')
    finally:
        _dashboard_clients.discard(websocket)
        log.info(f'Dashboard client disconnected (remaining: {len(_dashboard_clients)})')


async def broadcast_to_dashboard(payload: dict) -> None:
    """Push an ML result to all connected dashboard clients."""
    if not _dashboard_clients:
        return
    msg = json.dumps(payload)
    dead = set()
    for ws in list(_dashboard_clients):
        try:
            await ws.send(msg)
        except Exception:
            dead.add(ws)
    _dashboard_clients -= dead


# =============================================================================
# UPSTREAM DIGITAL TWIN CONSUMER  (subscribes to ws://localhost:8765)
# =============================================================================

async def consume_digital_twin(src_ws_url: str) -> None:
    """
    Subscribe to the existing digital-twin WebSocket (ws_server.py on :8765),
    run each frame through the ML ensemble, and push results to dashboard clients.
    """
    global _latest_ml_result

    RECONNECT_DELAY = 5   # seconds between reconnect attempts
    msg_count       = 0

    log.info(f'Connecting to digital twin at {src_ws_url} ...')

    while True:
        try:
            async with websockets.connect(
                src_ws_url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
            ) as ws:
                log.info(f'Connected to digital twin: {src_ws_url}')

                async for raw_msg in ws:
                    try:
                        sensor_data = json.loads(raw_msg)
                    except json.JSONDecodeError:
                        continue

                    # Run ML inference
                    try:
                        ml_result = _inference_engine.infer(sensor_data)
                    except Exception as e:
                        log.warning(f'Inference error: {e}')
                        ml_result = None

                    msg_count += 1

                    # Build payload for dashboard
                    payload = {
                        'ready'       : ml_result is not None,
                        'timestamp'   : time.strftime('%H:%M:%S'),
                        'msg_count'   : msg_count,
                        'sensor_data' : {
                            # Key sensors shown prominently in the dashboard
                            k: sensor_data.get(k)
                            for k in ['LIT_101', 'LIT_301', 'LIT_401', 'LIT_501',
                                      'AIT_202', 'AIT_203', 'FIT_101', 'FIT_201',
                                      'FIT_301', 'DPIT_301', 'PIT_501', 'PIT_502',
                                      'P_101', 'P_102', 'P_301', 'P_501',
                                      'MV_101', 'MV_201', 'MV_301', 'MV_501',
                                      'Chlorine_Residual']
                            if sensor_data.get(k) is not None
                        },
                    }

                    if ml_result:
                        payload.update(ml_result)
                    else:
                        # Warm-up period — LSTM buffer not yet full
                        payload.update({
                            'is_attack'   : False,
                            'attack_prob' : 0.0,
                            'attack_name' : 'Warming up...',
                            'verdict'     : 'NORMAL',
                            'layer1_score': 0.0,
                            'layer1_flag' : 0,
                            'layer2_prob' : 0.0,
                            'layer2_flag' : 0,
                            'layer3_prob' : 0.0,
                            'layer3_flag' : 0,
                            'vote_sum'    : 0,
                        })

                    _latest_ml_result = payload
                    await broadcast_to_dashboard(payload)

        except (websockets.exceptions.ConnectionClosed,
                ConnectionRefusedError, OSError) as e:
            log.warning(f'Upstream WS disconnected: {e}. Reconnecting in {RECONNECT_DELAY}s ...')
            await asyncio.sleep(RECONNECT_DELAY)
        except Exception as e:
            log.error(f'Unexpected error in consume_digital_twin: {e}')
            await asyncio.sleep(RECONNECT_DELAY)


# =============================================================================
# MAIN
# =============================================================================

async def main_async(args) -> None:
    global _inference_engine, _attack_injector

    # ── Load models ───────────────────────────────────────────────────────────
    _inference_engine = InferenceEngine(models_dir=args.models_dir)
    _inference_engine.load()

    # ── Set up attack injector ────────────────────────────────────────────────
    _attack_injector = AttackInjector(
        host    = args.plc_host,
        port    = args.plc_port,
        enabled = not args.no_attack_inj,
    )

    # ── Start WebSocket server for the HTML dashboard (port 8766) ─────────────
    log.info(f'Starting ML inference WebSocket server on ws://0.0.0.0:{args.ml_port}')
    ml_server = await websockets.serve(
        dashboard_handler,
        '0.0.0.0',
        args.ml_port,
        ping_interval=20,
        ping_timeout=10,
    )

    log.info('─' * 60)
    log.info(f'ML server ready at  ws://localhost:{args.ml_port}')
    log.info(f'Open swat_ml_dashboard.html in your browser.')
    log.info('─' * 60)

    # ── Start consuming digital twin stream ───────────────────────────────────
    await asyncio.gather(
        consume_digital_twin(args.src_ws),
        asyncio.Future(),   # run forever
    )

    ml_server.close()
    await ml_server.wait_closed()


def main() -> None:
    parser = argparse.ArgumentParser(
        description='SWaT Real-Time ML Inference WebSocket Server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--plc-host',      default='192.168.5.195',
                        help='CODESYS PLC IP for attack injection (default: 192.168.5.195)')
    parser.add_argument('--plc-port',      type=int, default=1502,
                        help='CODESYS Modbus TCP port (default: 1502)')
    parser.add_argument('--src-ws',        default='ws://localhost:8765',
                        help='Upstream digital-twin WebSocket URL (default: ws://localhost:8765)')
    parser.add_argument('--ml-port',       type=int, default=8766,
                        help='ML inference WebSocket server port (default: 8766)')
    parser.add_argument('--models-dir',    default='models',
                        help='Path to saved models directory (default: models)')
    parser.add_argument('--no-attack-inj', action='store_true',
                        help='Disable Modbus attack injection (safe/demo mode)')

    args = parser.parse_args()

    log.info('SWaT Real-Time ML Inference Server')
    log.info(f'  Upstream WS : {args.src_ws}')
    log.info(f'  ML port     : {args.ml_port}')
    log.info(f'  Models dir  : {args.models_dir}')
    log.info(f'  PLC host    : {args.plc_host}:{args.plc_port}')
    log.info(f'  Attack inj  : {"DISABLED (safe mode)" if args.no_attack_inj else "ENABLED"}')

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        log.info('Shutdown requested.')


if __name__ == '__main__':
    main()
