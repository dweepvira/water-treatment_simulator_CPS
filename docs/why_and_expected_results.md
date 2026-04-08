# SWaT Digital Twin — Motivation & Expected Results

## Why This Research Matters

### The ICS Security Problem
Industrial Control Systems (ICS) running water treatment, power grids, and pipelines are increasingly targeted by cyberattacks. The 2021 Oldsmar water plant attack (Florida) demonstrated that a remote attacker could raise sodium hydroxide levels to 111× the safe limit in under 5 minutes via SCADA access — nearly poisoning 15,000 people.

Traditional IT security tools (firewalls, antivirus) cannot detect process-level attacks that operate within legitimate Modbus/PROFINET protocols. An attacker sending valid Modbus write commands to change a setpoint is indistinguishable from normal operation at the network layer. Detection must happen at the **physics level** — does the plant behaviour match what the control logic predicts?

### Why Datasets Are Scarce
The original iTrust SWaT testbed at Singapore University of Technology and Design cost approximately $1M USD to build and requires physical chemicals, pumps, and membranes to operate. Generating labelled attack data requires deliberately injecting attacks into a live plant — unsafe and impractical for most researchers. The publicly released iTrust dataset (2015) contains only 11 attack types with limited sensor coverage.

### Why a Digital Twin Solves This
A digital twin reproduces the physics and control logic in software, allowing:
- **Unlimited attack injection** without safety risk
- **Perfect ground truth labelling** — every row knows exactly which attack is active
- **Reproducibility** — anyone can regenerate the dataset from the code
- **Variation** — operating conditions (setpoints, fouling state, chemical levels) can be varied systematically across runs to improve ML generalisation

---

## Research Questions

1. **Can ML models detect ICS attacks that are invisible to threshold-based alarms?** — Slow ramp attacks deliberately stay below ST interlock thresholds. Can LSTM/XGBoost catch the temporal pattern?

2. **Which features carry the most discriminative information?** — Is it sensor values, coil state changes, or derived features (mass balance residuals, rate of change)?

3. **Do models trained on one operating condition generalise to another?** — Run 01 (pH 6.8–8.5) vs Run 04 (wider pH range) as train/test split.

4. **How early can attacks be detected?** — Can the model alarm within 30 seconds of attack onset, before physical damage begins?

---

## Why Each Attack Was Chosen

### Reconnaissance (T0840)
Attackers scan ICS networks before targeting. No writes occur, but the 20 Hz read rate is anomalous. This tests whether ML can detect **network-level behavioural patterns** without any physical effect.

### Replay (T0839)
A classic ICS attack: capture legitimate Modbus traffic, replay it to mask a simultaneous physical attack. Signature is near-zero variance across all sensors simultaneously — physically impossible in a running plant.

### pH Manipulation (T0836)
Directly relevant to water safety. pH outside 6.5–9.0 makes water corrosive or alkaline enough to damage pipes and harm consumers. The attack bypasses the ST pH interlock by manipulating the sensor register before the interlock can trip.

### Slow Ramp (T0836)
The hardest attack for threshold-based detection. A 0.01 pH unit/cycle drift takes 30+ minutes to reach the interlock threshold. Human operators would not notice. This specifically tests LSTM temporal pattern detection.

### Membrane Damage (T0836)
UF and RO membranes cost $600–$2000 each. Suppressing backwash while forcing high-turbidity water through the UF membrane accelerates irreversible fouling. The physical signature is DPIT-301 rising beyond 60 kPa — but the attack suppresses the backwash coil so the ST recovery mechanism never triggers.

### Chemical Depletion (T0814)
Forces all dosing pumps ON simultaneously. Acid, chlorine, coagulant, and bisulfate tanks drain rapidly. When chlorine drops below 2 mg/L, pathogen risk increases. When acid runs out, pH control fails. This tests multi-variable correlated feature detection.

### Tank Overflow (T0816)
Disables outlet pumps while keeping the inlet open. As the tank approaches 950 L (overflow threshold), ST triggers High_Level_Alarm and shuts System_Run — effectively performing a denial-of-service on the entire plant.

### Valve Manipulation (T0849)
Closes inlet/outlet valves while pumps remain ON. Flow-pump inconsistency (P_101 ON but FIT_101 near zero) is the detection signature. This tests physical consistency checking — a purely rule-based feature that ML can learn.

---

## Expected ML Results

### Feature Importance (predicted by physics)

| Rank | Feature | Why |
|---|---|---|
| 1 | d(AIT_202)/dt | pH rate of change — catches pH manipulation and slow ramp |
| 2 | P_205 duty cycle | Chlorine pump ON-time correlates with Cl depletion attack |
| 3 | P_101 AND FIT_101<0.5 | Physical inconsistency — pump on, no flow |
| 4 | RO_Fouling acceleration | d²(RO_Fouling)/dt² spikes during membrane attack |
| 5 | Mahalanobis distance | Detects multi-variable stealth attacks invisible to univariate rules |
| 6 | FIT_101 − FIT_201 | Mass balance residual — should be ~0 in steady state |
| 7 | P_403 duty cycle | Bisulfate pump anomaly during pH attack (71.3% ON vs 4.3% normal) |

### Target Performance Metrics

| Model | Expected F1 | Key Limitation |
|---|---|---|
| Isolation Forest | 0.72–0.82 | False positives during UF backwash / RO CIP |
| Autoencoder | 0.75–0.85 | May miss slow ramp (too gradual to reconstruct badly) |
| XGBoost | 0.88–0.94 | Requires balanced classes; may overfit run-specific patterns |
| LSTM | 0.90–0.96 | Best for slow ramp and replay; slower inference |

### What We Expect to Confirm
- LSTM outperforms all other models on Slow Ramp detection (F1 >0.90 vs XGBoost <0.80)
- P_403 duty cycle is the single most important feature for pH attack detection (SHAP)
- Reconnaissance and Replay are detected at >0.98 F1 by all models (strong network signature)
- Chemical Depletion: Chlorine_Tank rate-of-change is more discriminative than the tank level itself
- Transfer test (train on runs 1–4, test on run 5 normal): FPR < 5% confirms generalisation
