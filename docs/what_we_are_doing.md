# SWaT Digital Twin — Project Overview & Outcomes

## What We Are Building

A **software digital twin** of the Secure Water Treatment (SWaT) testbed — a 6-stage water treatment plant — for ICS/SCADA cybersecurity research. The twin runs entirely in software: MATLAB models the physics, CODESYS runs the PLC control logic, and Python bridges them over Modbus TCP while logging every cycle to CSV.

The goal is to generate **labelled attack datasets** for training machine learning intrusion detection systems on industrial control networks without needing physical hardware.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  MATLAB (swat_physics_server.m)                                  │
│  TCP port 9501 — computes sensor physics every 100 ms            │
│  Input:  actuator states (pump ON/OFF, valve positions)          │
│  Output: all sensor register values (pH, flow, level, pressure)  │
└─────────────────┬───────────────────────────────────────────────┘
                  │ TCP (JSON, newline-delimited)
┌─────────────────▼───────────────────────────────────────────────┐
│  Python Bridge (physics_client.py)                               │
│  Atomic 100 ms cycle:                                            │
│  1. Read coils + MV registers from CODESYS (Modbus FC1/FC3)     │
│  2. Send actuator JSON → MATLAB                                   │
│  3. Receive sensor JSON ← MATLAB                                  │
│  4. Write sensor registers → CODESYS (Modbus FC16)               │
│  5. Log one CSV row (sensors + coils + attack label)             │
└─────────────────┬───────────────────────────────────────────────┘
                  │ Modbus TCP port 1502
┌─────────────────▼───────────────────────────────────────────────┐
│  CODESYS PLC (plant.st — Structured Text)                        │
│  Runs ST control logic at PLC scan rate                          │
│  Reads: sensor holding registers (written by Python/MATLAB)       │
│  Writes: pump coils, valve states, alarm coils                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6 Plant Stages

| Stage | Function | Key Instruments |
|---|---|---|
| S1 Raw Intake | Inlet flow control | LIT-101, FIT-101, MV-101, P-101/102 |
| S2 Chemical Dosing | pH, turbidity, chlorination | AIT-202 (pH), AIT-201 (NTU), P-203/205/206 |
| S3 Ultrafiltration | Membrane separation | DPIT-301 (TMP), LIT-301, P-301, P-602 (BW) |
| S4 UV / Dechlor | UV disinfection, bisulfate dosing | UV-401, P-401, P-403, AIT-402 |
| S5 Reverse Osmosis | High-pressure filtration | PIT-501, P-501, FIT-502, RO_Fouling |
| S6 Distribution | Treated water output | FIT-601, P-601/603 |

---

## Attack Types Implemented

| Category | Attack | MITRE ID | Mechanism |
|---|---|---|---|
| Network | Reconnaissance Scan | T0840 | 20 Hz read-only scan across all registers |
| Network | Replay Attack | T0839 | Freeze actuator state while attack proceeds |
| Temporal | pH Manipulation | T0836 | Drive AIT-202 outside 6.8–8.5 via P_203 + register write |
| Temporal | Slow Ramp | T0836 | Gradually drift AIT-202 via coil duty-cycle |
| Command | Tank Overflow | T0816 | Kill outlet pumps, keep MV-101 open |
| Command | Valve Manipulation | T0849 | Close MV-101/201/301 while pumps run |
| Temporal | Membrane Damage | T0836 | Suppress backwash, accumulate UF fouling |
| Temporal | Chemical Depletion | T0814 | Force all dosing pumps ON continuously |

---

## Dataset Structure

Each run produces a single `master_dataset.csv`:
- **84 columns**: 52 sensor registers + 28 coils + Timestamp + ATTACK_ID + ATTACK_NAME + MITRE_ID
- **~42,000 rows** per 70-min run at 10 Hz
- **Fully labelled**: every row stamped with attack type via `attack_metadata.json` IPC

### 5 Planned Runs

| Run | Attacks | Purpose |
|---|---|---|
| 01 | Recon, Replay, pH, SlowRamp | Baseline attack mix |
| 02 | Recon, Replay, Membrane, ChemDepletion | Fouling + chemistry |
| 03 | Recon, Replay, TankOverflow, Valve | Command injection |
| 04 | pH, SlowRamp, Membrane, ChemDepletion | All temporal |
| 05 | Normal only | Clean baseline for unsupervised models |

---

## Expected Outcomes

### Dataset
- ~210,000 total rows across 5 runs
- 8 distinct attack types labelled with MITRE IDs
- Engineering-unit scaled values (pH as float, flows in m³/h)
- Temporal continuity guaranteed (single-session per run, <1 s max gap)

### ML Models (Phase 2)
| Model | Training data | Output |
|---|---|---|
| Isolation Forest | Normal rows only (run_05) | Anomaly score 0–1 |
| Autoencoder | Normal rows only | Reconstruction error |
| XGBoost | All 5 runs labelled | Attack class + probability |
| LSTM (30-step window) | All 5 runs | Temporal attack detection |

### Research Deliverables
- Reproducible ICS attack dataset generation pipeline
- Comparison of rule-based (ST interlocks) vs ML-based anomaly detection
- SHAP feature importance per attack type
- Transfer learning evaluation: model trained on runs 1–4 tested on run 5
