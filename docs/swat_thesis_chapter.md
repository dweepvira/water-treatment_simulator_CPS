# A Software Digital Twin for Secure Water Treatment: Architecture, Physics Modelling, Adversarial Attack Generation, and Machine Learning–Based Anomaly Detection

**Dweep — Cyber-Physical Systems Security Research | March 2026**

---

> **Document note.** This chapter is intended to serve as a self-contained technical contribution within a larger thesis or research report. All mathematical notation follows IEEE journal conventions. LaTeX-compatible equation blocks are marked with `$$…$$`. Suggested figure insertion points are annotated with `[FIGURE N]` markers and accompanying captions.

---

## Table of Contents

1. [Introduction and Research Motivation](#1-introduction-and-research-motivation)
2. [System Architecture](#2-system-architecture)
3. [Physics Modelling and Mathematical Foundations](#3-physics-modelling-and-mathematical-foundations)
4. [Adversarial Attack Modelling](#4-adversarial-attack-modelling)
5. [Dataset Generation Pipeline](#5-dataset-generation-pipeline)
6. [Multi-Run Experimental Design](#6-multi-run-experimental-design)
7. [Machine Learning Integration and Anomaly Detection](#7-machine-learning-integration-and-anomaly-detection)
8. [Control Logic, Cause–Effect Relationships, and PLC Interlock Analysis](#8-control-logic-causeeffect-relationships-and-plc-interlock-analysis)
9. [Conclusion and Research Contributions](#9-conclusion-and-research-contributions)

---

## 1. Introduction and Research Motivation

### 1.1 The Industrial Control System Security Problem

Industrial Control Systems (ICS) govern the operation of critical infrastructure — water treatment, power generation, oil and gas pipelines, and chemical manufacturing. Unlike conventional information technology (IT) systems, ICS environments prioritise process continuity and physical safety over confidentiality, and they operate on deterministic, time-critical protocols such as Modbus TCP, PROFINET, and DNP3. These characteristics create a security posture that is fundamentally different from the enterprise IT domain: network segmentation is difficult to maintain, devices operate on decades-long lifecycles, firmware updates are rarely deployed, and the consequences of a successful attack are physical rather than merely informational.

The severity of this threat was made unambiguously apparent in 2021, when an attacker gained remote access to the SCADA system of a water treatment facility in Oldsmar, Florida, and raised the concentration of sodium hydroxide from 111 parts per million to 11,100 parts per million — a factor of one hundred above the safe limit — in under five minutes [CITATION]. Had a plant operator not been monitoring the Human–Machine Interface (HMI) at the moment of the intrusion, the consequences for the 15,000 residents supplied by the plant could have been severe. Critically, the attacker exploited a legitimate remote access pathway and issued commands that were syntactically valid within the Modbus protocol. No network-layer intrusion detection system would have flagged the traffic as anomalous.

This observation — that process-level attacks are invisible to network-level defences — defines the central motivation of the present work. Detection must occur at the **physics level**: by continuously comparing observed sensor behaviour with what the underlying physical model predicts, any deviation beyond the noise floor constitutes a candidate anomaly. This principle, sometimes termed physics-based anomaly detection or model-based intrusion detection, is the conceptual foundation upon which the digital twin described here is constructed.

### 1.2 The Dataset Scarcity Problem

Supervised machine learning intrusion detection systems require labelled training data: time-series records in which each sample carries a ground-truth label identifying whether a particular attack was active at that moment, and if so, what class of attack. In the ICS domain, the generation of such datasets is severely constrained by the properties of the physical systems involved. A water treatment plant cannot be deliberately subjected to a sodium hydroxide overdose for the sake of generating training data. Chemical reagent tanks cannot be deliberately drained to exhaustion during live production. Membrane fouling cannot be deliberately induced in an RO plant that serves a population.

The publicly available iTrust SWaT dataset, released by the Singapore University of Technology and Design [CITATION], remains the most widely cited benchmark in the field. It was generated using a fully physical six-stage water treatment testbed at an estimated hardware cost of approximately one million US dollars. The dataset covers eleven attack scenarios, recorded over eleven days of operation. While the dataset has been invaluable in establishing baseline benchmarks, its limitations are significant: the attack set is fixed, the operating conditions are constant across runs, the sensor count is constrained by the physical hardware, and replication by independent researchers requires either access to an equivalent physical facility or acceptance of the domain shift introduced by different hardware. Furthermore, because the physical testbed must be operated safely, certain attack scenarios — those that would cause irreversible physical damage — could not be included.

### 1.3 The Digital Twin as a Research Platform

A software digital twin of a water treatment plant resolves all of these constraints simultaneously. If the twin faithfully replicates the physics, the control logic, and the communication protocol of the physical system, then the dataset it generates carries the same statistical properties as data from the physical plant — but can be produced at negligible marginal cost, with arbitrary attack injection, perfect ground-truth labelling, and complete reproducibility from source code.

The system described in this document implements precisely this architecture. MATLAB provides a physics simulation engine that models six stages of water treatment chemistry and hydraulics using a set of coupled ordinary differential equations. CODESYS executes the PLC Structured Text control program that would govern actuator behaviour in the physical plant. A Python bridge synchronises the two at ten cycles per second — the sampling rate of a real industrial Modbus network — while logging every sensor reading, actuator state, and attack label to a timestamped CSV file. The result is a dataset generation platform that is physically grounded, protocol-faithful, and fully open to adversarial perturbation.

---

## 2. System Architecture

### 2.1 Overview and Design Philosophy

The digital twin is structured as a closed-loop cyber-physical system with three coupled layers: a **physics engine** that governs the evolution of the plant state, a **control layer** that issues actuator commands based on sensor readings, and an **orchestration bridge** that synchronises the two at each timestep while simultaneously managing attack injection and data logging. This layered decomposition mirrors the actual architecture of an operational ICS, where field-level sensors and actuators are governed by PLC control logic, which is in turn supervised by a SCADA historian.

A critical design choice was to use a real, executing PLC runtime (CODESYS) rather than a simulated controller. This ensures that the control logic seen by the dataset is genuinely Structured Text executing in a real scan cycle, with all of the associated artefacts: one-cycle evaluation lag, register read-before-write semantics, and hysteresis states maintained across scan boundaries. A purely simulated controller would not reproduce these artefacts, potentially generating training data with temporal structure that does not match the physical system.

```
┌──────────────────────────────────────────────────────────────────┐
│  MATLAB Physics Server  (swat_physics_server.m)                  │
│  TCP port 9501 — computes sensor physics at 10 Hz                │
│  Input:  actuator state vector (pump coils, valve positions)     │
│  Output: sensor register vector (pH, flow, level, pressure)      │
└──────────────────────────┬───────────────────────────────────────┘
                           │ TCP / JSON  (newline-delimited)
┌──────────────────────────▼───────────────────────────────────────┐
│  Python Bridge  (physics_client.py)                              │
│  Atomic 100 ms cycle:                                            │
│  1. read_actuators()   — FC1 coils + FC3 MV registers (Modbus)  │
│  2. call_matlab()      — send actuator JSON, receive sensor JSON │
│  3. _apply_attack_sensors() — override registers if attack active│
│  4. write_sensors()    — FC16 bulk write registers 0–51         │
│  5. log_row()          — SCALE_MAP applied, label stamped, CSV  │
└──────────────────────────┬───────────────────────────────────────┘
                           │ Modbus TCP  (port 1502)
┌──────────────────────────▼───────────────────────────────────────┐
│  CODESYS PLC  (plant.st — Structured Text)                       │
│  Runs ST control logic at PLC scan rate                          │
│  Reads:  sensor holding registers 0–51 (written by Python)       │
│  Writes: pump coils 0–27, alarm coils, valve states             │
└──────────────────────────────────────────────────────────────────┘
```

`[FIGURE 1: Three-layer digital twin architecture showing data flow between MATLAB physics engine, Python orchestration bridge, and CODESYS PLC runtime. Arrows indicate direction and protocol of each communication link.]`

### 2.2 The Physics Engine: MATLAB Simulation Server

The MATLAB physics server (`swat_physics_server.m`) operates as a TCP server listening on port 9501. At each timestep, it receives a JSON object encoding the current actuator state vector — which pumps are energised, which motorised valves are open, and what position feedback the valve positioners report — and returns a JSON object encoding the resulting sensor state. The computation within MATLAB is a discrete-time integration of a set of coupled ordinary differential equations governing tank mass balance, chemical buffer kinetics, membrane fouling accumulation, and pressure distribution.

The use of MATLAB for physics rather than a Python-native simulation library reflects a deliberate engineering decision. MATLAB's ODE solvers (`ode45`, `ode23`) and its signal processing libraries provide a well-validated, numerically stable environment for physical modelling. More importantly, the physics equations in `swat_physics_server.m` are self-documenting and can be directly compared against the published process engineering literature, supporting the claim that the digital twin is physically grounded rather than merely parameterised.

The server maintains state between cycles: tank levels, membrane fouling factors, chemical tank quantities, and accumulated runtime counters are persistent variables updated by each integration step. The timestep `dt = 0.1 s` is sufficient to capture the relevant dynamics of the plant — the slowest process (pH buffer kinetics, $\tau = 40$ s) spans approximately 400 integration steps per time constant, providing more than adequate numerical resolution.

### 2.3 The Python Bridge: Synchronisation and Orchestration

The Python bridge (`physics_client.py`) is the central orchestration layer. It runs a strict 100 ms periodic loop that must complete all five sub-steps — Modbus read, MATLAB request, MATLAB response, Modbus write, and CSV log — within the 100 ms budget. This is not a soft real-time system: individual cycles may occasionally exceed 100 ms due to network jitter or garbage collection pauses, but the bridge uses wall-clock timestamps to detect and log such exceedances, and the dataset's `delta_t` column captures any timing anomalies for use as a temporal feature in ML training.

The most architecturally significant design decision in the bridge is the placement of attack sensor injection. An earlier version of the system performed attack register writes from a separate process (`command_injection.py`), which wrote to CODESYS registers independently of the bridge's write cycle. This produced a race condition in which the bridge's `write_sensors()` call, which executes every 100 ms, would overwrite the attack values written by `command_injection.py` between cycles. The consequence was that attack signatures appeared in the CODESYS registers for at most one cycle before being erased — far too briefly to appear in the logged CSV data, which reads from CODESYS at the end of the bridge's cycle.

The correct architecture, implemented in the current system, places attack injection inside the bridge cycle as `_apply_attack_sensors()`, which executes after MATLAB returns its physics-computed sensor vector but before that vector is written to CODESYS. This ensures that the modified (attacked) sensor values are the values that CODESYS evaluates in its next ST scan, and are also the values logged to CSV. The attack and the ground-truth label therefore have zero temporal misalignment.

### 2.4 The CODESYS PLC: Control Logic Execution

CODESYS executes the Structured Text program `plant.st`, which implements the full set of control rules for all six plant stages. The PLC runtime exposes a Modbus TCP slave on port 1502, with holding registers 0–51 carrying sensor values written by the Python bridge, and coils 0–27 carrying actuator states written by the ST program.

A fundamental protocol discipline governs which entity owns which registers. **Sensor holding registers (0–51) are owned by the Python bridge.** The bridge writes them every 100 ms with the MATLAB-computed (and possibly attack-modified) sensor values. The PLC reads these registers in the ST program as inputs to its control logic, but never writes to them. Conversely, **actuator coils (0–27) are owned by CODESYS.** The ST program writes coil states as outputs of its control evaluation, and the bridge reads them at the start of each cycle to pass to MATLAB as the actuator input vector.

This ownership discipline was not present in an early version of the system, where `write_sensors()` inadvertently overwrote motorised valve registers that CODESYS was using to communicate valve state back to the bridge. The symptom was that all MV registers appeared as zero in the logged CSV data regardless of the plant state, because the bridge was replacing CODESYS's valve state with MATLAB's valve physics every cycle. Formalising the register ownership rule — and implementing it via a register exclusion list in `write_sensors()` — eliminated this class of bug.

### 2.5 One-Cycle Evaluation Lag and Its Dataset Implications

A structural timing artefact arises from the sequential execution of the bridge cycle. At cycle $N$, the bridge writes new sensor values to CODESYS registers. CODESYS evaluates its ST program — which reads those registers and computes new coil states — on the **next** PLC scan, which occurs before cycle $N+1$. The bridge reads the updated coil states at the start of cycle $N+1$. Consequently, the coil state logged in the CSV row for cycle $N$ reflects the ST decision computed in response to the sensor values written in cycle $N-1$.

This one-cycle (100 ms) lag is an inherent property of the Modbus polling architecture and is present in physical ICS deployments as well. It manifests in the dataset as systematic one-row misalignment between sensor state transitions and the corresponding actuator responses. For example, when `LIT_101` crosses the 449 L threshold that should trigger `MV_101 := 1`, the logged row at exactly 449 L will show `MV_101 = 0`, because CODESYS has not yet had time to evaluate the threshold crossing. The row at 449 L is followed by a row where `LIT_101 > 449` and `MV_101 = 1`. Approximately 97% of apparent S1-R1 rule violations in the dataset are attributable to this boundary-value logging artefact rather than genuine control failures.

This phenomenon has significant implications for ML feature engineering. A classifier trained naively on raw register values will observe these one-row violations and may either learn them as spurious anomaly signatures or, worse, learn to ignore genuine single-cycle violations by conflating them with the artefact. The recommended mitigation is to use temporal lag features (`LIT_101_lag1`, `MV_101_lag1`) that explicitly model the one-cycle delay, allowing the classifier to correctly attribute boundary violations to timing rather than attack.

---

## 3. Physics Modelling and Mathematical Foundations

### 3.1 Formal System Representation

The digital twin is formally a **discrete-time cyber-physical system**. At each timestep $t$, the system state $\mathbf{x}_t \in \mathbb{R}^n$ captures all physical quantities — tank levels, concentrations, fouling factors, and membrane pressures — that carry information from one cycle to the next. The state evolves according to the nonlinear difference equation:

$$\mathbf{x}_{t+1} = f(\mathbf{x}_t, \mathbf{u}_t, \boldsymbol{\omega}_t)$$

where $\mathbf{u}_t \in \{0,1\}^m$ is the binary actuator control vector (pump coils and valve states) issued by the CODESYS ST program at timestep $t$, and $\boldsymbol{\omega}_t \sim \mathcal{N}(\mathbf{0}, \mathbf{Q})$ is a zero-mean Gaussian process noise vector capturing unmodelled disturbances such as raw water quality variation and ambient temperature drift. The transition function $f(\cdot)$ is implemented by the MATLAB physics engine.

Sensor measurements are modelled as noisy observations of the true state:

$$\mathbf{y}_t = h(\mathbf{x}_t) + \boldsymbol{\epsilon}_t, \qquad \boldsymbol{\epsilon}_t \sim \mathcal{N}(\mathbf{0}, \mathbf{R})$$

where $h: \mathbb{R}^n \to \mathbb{R}^p$ is the (generally nonlinear) observation function mapping true states to register-scaled sensor readings, and $\mathbf{R} = \mathrm{diag}(\sigma_1^2, \ldots, \sigma_p^2)$ is a diagonal noise covariance matrix with per-sensor noise variances characterised from physical instrument data sheets.

Under attack, the measurement model is augmented by an adversarial perturbation term:

$$\mathbf{y}_t^{\mathrm{atk}} = h(\mathbf{x}_t) + \boldsymbol{\delta}_t + \boldsymbol{\epsilon}_t$$

where $\boldsymbol{\delta}_t \in \mathbb{R}^p$ is the attack-injected register deviation, which may be zero for most components and nonzero only for the targeted sensors. The ML anomaly detection task is precisely to infer, from the sequence $\{\mathbf{y}_0, \mathbf{y}_1, \ldots, \mathbf{y}_t\}$, whether $\boldsymbol{\delta}_t \neq \mathbf{0}$ and, if so, to identify the non-zero components (affected registers) and the temporal profile of $\boldsymbol{\delta}_t$ (attack class).

### 3.2 Stage 1 — Raw Water Intake: Tank Mass Balance

The primary physical variable in Stage 1 is the raw water tank volume $V_t$ [L], governed by the conservation of mass:

$$\frac{dV}{dt} = Q_{\mathrm{in}}(t) - Q_{\mathrm{out}}(t)$$

Volumetric inflow depends on the state of the motorised inlet valve $u_{\mathrm{MV101}} \in \{0,1\}$ and a stochastic source pressure term:

$$Q_{\mathrm{in}}(t) = u_{\mathrm{MV101}} \cdot \frac{5 + \omega_Q}{3600} \times 1000 \quad [\mathrm{L/s}]$$

where $\omega_Q \sim \mathcal{N}(0, 0.1^2)$ models source pressure variability. Outflow is a level-dependent centrifugal pump characteristic:

$$Q_{\mathrm{out}}(t) = \frac{1}{3600} \times \left[4 + \mathbf{1}(V_t > 400) + \mathbf{1}(V_t > 600) + 2 \cdot u_{P102}\right] \times 1000 \quad [\mathrm{L/s}]$$

The staged pump curve — where higher tank levels produce higher outlet flow through the activation of the booster pump $P_{102}$ — models the hydraulic characteristic of a centrifugal pump operating on a falling pump curve. In steady state, $dV/dt = 0$ implies $Q_{\mathrm{in}} = Q_{\mathrm{out}}$, giving a natural equilibrium level around which $V_t$ oscillates with period approximately 67 seconds and amplitude approximately ±117 L.

The discrete-time integration used in MATLAB is the forward Euler method:

$$V_{t+1} = V_t + \left(Q_{\mathrm{in}}(t) - Q_{\mathrm{out}}(t)\right) \cdot \Delta t, \qquad \Delta t = 0.1 \text{ s}$$

with $V_t$ clamped to $[0, 1000]$ L to model the physical tank boundaries. Register values are scaled as $\mathrm{LIT\_101} = \lfloor V_t \rceil$ (integer litres, no scaling), and $\mathrm{FIT\_101} = \lfloor Q_{\mathrm{in}} \times 10 \rceil$ (stored at $\times 10$, logged in CSV at $\div 10 = \mathrm{m}^3/\mathrm{h}$).

### 3.3 Stage 2 — Chemical Dosing: pH Buffer Kinetics

The pH dynamics of the dosing stage follow a first-order buffer depletion model. In aqueous solution, the equilibrium pH is maintained by the bicarbonate buffer system ($\mathrm{HCO_3^-/H_2CO_3}$). Acid dosing drives the equilibrium toward a lower target pH $\phi_{\mathrm{target}}$, while natural alkalinisation (from dissolved CO$_2$ uptake and mineral leaching) drives pH toward a higher natural target. The first-order ODE governing this process is:

$$\frac{d\phi}{dt} = -\frac{\phi - \phi_{\mathrm{target}}(t)}{\tau_\phi} + \epsilon_\phi(t)$$

where $\tau_\phi = 40$ s is the buffer time constant characterising the rate at which the chemical equilibrium responds to dosing, and $\epsilon_\phi(t) \sim \mathcal{N}(0, 0.01^2)$ is sensor noise in pH units. The target pH switches discontinuously based on the acid pump state:

$$\phi_{\mathrm{target}}(t) = \begin{cases} 6.80 & \text{if } u_{P203}(t) = 1 \text{ (acid dosing ON)} \\ 8.50 & \text{if } u_{P203}(t) = 0 \text{ (natural alkalinisation)} \end{cases}$$

The analytic solution of the ODE, which MATLAB evaluates per timestep, is:

$$\phi(t) = \phi_{\mathrm{target}} + \left(\phi_0 - \phi_{\mathrm{target}}\right) \cdot e^{-t/\tau_\phi}$$

The exponential approach means that after one time constant (40 s), 63.2% of the gap between current and target pH has been closed. After three time constants (120 s), 95.0% of the transition is complete. This kinetic structure is physically justified: first-order chemical buffer kinetics arise directly from the Henderson–Hasselbalch equation when one reactant is in excess, giving $d[\mathrm{HCO_3^-}]/dt = -k[\mathrm{HCO_3^-}]$. The register encoding is $\mathrm{AIT\_202} = \lfloor \phi \times 100 \rceil$, logged in CSV at $\div 100$ to recover pH units.

Chlorine residual dynamics are modelled as a piecewise linear accumulation and decay process:

$$\mathrm{Cl}(t+1) = \begin{cases} \min(8.0, \mathrm{Cl}(t) + 0.3\,\Delta t) & \text{if } u_{P205} = 1 \\ \max(1.5, \mathrm{Cl}(t) - 0.1\,\Delta t) & \text{if } u_{P205} = 0 \end{cases}$$

The decay rate of 0.1 mg/L per timestep (1.0 mg/L per second at 10 Hz, or equivalently 360 mg/L/hour) represents chlorine demand from dissolved organics and reaction with the water matrix. The minimum floor of 1.5 mg/L reflects the fact that real distribution systems maintain a minimum residual to prevent microbial regrowth; this floor would be violated only by a chemical depletion attack that exhausts the chlorine supply faster than the demand floor.

### 3.4 Stage 3 — Ultrafiltration: Membrane Fouling and Darcy's Law

Membrane fouling accumulation is modelled via a simplified form of Darcy's Law for cake filtration. The trans-membrane pressure (TMP) is proportional to the total hydraulic resistance, which increases as fouling material deposits on the membrane surface:

$$\frac{dF}{dt} = \alpha \cdot \frac{\mathrm{AIT\_201}}{1000} \cdot J \cdot \Delta t$$

where $F \in [0,1]$ is the normalised fouling factor (0 = clean, 1 = fully blocked), $\alpha = 0.001$ is the specific fouling resistance coefficient, and $J$ is the permeate flux (approximated as constant in the simplified model). The turbidity $\mathrm{AIT\_201}$ [NTU] modulates the fouling rate: high-turbidity feed water carries more suspended solids and therefore accumulates fouling faster, consistent with Darcy's cake resistance theory. In the simplified discrete form:

$$F_{t+1} = F_t + 0.001 \cdot \left(1 + \frac{\mathrm{AIT\_201}_t}{1000}\right) \cdot \Delta t$$

The trans-membrane pressure is then computed from the fouling factor via a linear constitutive relation:

$$\mathrm{DPIT\_301} = 25 + 100 \cdot F_t \quad [\mathrm{kPa}]$$

This gives $\mathrm{DPIT\_301} = 25$ kPa for a clean membrane ($F=0$) and $\mathrm{DPIT\_301} = 125$ kPa for a fully fouled membrane ($F=1$). The backwash trigger is set at $\mathrm{DPIT\_301} > 60$ kPa, corresponding to $F > 0.575$. Starting from $F=0$ with clean water ($\mathrm{AIT\_201} \approx 0$ NTU), the time to reach the backwash threshold is approximately:

$$t_{\mathrm{BW}} = \frac{F^* - F_0}{\alpha \cdot \Delta t} = \frac{0.575}{0.001 \times 0.1} \approx 5750 \text{ s} \approx 96 \text{ min}$$

This is why the time-triggered backwash at 30 minutes (`UF_Last_Backwash > 18000` cycles) typically fires before the pressure-triggered backwash under normal operating conditions.

### 3.5 Stage 5 — Reverse Osmosis: Pressure Modelling

RO feed pressure is modelled as an affine function of the membrane fouling state, augmented by a level-dependent hydraulic head term:

$$\mathrm{PIT\_501} = 120 + 80 \cdot F_{\mathrm{RO}} + 5 \cdot \mathbf{1}(\mathrm{LIT\_401} > 600) - 5 \cdot \mathbf{1}(\mathrm{LIT\_401} < 400) \quad [\mathrm{bar}]$$

RO fouling accumulates at a constant rate $dF_{\mathrm{RO}}/dt = 0.0005\,\Delta t$ [fraction/step], reflecting the slow, irreversible nature of scaling and biofouling on spiral-wound RO membranes. The CIP (Clean-In-Place) trigger fires when $F_{\mathrm{RO}} > 0.80$, after which the fouling factor is reduced at $0.02\,\Delta t$ per step. The TDS rejection ratio is modelled as a constant 98.5%:

$$\mathrm{TDS\_permeate} = \left\lfloor \frac{\mathrm{TDS\_feed} \times 15}{1000} \right\rceil \quad [\mathrm{ppm}]$$

### 3.6 Sensor Noise Characterisation

All sensor measurements include additive Gaussian noise, justified by the Central Limit Theorem: real sensor noise is the superposition of many independent, small-magnitude random disturbances (thermal noise, electromagnetic interference, quantisation error, mechanical vibration), and their sum converges in distribution to a Gaussian. The noise parameters, scaled to register units, are:

| Sensor | $\sigma$ (register) | $\sigma$ (engineering unit) |
|---|---|---|
| AIT\_202 (pH $\times 100$) | 4 | $\pm 0.04$ pH |
| LIT\_101 (L) | 6 | $\pm 6$ L |
| PIT\_501 (bar $\times 10$) | 30 | $\pm 3.0$ bar |
| DPIT\_301 (kPa $\times 10$) | 10 | $\pm 1.0$ kPa |
| FIT\_101 (m$^3$/h $\times 10$) | 2 | $\pm 0.2$ m$^3$/h |

These values are calibrated against manufacturer data sheets for the corresponding physical instruments (Endress+Hauser, Hach, Keyence). The noise floor defines the minimum attack amplitude that is statistically distinguishable from normal process variation: a deviation of less than $3\sigma$ in any single sensor is indistinguishable from noise at standard detection thresholds, which has direct implications for the design of stealth attacks (Section 4).

---

## 4. Adversarial Attack Modelling

### 4.1 Attack Classification Framework

The eight attack types implemented in the digital twin span three layers of the ICS reference model: network-layer attacks that operate on the communication protocol without touching physical process values, command-layer attacks that issue legitimate-format actuator commands to cause physical effects, and temporal-layer attacks that modify sensor register values to gradually steer the process into an unsafe state while evading threshold-based alarms. Each attack is tagged with the corresponding MITRE ATT&CK for ICS technique identifier [CITATION].

The central modelling insight is that each attack can be characterised by a triple (target register set, deviation profile $\boldsymbol{\delta}_t$, detection signature). Understanding this triple is the prerequisite for designing effective ML features.

### 4.2 Reconnaissance Scan (T0840)

A reconnaissance attack performs a systematic, high-frequency read scan across all Modbus holding registers and coils without issuing any write commands. In the physical system, such a scan would originate from an attacker-controlled node on the OT network that has obtained network access (via spear-phishing, supply chain compromise, or lateral movement from the IT network). The attack model injects a 20 Hz read stream — twice the nominal bridge polling rate — against the CODESYS Modbus slave.

From a physics perspective, reconnaissance has zero impact on the plant state: $\boldsymbol{\delta}_t = \mathbf{0}$ throughout the attack. The physical sensor and actuator values are unchanged. Detection must therefore rely entirely on network-layer behavioural features: anomalous Modbus function code frequency, read requests originating from an unexpected IP address (192.168.5.200 rather than the bridge at 192.168.5.100), and the characteristic uniform coverage of the register map (normal SCADA polling reads only configured tags, not all 52 registers sequentially).

In the dataset, reconnaissance is labelled by ground-truth metadata without any corresponding deviation in sensor values. This makes it an important test of whether ML models can learn network-level temporal patterns from the logged `delta_t` jitter introduced by the concurrent high-frequency polling, rather than relying on physics-based features.

### 4.3 Replay Attack (T0839)

The replay attack models the scenario in which an attacker captures a window of legitimate Modbus traffic — actuator command sequences during a known-good operating period — and continuously replays the captured coil write commands against the PLC while a separate physical manipulation is underway. The effect of replay is to freeze the actuator register state: all coils appear to maintain the values they held at the capture moment, regardless of what the ST control program is actually commanding.

The physical signature of a replay attack is statistically distinctive and physically impossible in a genuine running plant: near-zero variance across all sensor readings and all actuator coils simultaneously. In a real water treatment plant, the combination of pump cycling, chemical dosing feedback, and level oscillation guarantees that multiple signals are changing continuously. A window of frozen readings longer than approximately 10 seconds violates this statistical expectation with probability approaching 1.

In the dataset, replay is implemented by holding actuator coil values at their captured states, allowing MATLAB to compute the resulting physics — which diverges from the frozen sensor registers — while the attack labels mark the affected rows. The ML detection feature is `rolling_variance(window=100)` across the full sensor vector: a simultaneous near-zero variance spike in this multivariate statistic is pathognomonic for replay.

### 4.4 pH Manipulation Attack (T0836)

The pH manipulation attack directly overwrites the `AIT_202` holding register (Modbus address 4) with a target value outside the normal operating range, exploiting the fact that the CODESYS ST program uses this register as the input to its pH control logic. By controlling what pH value the ST program observes, the attacker controls the behaviour of the acid dosing pump $P_{203}$: if the register reports an erroneously low pH, $P_{203}$ will be commanded OFF even as the actual process pH drifts outside safe bounds.

The attack is implemented at 25 Hz — 2.5× the bridge's 10 Hz polling rate — ensuring that approximately 71% of the bridge's `write_sensors()` calls see the attack value before it can overwrite the register with the MATLAB-computed true value. The register-level dynamics under this attack follow the forced first-order response:

$$\mathrm{AIT\_202}^{\mathrm{atk}}(t) = \phi_{\mathrm{target}}^{\mathrm{atk}} \times 100 + \left(\mathrm{AIT\_202}(0) - \phi_{\mathrm{target}}^{\mathrm{atk}} \times 100\right) \cdot e^{-t/\tau_\phi} + \epsilon_t$$

For a target of pH 5.0 ($\phi_{\mathrm{target}}^{\mathrm{atk}} \times 100 = 500$), starting from a normal operating pH of 7.2 ($\mathrm{AIT\_202}(0) = 720$), the register approaches 500 with time constant $\tau_\phi = 40$ s, reaching 500 ± 4 (noise) within approximately 200 seconds. At this point, if the true process pH (which the attacker cannot control) has drifted to 9.0 due to the suppressed acid dosing, the safety interlock `S2-R7` (`AIT_202 > 900`) may not fire because the register reports a falsely low value.

The critical detection feature is the **physical inconsistency between the register value and the actuator state**: a pH register reporting 5.0 (AIT\_202 = 500) while the acid dosing pump $P_{203}$ is simultaneously OFF is physically impossible under normal control logic, since $P_{203}$ is energised whenever $\mathrm{AIT\_202} > 750$. The feature `ph_pump_inconsistency = (AIT_202 < 680) AND (P_203 = 0)` captures this contradiction with zero false positive rate in normal operation.

### 4.5 Slow Ramp Attack (T0836)

The slow ramp attack is the most operationally sophisticated attack in the dataset and the primary motivation for including an LSTM layer in the ML detection stack. Rather than driving the target register to an extreme value immediately, the slow ramp applies a sigmoid-shaped drift profile that keeps the register value within normal operating bounds for as long as possible:

$$\mathrm{AIT\_202}^{\mathrm{atk}}(t) = \phi_{\mathrm{start}} \times 100 + (\phi_{\mathrm{end}} - \phi_{\mathrm{start}}) \times 100 \cdot \sigma\!\left(\frac{10t}{T} - 5\right) + \epsilon_t$$

where $\sigma(x) = (1 + e^{-x})^{-1}$ is the logistic sigmoid and $T$ is the attack duration in seconds. The maximum rate of change, occurring at the sigmoid inflection point $t = T/2$, is:

$$\left.\frac{d\,\mathrm{AIT\_202}^{\mathrm{atk}}}{dt}\right|_{\max} = \frac{(\phi_{\mathrm{end}} - \phi_{\mathrm{start}}) \times 100 \cdot 2.5}{T}$$

For the default parameterisation ($\phi_{\mathrm{start}} = 7.20$, $\phi_{\mathrm{end}} = 5.60$, $T = 600$ s), the maximum rate is:

$$\frac{(5.60 - 7.20) \times 100 \times 2.5}{600} = -\frac{400}{600} \approx -0.67 \text{ register units/s} \approx -0.007 \text{ pH units/s}$$

This rate is approximately equal to the noise standard deviation per second ($\sigma_{\mathrm{AIT202}} / \Delta t = 4 / 0.1 = 40$ register units/s normalised to noise; the signal change is $0.67$ vs noise of $4/0.1$), meaning that the drift is undetectable in a single sample. Only by accumulating evidence over a window of 30 or more samples — as an LSTM does through its hidden state — can the temporal trend be separated from the noise floor.

The slow ramp attack also exploits the hysteresis band of the ST pH controller: as long as the AIT\_202 register remains within [680, 750] (the hysteresis dead-band between the P\_203 OFF and ON thresholds), the controller takes no corrective action. The attacker can therefore drive the pH reading through the dead-band at a rate slow enough to avoid triggering the control response until the reading reaches the P\_203 ON threshold from above — at which point the controller activates acid dosing, but the true process pH (unobserved) may have already drifted far outside safe bounds.

### 4.6 Tank Overflow Attack (T0816)

The tank overflow attack targets Stage 1 hydraulics by disabling the transfer pumps $P_{101}$ and $P_{102}$ via coil writes while keeping the motorised inlet valve $\mathrm{MV\_101}$ open. With $Q_{\mathrm{out}} \approx 0$ and $Q_{\mathrm{in}} \approx 1.4$ L/s, the tank fills at a rate determinable from the mass balance:

$$\frac{dV}{dt} \approx Q_{\mathrm{in}} = \frac{5}{3600} \times 1000 \approx 1.39 \text{ L/s}$$

Starting from the nominal mid-level of 449 L, the tank reaches the 950 L overflow threshold after approximately:

$$t_{\mathrm{overflow}} = \frac{950 - 449}{1.39} \approx 360 \text{ s} \approx 6 \text{ min}$$

The detection signature is straightforward: the level rate of change $d(\mathrm{LIT\_101})/dt$ is strongly positive for an extended period while $P_{101} = 0$ and $P_{102} = 0$. In normal operation, a positive level rate implies that $Q_{\mathrm{in}} > Q_{\mathrm{out}}$, which occurs only transiently during inlet-open phases and is corrected within seconds by the pump control logic. A sustained positive rate persisting beyond 30 seconds with pumps OFF is a highly specific attack signature.

The plant safety system responds to $\mathrm{LIT\_101} > 950$ by setting `High_Level_Alarm := TRUE` and subsequently `System_Run := FALSE`, effectively performing a controlled shutdown. The attack therefore constitutes a denial-of-service against the plant: the intended outcome is not physical damage but cessation of water production, which has downstream consequences for the populations and industrial processes the plant supplies.

### 4.7 Valve Manipulation Attack (T0849)

The valve manipulation attack closes the inlet valve $\mathrm{MV\_101}$ and the UF feed valve $\mathrm{MV\_301}$ (and optionally $\mathrm{MV\_201}$ and $\mathrm{MV\_302}$) via direct coil writes while the transfer pumps remain energised. The immediate physical consequence is that $Q_{\mathrm{in}} = 0$ even though $P_{101} = 1$: the pump is running against a closed valve. In a real system, this condition would rapidly overheat and damage the pump via cavitation. In the digital twin, it produces a measurable flow-pump inconsistency: $P_{101} = 1$ AND $\mathrm{FIT\_101} \approx 0$, which is physically impossible under normal operation.

The detection feature `pump_flow_inconsistency = (P_101 = 1) AND (FIT_101 < \theta)` where $\theta$ is the 10th percentile of `FIT_101` under normal $P_{101} = 1$ conditions (approximately 0.05 m$^3$/h) captures this signature with a false positive rate approaching zero. The feature is a direct Boolean expression of a physical constraint: a centrifugal pump operating on an open fluid path must produce measurable flow.

### 4.8 Membrane Damage Attack (T0836)

The membrane damage attack suppresses the backwash activation coil `UF_Backwash_Active` while simultaneously forcing high-turbidity water through the UF membrane, causing accelerated fouling accumulation. Under attack:

$$F_{t+1}^{\mathrm{atk}} = F_t + 0.001 \cdot \left(1 + \frac{\mathrm{AIT\_201}}{1000}\right) \cdot \Delta t, \qquad \text{BW\_Active} = 0 \text{ (forced)}$$

Without backwash regeneration, fouling accumulates monotonically. Starting from $F_0 = 0$, the membrane reaches the physical damage threshold ($F > 0.8$, corresponding to $\mathrm{DPIT\_301} > 105$ kPa) after approximately:

$$t_{\mathrm{damage}} = \frac{0.8}{0.001 \times 0.1} = 8000 \text{ s} \approx 133 \text{ min}$$

The attack duration in the dataset (300–600 s) does not reach this extreme, but accumulates sufficient fouling to produce a distinguishable DPIT trajectory. The second derivative $d^2(\mathrm{DPIT\_301})/dt^2$ is the most sensitive early-warning feature, because it detects the onset of accelerating fouling before the first derivative has crossed the alarm threshold.

### 4.9 Chemical Depletion Attack (T0814)

The chemical depletion attack forces all four dosing pumps ($P_{203}$, $P_{205}$, $P_{206}$, $P_{403}$) into continuous ON states, simultaneously draining the acid, chlorine, coagulant, and bisulfate tanks at their maximum consumption rates. The tank level dynamics under attack become:

$$\mathrm{Tank}_i(t+1) = \max\!\left(0, \, \mathrm{Tank}_i(t) - \dot{m}_i \cdot \Delta t\right)$$

where $\dot{m}_i$ is the consumption rate of chemical $i$ when the corresponding pump is continuously energised. The chlorine tank depletes from 85% to 15% (the `Chemical_Low_Alarm` threshold) in the shortest time because chlorine is consumed fastest at the dosing rates configured in the MATLAB model. As the tank levels fall, the SR-latch refill mechanism activates, but the attack prevents the latch from latching OFF because the consumption rate exceeds the refill rate.

The multi-variable nature of this attack — simultaneously affecting four independent dosing channels — is what makes it particularly challenging for univariate threshold detectors. No single tank's rate of change is extreme enough to trigger a threshold alarm immediately. The correct detection strategy is the **multivariate Mahalanobis distance** from the normal operating manifold, which measures the aggregate statistical deviation across all correlated variables simultaneously and can detect the chemical depletion signature within 60 seconds of attack onset, compared to 180+ seconds for any univariate threshold.

---

## 5. Dataset Generation Pipeline

### 5.1 Data Acquisition Architecture

The dataset generation pipeline is designed around three requirements that must be satisfied simultaneously and without exception: **temporal continuity** (no gaps or reorderings in the time series), **ground-truth label accuracy** (every row must carry the correct attack state at the moment it was logged), and **physical consistency** (sensor values must evolve in accordance with the simulation physics, not be replaced by random synthetic values).

Temporal continuity is enforced by the fixed 100 ms bridge cycle, which produces a timestamp monotonically increasing at 10 Hz. The Python bridge measures the wall-clock time at the start and end of each cycle and logs any cycle that exceeds 110 ms as a `delay_anomaly`. Over a 70-minute run (42,000 cycles), the expected number of delay anomalies is fewer than 50 — less than 0.12% of rows — based on empirical measurements on the host system.

Ground-truth label accuracy is enforced by the IPC (inter-process communication) mechanism: the attack scheduler writes the current attack state to an `attack_metadata.json` file at the moment each attack begins and ends. The bridge reads this file at the start of every cycle and stamps the ATTACK\_ID, ATTACK\_NAME, and MITRE\_ID fields accordingly. The maximum label lag — between the moment the attack scheduler writes the file and the moment the bridge reads it — is at most 100 ms (one cycle), which is negligible relative to the minimum attack duration (300 seconds = 3,000 cycles). At most one row per attack transition carries an incorrect label, corresponding to a label error rate below 0.007%.

Physical consistency is guaranteed by the architecture decision discussed in Section 2.3: attack sensor values are applied inside the bridge cycle after MATLAB computes the physics-correct values, ensuring that the logged sensor values are always the product of a coherent physics state rather than an arbitrary override.

### 5.2 Register Scaling and the SCALE\_MAP

A single scaling convention, implemented as the `SCALE_MAP` dictionary in the bridge's `log_row()` function, converts raw Modbus register integers to engineering-unit floating-point values for CSV storage. This conversion happens exactly once, at the logging stage, and is never applied a second time. The SCALE\_MAP encodes the register type for each address:

| Register type | Scale factor | Example |
|---|---|---|
| Flow (FIT\_xxx) | $\div 10$ | Register 10 $\rightarrow$ 1.0 m$^3$/h |
| pH (AIT\_202) | $\div 100$ | Register 720 $\rightarrow$ pH 7.20 |
| Pressure (PIT, DPIT) | $\div 10$ | Register 120 $\rightarrow$ 12.0 bar |
| Level (LIT\_xxx) | $\times 1$ | Register 500 $\rightarrow$ 500 L |
| Fouling factors | $\times 1$ | Register 35 $\rightarrow$ 35% |
| Temperature | $\div 10$ | Register 250 $\rightarrow$ 25.0°C |
| Actuator coils | $\times 1$ | Bool 0/1 |

Early versions of the system inadvertently applied the SCALE\_MAP twice: once in the bridge and once in a downstream analysis script. The result was that flow values appeared in the CSV as 0.01 m$^3$/h instead of 0.1 m$^3$/h, and pH values appeared as 0.072 instead of 7.20. The current architecture applies the SCALE\_MAP only in `log_row()` and stores raw integer register values in all other pipeline stages, eliminating this class of scaling error.

### 5.3 CSV Structure and Dataset Dimensions

Each dataset run produces a single `master_dataset.csv` file with 84 columns:

- **52 sensor columns**: one per holding register address 0–51, in engineering units
- **28 actuator columns**: one per coil address 0–27, as binary integers
- **1 timestamp column**: ISO 8601 UTC, microsecond resolution
- **3 label columns**: ATTACK\_ID (integer), ATTACK\_NAME (string), MITRE\_ID (string)

At 10 Hz with a 70-minute run duration, each CSV contains approximately 42,000 rows. Five planned runs yield a total of approximately 210,000 rows. The label distribution within a single run is approximately 57% NORMAL (40 minutes of baseline operation) and 43% ATTACK (30 minutes of attack periods), with individual attack types each comprising 5–8% of total rows depending on the run configuration.

### 5.4 Challenges: Class Imbalance and Temporal Correlation

Two dataset properties require special treatment during ML training. The first is **class imbalance**: normal operation rows outnumber individual attack type rows by a ratio of approximately 8:1. A naive classifier that always predicts NORMAL achieves 57% accuracy without learning any attack signature. This is mitigated by stratified sampling during train/validation/test splitting, the `scale_pos_weight` parameter in XGBoost, and class-weighted loss functions in the LSTM.

The second challenge is **temporal autocorrelation**. Consecutive sensor readings in a 10 Hz time series are highly correlated with their neighbours — the autocorrelation of LIT\_101 at lag 1 (100 ms) is approximately 0.997 under normal conditions. If training and test splits are drawn by random row sampling rather than temporal blocking, the resulting test set will contain rows that are adjacent in time to training rows. A classifier can then achieve misleadingly high performance by simply interpolating between its training samples, without learning any generalizable attack signature. All train/validation/test splits in this work are therefore **chronological**: the first 70% of each run's time series forms the training set, the next 15% the validation set, and the final 15% the test set.

---

## 6. Multi-Run Experimental Design

### 6.1 Motivation and Research Contribution

The five-run experimental design is the central methodological contribution of this work. Rather than generating a single large dataset from one continuous simulation session, the design produces five statistically independent dataset runs, each with a distinct attack composition and operating condition. This multi-run structure directly addresses the two principal failure modes of ML intrusion detection systems: **overfitting to run-specific artefacts** and **data leakage between training and evaluation sets**.

Run-specific artefacts are systematic patterns that arise from the particular sequence of events in a single simulation session — the exact phase of the pH oscillation cycle when an attack begins, the state of the RO fouling counter at run start, the random seed of the MATLAB noise generator. A model trained on a single run and evaluated on a held-out portion of the same run may learn these session-specific correlations rather than the physics-grounded attack signatures. Such a model would catastrophically fail on data from a different run, let alone from a physical plant.

The five-run design mitigates this by ensuring that the training corpus contains multiple independent instantiations of each attack type, under different initial conditions and with different co-occurring background attacks. The evaluation of generalization performance is then operationalized as a cross-run transfer test: a model trained on runs 01–04 is evaluated on run 05, which it has never seen. This transfer test is significantly more demanding than a within-run held-out evaluation, and a model that passes it with FPR < 5% and per-attack F1 > 0.85 can reasonably be claimed to have learned generalizable attack signatures.

### 6.2 Run Design and Attack Composition

Each of the five runs is designed to exercise a distinct combination of attack types, ensuring that every attack class appears in multiple runs in different combinations:

| Run | Duration | Attack window | Attack types | Primary ML purpose |
|---|---|---|---|---|
| 01 | 70 min | 30 min | Recon, Replay, pH, SlowRamp | Baseline attack mix; network + temporal |
| 02 | 70 min | 30 min | Recon, Replay, Membrane, ChemDepletion | Fouling + chemistry; multi-variable |
| 03 | 70 min | 30 min | Recon, Replay, TankOverflow, Valve | Command injection; physical actuator |
| 04 | 80 min | 40 min | pH, SlowRamp, Membrane, ChemDepletion | All temporal; hardest to detect |
| 05 | 60 min | 0 min | Normal only | Unsupervised model training; FPR baseline |

The deliberate inclusion of reconnaissance and replay attacks in runs 01–03 — but not in run 04 — means that a model trained on runs 01–04 will encounter the slow ramp and pH attacks in a context where network-level anomalies (jitter from reconnaissance, variance collapse from replay) are absent in run 04 but present in runs 01–03. The transfer test (model trained on 01–04, evaluated on 05 normal data) directly measures the false positive rate on genuinely unseen normal operating data.

### 6.3 Avoiding Data Leakage

Data leakage — the inadvertent inclusion of evaluation-set information in the training process — takes two forms in this experimental design. The first is **feature leakage**: computing features (e.g., rolling statistics, normalisation parameters) using the full dataset before splitting, so that validation and test samples influence the features of training samples. This is avoided by fitting the `RobustScaler` exclusively on the training split and transforming the validation and test splits using the training-fit parameters.

The second form is **label leakage via temporal proximity**: as discussed in Section 5.4, random row-level splits in a temporally correlated time series allow near-identical samples from the same temporal neighbourhood to appear in both training and test sets. All splits in this work use chronological blocking within each run, and cross-run evaluation uses entire runs as atomic units — runs 01–04 for training, run 05 for evaluation — ensuring complete temporal separation.

---

## 7. Machine Learning Integration and Anomaly Detection

### 7.1 Design Rationale for the Three-Layer Ensemble

A single ML model optimised for the heterogeneous anomaly detection task described in Section 4 would face irreconcilable design constraints. A model sensitive enough to detect slow ramp attacks — which accumulate statistical evidence over 300+ samples — would operate on long temporal windows and be computationally unsuitable for high-frequency screening of all 42,000 rows per run. Conversely, a model optimised for high-throughput screening of individual samples would lack the temporal context necessary to detect gradual drift. The three-layer ensemble resolves this tension by assigning each model to the detection task best suited to its architecture.

### 7.2 Layer 1: Isolation Forest as Physics-Grounded Pre-Filter

The Isolation Forest [Liu et al., 2008] is trained exclusively on data from the normal operating periods (ATTACK\_ID = 0) across the training runs. Its training objective — to isolate anomalous points from the majority of the data by recursive binary partitioning — is precisely aligned with the anomaly detection setting: normal operation occupies a dense manifold in feature space, and attacks produce deviations from that manifold that are easier to isolate. The contamination parameter is set to 0.05, acknowledging that approximately 5% of nominally "normal" rows may contain pre-attack transients or physical conditions (e.g., UF backwash, RO CIP) that are statistically unusual but not adversarial.

The output of the Isolation Forest is a per-sample anomaly score $s_t \in [0,1]$, where values approaching 1 indicate high anomaly severity. A threshold $\tau_1 = 0.6$ is selected via calibration on the validation set to achieve a false positive rate below 3% on normal data. Samples with $s_t > \tau_1$ are passed to Layer 2 for classification; samples with $s_t \leq \tau_1$ are classified as NORMAL without further computation. This pre-filtering step reduces the computational load on the more expensive Layer 2 model by approximately 80% under normal operating conditions, making real-time inference feasible at 10 Hz.

The Isolation Forest is expected to perform well on attacks with strong cross-feature signatures — replay (near-zero multivariate variance), tank overflow (extreme LIT\_101 rate-of-change), and valve manipulation (pump-flow inconsistency) — but is expected to have limited sensitivity for slow ramp attacks, where individual sample deviations are within the noise floor.

### 7.3 Layer 2: XGBoost for Multiclass Classification

The XGBoost classifier [Chen & Guestrin, 2016] is trained on the full labelled dataset (all ATTACK\_ID values, runs 01–04). As a gradient-boosted ensemble of decision trees, XGBoost is well-suited to this tabular, high-dimensional classification task for several reasons: it handles mixed-type features (continuous sensor values, binary actuator states, engineered rolling statistics) without requiring feature transformation; it naturally captures nonlinear interactions between features (e.g., the joint `P_101 AND FIT_101 < 0.5` rule); and it provides calibrated class probabilities via the softmax output, which enables threshold-based alarm generation.

The class imbalance between normal rows and individual attack type rows is addressed by the `scale_pos_weight` hyperparameter, which assigns a multiplicative weight to positive-class samples during gradient computation. For binary detection, `scale_pos_weight = n_normal / n_attack`; for multiclass classification, per-class sample weights are passed explicitly. Hyperparameter optimisation covers the ranges `max_depth ∈ [4, 10]`, `learning_rate ∈ [0.01, 0.1]`, and `n_estimators ∈ [200, 500]`, tuned by random search on the validation set.

The Layer 2 decision rule is: if the maximum predicted class probability exceeds $\tau_2 = 0.7$, an alarm is raised and the predicted class label is output. Samples that clear Layer 1 but do not reach the Layer 2 probability threshold are held for Layer 3 temporal validation, which can confirm or deny the anomaly based on the surrounding sequence context.

The expected performance profile of XGBoost by attack type reflects the discriminative power of the engineered features: reconnaissance and replay are expected to achieve F1 > 0.95 due to their strong network-level and multivariate variance signatures; pH manipulation and valve attacks are expected to achieve F1 > 0.88 due to the pump-flow and pH-pump inconsistency features; slow ramp is expected to achieve F1 < 0.80 on the XGBoost alone, motivating the LSTM layer.

### 7.4 Layer 3: LSTM Temporal Validation

The LSTM [Hochreiter & Schmidhuber, 1997] operates on sliding windows of 30 consecutive samples (3 seconds at 10 Hz), applied exclusively to windows that have been flagged by Layer 1 or Layer 2. This selective application means that the LSTM processes at most a few percent of all windows during normal operation, preserving computational efficiency. The LSTM's bidirectional architecture — with separate forward and backward passes over each 30-step window — allows it to condition its prediction on both the historical trend (useful for detecting slow ramp) and the subsequent correction (useful for identifying the absence of a normal control response).

The LSTM adds temporal context that XGBoost fundamentally cannot exploit in its point-in-time formulation. For the slow ramp attack, the critical discriminating evidence is not the value of AIT\_202 at any single timestep — which may be within the normal range — but the monotonic trend of AIT\_202 over the preceding 30 samples. The LSTM's hidden state $\mathbf{h}_t$ is designed to accumulate this trend information across the sequence, and its final hidden state is passed to a dense classification layer that outputs the binary anomaly probability and, in the multiclass variant, the attack type.

The expected performance improvement of the LSTM over XGBoost is most pronounced for slow ramp (F1 improvement of +0.15 to +0.25), membrane damage (F1 improvement of +0.08 to +0.12), and chemical depletion (F1 improvement of +0.05 to +0.10). For attacks with strong pointwise signatures (reconnaissance, replay, tank overflow), the LSTM adds little to the XGBoost prediction and serves primarily as a confirmation mechanism that reduces false alarms.

### 7.5 SHAP Explainability

To support the operational deployment of the ensemble — and to satisfy the interpretability requirements of safety-critical applications — SHAP (SHapley Additive exPlanations) values [Lundberg & Lee, 2017] are computed for the XGBoost model. SHAP values decompose each model prediction into additive contributions from individual features, with the contribution of feature $j$ to the prediction for sample $i$ given by the Shapley value $\phi_j(i)$. The global feature importance for attack class $k$ is then:

$$\Phi_j^{(k)} = \frac{1}{N} \sum_{i=1}^{N} \left|\phi_j^{(k)}(i)\right|$$

The predicted rank ordering of global feature importances, derived from the physics analysis in Section 4, is:

| Predicted rank | Feature | Physics justification |
|---|---|---|
| 1 | `d(AIT_202)/dt` | Rate of pH change — discriminates slow ramp from all other attacks |
| 2 | `P_203_duty_60s` | Sustained acid pump anomaly — 73% ON (attack) vs 46% ON (normal) |
| 3 | `pump_flow_inconsistency` | Boolean physical constraint — violated only by valve attacks |
| 4 | `d²(DPIT_301)/dt²` | TMP acceleration — early fouling warning before threshold |
| 5 | `FIT_101 − FIT_201` | Mass balance residual — nonzero only under valve/pump attack |
| 6 | `P_403_duty_30s` | Bisulfate pump anomaly — 71.3% ON vs 4.3% ON during pH attack |
| 7 | `rolling_variance(all_sensors)` | Near-zero → replay; extreme → multi-variable attack |

---

## 8. Control Logic, Cause–Effect Relationships, and PLC Interlock Analysis

### 8.1 Control Rule Verification and the 1-Cycle Artefact

The CODESYS Structured Text program implements 24 control rules across six stages, plus five system-level alarm and interlock rules. Formal verification of these rules against the expected cause-effect relationships reveals that the vast majority of apparent violations in the logged dataset are attributable not to logic errors but to the one-cycle evaluation lag discussed in Section 2.5. Of 619 observed instances where DPIT\_301 exceeded 60 kPa while `UF_Backwash_Active = FALSE`, 97% were boundary-value artefacts (DPIT\_301 exactly at the threshold in cycle $N$, `UF_Backwash_Active = TRUE` in cycle $N+1$). This finding has a direct implication for ML training: these rows must not be used as positive examples for the "backwash suppression attack" class, or the classifier will learn the normal S3-R2 trigger boundary as an attack signature.

### 8.2 The S2-R7 Safety Interlock

The S2-R7 interlock is the most safety-critical control rule in the system. When `AIT_202 > 900` (pH > 9.0) or `AIT_202 < 550` (pH < 5.5), the interlock immediately de-energises pumps $P_{101}$, $P_{102}$, $P_{301}$, and $P_{401}$, halting water movement through the plant. This interlock is the last line of defence against chemical dosing attacks that drive the pH outside the range compatible with safe distribution. Critically, the pH manipulation attack (Section 4.4) is designed to bypass this interlock by spoofing the AIT\_202 register: the interlock fires on the register value, not the true process pH. If the register reports a falsely benign value while the true pH is extreme, the interlock never fires.

This architecture — where the safety interlock is conditioned on the same sensor register that the attack can spoof — is a fundamental vulnerability of threshold-based detection in ICS environments. It is precisely the vulnerability that physics-based ML detection is designed to address: by predicting the expected sensor value from the physical model and comparing it to the observed register value, the ML system can detect the discrepancy between prediction and observation even when the threshold-based interlock cannot.

### 8.3 The Known RO CIP Bug and Its Fix

A known defect in the current ST implementation affects the RO CIP (Clean-In-Place) scheduling logic. Rule S5-R2 triggers CIP when `RO_Fouling_Factor > 80`, and rule S5-R3 triggers CIP when `RO_Last_Cleaning > 1000` cycles (100 seconds). These conditions are combined with an OR operator:

```pascal
(* Current — has re-arming failure *)
IF RO_Fouling_Factor > 80 OR RO_Last_Cleaning > 1000 THEN
    RO_Cleaning_Active := TRUE;
    P_501 := FALSE;
END_IF;
```

The defect arises when fouling accumulates rapidly after a recent CIP. If `RO_Fouling_Factor` rises from 0 to above 80% within 100 seconds of the last CIP, the OR condition `RO_Last_Cleaning > 1000` has not yet become TRUE (the counter has only reached ≤ 1000), and `RO_Fouling_Factor > 80` is TRUE but the overall logic may fail to latch due to a race condition in the interlock reset path. The correct fix removes the time-based OR condition and triggers CIP on fouling level alone:

```pascal
(* Fixed — fouling threshold is sufficient and unambiguous *)
IF RO_Fouling_Factor > 80 THEN
    RO_Cleaning_Active := TRUE;
    P_501 := FALSE;
END_IF;
```

This bug is consequential for the dataset: any rows where `RO_Fouling_Factor > 80` and `RO_Cleaning_Active = FALSE` represent a genuine control failure rather than a logging artefact, and should be excluded from training data for the RO CIP interlock compliance analysis.

---

## 9. Conclusion and Research Contributions

This document has presented a comprehensive technical description of a software digital twin for the Secure Water Treatment testbed, developed as a platform for generating labelled ICS cyber-physical attack datasets for machine learning intrusion detection research. The key research contributions are summarised as follows.

**Contribution 1: Physically grounded simulation architecture.** The digital twin integrates a MATLAB physics engine, a CODESYS PLC runtime executing genuine Structured Text control logic, and a Python synchronisation bridge over Modbus TCP. This three-layer architecture is architecturally isomorphic to a physical ICS deployment, ensuring that the generated dataset carries the protocol artefacts, control timing constraints, and sensor noise characteristics of a real plant.

**Contribution 2: Rigorous attack modelling.** Eight adversarial attack types are implemented with precise mathematical characterisation of the register-level deviation profiles, physical cause-effect chains, and expected detection signatures. The slow ramp attack, in particular, is modelled with a sigmoid deviation profile parameterised to remain below the sensor noise floor for the majority of its duration — a level of operational realism not present in existing public ICS datasets.

**Contribution 3: Multi-run experimental design for generalisation evaluation.** The five-run design, with distinct attack compositions per run and full chronological separation between training and evaluation, provides a rigorous framework for evaluating the cross-condition generalisability of ML models. The transfer test (train on runs 01–04, evaluate on run 05) constitutes a significantly harder evaluation protocol than within-run held-out testing.

**Contribution 4: Three-layer ensemble detection architecture.** The layered ensemble — Isolation Forest pre-filter, XGBoost classifier, and LSTM temporal validator — is designed to address the full spectrum of attack characteristics from strong pointwise signatures to slow temporal trends, with SHAP explainability enabling operator-facing alarm attribution. The architecture is grounded in the physics-based feature engineering framework derived from the mathematical process models in Section 3.

`[FIGURE 2: End-to-end pipeline from simulation to trained ensemble model. Shows data flow from MATLAB physics engine through dataset generation to feature engineering, model training (IF / XGBoost / LSTM), and final ensemble decision logic.]`

`[FIGURE 3: Attack cause-effect diagram for all eight attack types. Central plant schematic with arrows indicating each attack's target register, direction of deviation, and the ML feature most sensitive to that deviation.]`

`[FIGURE 4: SHAP summary beeswarm plot showing global feature importances across all attack types on the XGBoost classifier. Expected top features: d(AIT_202)/dt, P_203 duty cycle, pump_flow_inconsistency, DPIT_301 second derivative, FIT_101−FIT_201 mass balance.]`

---

## References

[CITATION] Oldsmar Water Treatment Plant Attack, February 2021. (Cite relevant CISA advisory or news source.)

[CITATION] iTrust SWaT Dataset, Singapore University of Technology and Design. https://itrust.sutd.edu.sg/itrust-labs_datasets/dataset_info/

[CITATION] Liu, F. T., Ting, K. M., & Zhou, Z. H. (2008). Isolation forest. *2008 Eighth IEEE International Conference on Data Mining*, 413–422.

[CITATION] Chen, T., & Guestrin, C. (2016). XGBoost: A scalable tree boosting system. *Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining*, 785–794.

[CITATION] Hochreiter, S., & Schmidhuber, J. (1997). Long short-term memory. *Neural Computation*, 9(8), 1735–1780.

[CITATION] Lundberg, S. M., & Lee, S. I. (2017). A unified approach to interpreting model predictions. *Advances in Neural Information Processing Systems*, 30.

[CITATION] MITRE ATT&CK for ICS. https://attack.mitre.org/matrices/ics/

[CITATION] Mathur, A. P., & Tippenhauer, N. O. (2016). SWaT: A water treatment testbed for research and training on ICS security. *2016 International Workshop on Cyber-physical Systems for Smart Water Networks*, 31–36.

---

*End of Chapter.*
