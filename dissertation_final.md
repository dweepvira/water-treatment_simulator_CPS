# Attack Detection System in Smart City Water Treatment Plants

**Dissertation submitted in partial fulfillment of the requirement of the M.Tech degree**

**By:** Dweep Vira (242240018)
**Under the Guidance of:** Dr. S. S. Udmale

Department of Computer Engineering and Information Technology
Veermata Jijabai Technological Institute (VJTI)
(An Autonomous Institute Affiliated to Mumbai University)
(Central Technological Institute, Maharashtra State)
Matunga, Mumbai – 400019

A.Y. 2025–2026

---

## Statement of Candidate

I state that work embodied in this report entitled "Attack Detection System in Smart City Water Treatment Plants" forms my own contribution of work under the guidance of Dr. S. S. Udmale at the Department of Computer Engineering, Veermata Jijabai Technological Institute, Mumbai. The report reflects the work done during the period of candidature but may include related preliminary material provided that it has not contributed to an award of previous degree. No part of this work has been used by us for the requirement of another degree except where explicitly stated in the body of the text and the attached statement.

**Student Name:** Dweep Vira
**Roll No.:** 242240018
**Date:**
**Place:** VJTI, Mumbai

---

## Abstract

Labelled cyber-physical datasets for industrial control system (ICS) intrusion detection research are scarce, expensive to collect, and ethically constrained. Physical testbeds cannot be subjected to adversarial manipulation at scale, and the widely used iTrust Secure Water Treatment (SWaT) dataset is limited in attack diversity, temporal resolution, and reproducibility.

This research presents the design and implementation of a high-fidelity software digital twin of the six-stage SWaT water treatment plant, built as a reproducible platform for labelled attack dataset generation and machine learning-based intrusion detection research. The twin integrates:

- A **MATLAB** ordinary differential equation physics engine
- A **CODESYS** IEC 61131-3 Structured Text PLC runtime
- A **Modbus TCP** synchronisation bridge operating at 10 Hz

Eight cyber-physical attack scenarios mapped to MITRE ATT&CK for ICS are injected across two long-duration continuous logs:
- A baseline dataset of approximately **24 hours** of normal plant operation
- An attack dataset of approximately **24 hours** in which attack traffic constitutes the majority of records

Each dataset contains **84 columns**, including 52 sensor registers reported in engineering units, 28 actuator coil states, a UTC timestamp, and ground-truth attack labels for each row.

The study introduces a **three-level feature engineering** approach where physical process knowledge guides feature construction; the resulting features are used for unsupervised and supervised learning. Attack injection occurs within the bridge cycle, and labels are assigned during the same cycle — preventing temporal misalignment between labels and data.

This work addresses an important data limitation in ICS security research by providing an open-source and reproducible pipeline that converts plant simulations into attack-labelled training data for temporal machine learning models.

---

## Table of Contents

- List of Abbreviations — vi
- **Chapter 1: Introduction** — 1
  - 1.1 Background
  - 1.2 Motivation
  - 1.3 Research Contribution
  - 1.4 System Overview
  - 1.5 Aim and Objectives
  - 1.6 Dissertation Outline
- **Chapter 2: Problem Statement** — 8
  - 2.1 Problem Definition
  - 2.2 Limitations of Existing Approaches
  - 2.3 Scope of the Research
  - 2.4 Research Hypotheses
- **Chapter 3: Literature Survey** — 12
  - 3.1 The ICS/SCADA Threat Landscape and Vulnerabilities
  - 3.2 Research Infrastructure: Testbeds, Datasets, and Honeypots
  - 3.3 Cyber-Physical Attack Vectors in Water Treatment Systems
  - 3.4 Machine and Deep Learning for ICS Intrusion Detection
  - 3.5 Evaluation Metrics for Temporal Anomaly Detection
- **Chapter 4: Methodology** — 18
  - 4.1 System Overview
  - 4.2 Plant Physics Model
  - 4.3 PLC Control Logic and Cause-Effect Map
  - 4.4 Bridge Synchronisation and Data Logging
  - 4.5 Attack Library and Orchestration
  - 4.6 Dataset Structure and Experimental Design
  - 4.7 Feature Engineering Strategy
  - 4.8 Ensemble Learning Framework
  - 4.9 Summary of the Research Framework
- **Chapter 5: Experimental Setup and Results** — 33
  - 5.1 Experimental Setup
  - 5.2 Results and Analysis
  - 5.3 Summary of Findings
- **Chapter 6: Conclusion and Future Work** — 45
  - 6.1 Summary of Contributions
  - 6.2 Future Work
- Bibliography — 49
- Appendix A: Research Paper — 51
- Appendix B: Plagiarism and AI Reports — 64

---

## List of Figures

| # | Title | Page |
|---|---|---|
| 4.1 | High-level architecture of the SWaT digital twin | 19 |
| 4.2 | Cause-effect logic flow of the CODESYS Structured Text control programme | 22 |
| 4.3 | The five-step atomic cycle of the orchestration bridge | 23 |
| 4.4 | Three-tier physics-driven feature engineering pipeline | 27 |
| 4.5 | Two-tier ensemble machine learning pipeline for ICS intrusion detection | 29 |
| 5.1 | ROC curves for each pipeline layer on the held-out test set | 38 |
| 5.2 | F1-score per pipeline layer on the held-out test set | 39 |
| 5.3 | Ensemble confusion matrix on the held-out test set | 40 |
| 5.4 | SHAP feature importance for the XGBoost ensemble component | 42 |

## List of Tables

| # | Title | Page |
|---|---|---|
| 4.1 | Condensed cause-effect map of the Stage 1 and Stage 2 PLC control logic | 22 |
| 4.2 | Attack classes, MITRE identifiers, physical mechanisms, and primary detection signals | 24 |
| 4.3 | Research framework design decisions and corresponding problem motivations | 32 |
| 5.1 | Summary statistics of the two experimental datasets | 34 |
| 5.2 | Ensemble model configurations and training data sources | 35 |
| 5.3 | Model-wise binary detection performance on the held-out test set | 37 |
| 5.4 | Ensemble binary classification report on the held-out test set (263,040 windows) | 38 |
| 5.5 | Per-attack-type ensemble performance on the held-out test set | 39 |
| 5.6 | Mapping of research hypotheses to experimental outcomes | 43 |

---

## List of Abbreviations

1. **ICS** — Industrial Control System
2. **SCADA** — Supervisory Control and Data Acquisition
3. **SWaT** — Secure Water Treatment
4. **PLC** — Programmable Logic Controller
5. **HMI** — Human-Machine Interface
6. **OT** — Operational Technology
7. **IT** — Information Technology
8. **FDI** — False Data Injection
9. **ODE** — Ordinary Differential Equation
10. **LSTM** — Long Short-Term Memory
11. **CNN** — Convolutional Neural Network
12. **SHAP** — SHapley Additive exPlanations
13. **TaPR** — Time-series Aware Precision and Recall
14. **MITRE ATT&CK** — MITRE Adversarial Tactics, Techniques, and Common Knowledge
15. **FIT** — Flow Indicating Transmitter
16. **LIT** — Level Indicating Transmitter
17. **PIT** — Pressure Indicating Transmitter
18. **DPIT** — Differential Pressure Indicating Transmitter
19. **AIT** — Analyzer Indicating Transmitter
20. **TMP** — Trans-Membrane Pressure
21. **RO** — Reverse Osmosis
22. **UV** — Ultraviolet

---

# Chapter 1: Introduction

## 1.1 Background

Critical infrastructure widely employs Industrial Control Systems (ICS) and Supervisory Control and Data Acquisition (SCADA) platforms — examples are power grids and water distribution networks. These systems link digital control functions to physical processes; their decisions directly affect plant operations. In the past, OT networks have been separated from IT networks, but the increase in connectivity between both environments has expanded the attack surface. Consequently, attackers can attack physical processes through digital attacks [1].

The **February 2021 attack on a water treatment facility in Oldsmar, Florida** illustrated the severity of this threat in practice. An attacker who had gained remote access to the SCADA system pushed the sodium hydroxide concentration to **111 times** above the permitted regulatory ceiling — an action accomplished within five minutes and one that placed approximately **15,000 residents** at risk [2]. Crucially, the malicious Modbus write commands were syntactically identical to routine operator commands. Packet-level inspection therefore offers no reliable basis for distinguishing attack traffic from legitimate control activity. Reliable detection must instead be grounded in the physical process: deviations between observed sensor trajectories and the behaviour predicted by a process model expose attacks that are invisible at the network layer.

Despite this growing threat, high-quality security datasets for ICS environments remain extremely scarce. Physical testbeds are costly to build and operate; the iTrust Secure Water Treatment (SWaT) facility at the Singapore University of Technology and Design required approximately **USD 1 million** to construct and depends on real chemicals, membranes, and pumps to function. Conducting repeated adversarial experiments on such infrastructure is both unsafe and impractical. The publicly available iTrust dataset covers only **36 attack scenarios**, all recorded at 1 Hz under a single operating configuration and without coil-state information or sub-second attack labels. A consistent finding in the literature is that models trained on this dataset memorise run-specific statistical fingerprints rather than generalisable attack characteristics, so high training accuracy does not reliably indicate strong detection capability on held-out data.

A software digital twin offers a principled route around these constraints. Attack scenarios can be injected into the simulation without any risk to physical equipment or personnel. Because the orchestration layer records the active attack class at each logging cycle, ground-truth labels are generated automatically and with sub-cycle precision. The entire pipeline can be reconstructed from source code, enabling researchers to regenerate or extend the dataset under varied operating conditions without requiring access to the original hardware.

## 1.2 Motivation

Two compounding problems motivate this research.

**The first is a data problem.** No publicly available dataset simultaneously provides sufficient attack diversity, temporal resolution, engineering-unit fidelity, and cross-condition variability to train and fairly evaluate temporal machine learning models on ICS process data. The widely referenced iTrust SWaT dataset — the most credible physical-testbed resource in the field — was logged at 1 Hz under a single operating condition and lacks coil-state records. Supervised models trained on it learn run-specific statistical fingerprints rather than generalisable attack signatures.

**The second is a detection methodology problem.** Existing approaches predominantly apply standard classification metrics to single-step sensor snapshots, discarding the temporal autocorrelation structure of process data. A slow-ramp pH attack drifting at 0.004 pH units/s lies below both human perception thresholds and PLC interlock trip points throughout its entire duration. Such an attack is undetectable by any single-step classifier, yet is statistically distinguishable from normal operation by a model that evaluates the cumulative trajectory over a temporal window. The discriminative signal is a **velocity anomaly**, not a positional one.

### Three consequences follow from these problems:

**First**, threshold-based alarms embedded in PLC Structured Text interlocks are structurally blind to any attack that remains within the configured interlock band. The slow-ramp attack, for example, applies a sigmoid-modulated drift profile to the pH sensor register:

$$s(t) = \frac{1}{1 + e^{-(10t/T - 5)}} \quad (1.1)$$

where $T = 600\,\text{s}$ yields a maximum instantaneous drift rate of:

$$\left.\frac{ds}{dt}\right|_{max} = \frac{2.5}{T} = 0.004 \text{ pH units/s} \quad (1.2)$$

well below the ST interlock trip points (pH < 5.5 or pH > 9.0). A labelled dataset capturing the full temporal trajectory of such gradual anomalies is a prerequisite for training sequential detectors.

**Second**, multi-variable correlated attacks such as chemical depletion — which forces all four dosing pumps active simultaneously — produce signatures invisible to any single-feature threshold but geometrically separable in higher-dimensional sensor space via Mahalanobis distance or autoencoder reconstruction error. Generating co-labelled data for all 52 sensor registers and 28 coil states in a single temporally continuous log enables such multivariate analyses without manual alignment.

**Third**, reproducibility is a prerequisite for scientific comparability. The proposed system uses a deterministic physics engine based on explicit ordinary differential equations, along with a fixed register-scaling map. These components allow researchers to regenerate the same dataset from open-source resources, so experimental results can be compared across institutions without access to the original iTrust hardware.

## 1.3 Research Contribution

This study presents a high-fidelity software digital twin of the six-stage SWaT water treatment plant, providing a reproducible environment for generating labelled attack datasets and supporting research on machine learning-based intrusion detection.

The system integrates three communicating components:
- A **MATLAB** ordinary differential equation physics engine
- A **CODESYS** IEC 61131-3 Structured Text PLC runtime
- A **Python orchestration bridge** synchronising actuator and sensor state over Modbus TCP in a deterministic **100 ms cycle**

Attack injection occurs inside the bridge cycle, guaranteeing zero label-data temporal misalignment.

Two long-duration continuous logs are collected at **10 Hz**:
1. A **24-hour normal-only baseline** dataset providing the reference distribution for unsupervised anomaly detection and feature normalisation.
2. A **24-hour attack dataset** in which attack traffic constitutes the majority of records, covering eight MITRE ATT&CK-aligned attack categories with perfect per-row ground-truth labels.

Each log contains **84 columns** comprising 52 sensor registers in engineering units, 28 actuator coil states, a UTC timestamp, and three label fields.

A three-tier physics-driven feature engineering strategy is developed to support both unsupervised anomaly detection and supervised multi-class classification. Detection is performed by an ensemble learning framework comprising:
- An **Isolation Forest** and an **Autoencoder** for unsupervised anomaly detection
- An **XGBoost** classifier combined with a **bidirectional LSTM** network for supervised multi-class attack classification

Final attack predictions are produced by soft-voting over the XGBoost and LSTM probability outputs. All models are evaluated under both sample-level and event-level time-series aware precision and recall (TaPR) metrics.

## 1.4 System Overview

The digital twin comprises three communicating software components that together replicate the sensing, control, and actuation layers of the six-stage SWaT water treatment plant. The components operate within a deterministic **100 ms cycle**, mirroring the two-level network hierarchy of the physical iTrust SWaT testbed.

1. **MATLAB Physics Engine**: Listens on TCP port 9501 and computes the full plant state at each $\Delta t = 0.1\,\text{s}$ timestep. Input is an actuator-state vector (pump and valve booleans); output is a sensor-register vector covering all six treatment stages. The framework models plant dynamics through explicit ordinary differential equations, so sensor readings evolve continuously and remain physically consistent with the underlying process rather than being generated by statistical interpolation.

2. **Modbus TCP Bridge**: Executes a strictly ordered five-step cycle every 100 ms:
   - Step 1: Pump/valve coil states and motorised valve position registers are read from CODESYS via Modbus FC1 and FC3.
   - Step 2: The actuator state vector is forwarded to the physics engine over TCP.
   - Step 3: On receipt of the updated sensor-register vector, any active attack override is applied within the same cycle — inserted after the physics engine response and before the CODESYS write operation.
   - Step 4: The bridge bulk-writes all 52 sensor holding registers to CODESYS via Modbus FC16.
   - Step 5: It applies the register-to-engineering-unit scaling map, reads the current attack label, and appends a new row to the master CSV log.

3. **CODESYS PLC Runtime**: Executes IEC 61131-3 Structured Text control logic at its native scan rate, reading sensor values from the holding registers populated by the bridge and asserting actuator coils accordingly. Control decisions follow hysteresis-band setpoint rules and hard-trip safety interlocks.

A strict **register-ownership convention** governs the entire twin: sensor holding registers (Modbus addresses 0–51) are written exclusively by the Python bridge; actuator coils (addresses 0–27) are written exclusively by the CODESYS Structured Text programme. This partitioning eliminates register conflicts and preserves the integrity of valve-state data throughout the dataset.

The twin models all six treatment stages:
- **Stage S1**: Raw water intake — `LIT_101`, `FIT_101`
- **Stage S2**: Chemical dosing — `AIT_202`, `AIT_201`
- **Stage S3**: Ultrafiltration — `DPIT_301`, `UF_Fouling_Factor`
- **Stage S4**: UV treatment and dechlorination — `UV_401`, `P_403`
- **Stage S5**: Reverse osmosis — `PIT_501`, `RO_Fouling_Factor`
- **Stage S6**: Treated-water distribution — `FIT_601`, `P_601`, `P_603`

### Plant Physics Model

**Stage 1 — Tank Mass Balance**

The tank volume $V$ (litres) follows the conservation-of-mass ODE:

$$\frac{dV}{dt} = Q_{in}(t) - Q_{out}(t) \quad (1.3)$$

$Q_{in}$ is the inlet flow rate controlled by motorised valve MV_101; $Q_{out}$ is determined by a level-staged pump characteristic. LIT_101 is clamped to [0, 1000] L. Under normal PLC operation, LIT_101 remains within the hysteresis band of **449 to 851 L**, exhibiting periodic behaviour with a cycle time of approximately **67 seconds** and a measured standard deviation of approximately **117 L**.

**Stage 2 — pH Buffer Kinetics**

Modelled using a first-order ODE representing buffer depletion behaviour, consistent with bicarbonate buffer reaction kinetics:

$$\frac{d(\text{pH})}{dt} = -\frac{\text{pH}(t) - \text{pH}_{target}}{\tau_{pH}} + \varepsilon(t), \quad \varepsilon(t) \sim \mathcal{N}(0, \sigma_{pH}^2) \quad (1.4)$$

Buffer time constant $\tau_{pH} = 40\,\text{s}$; measurement noise $\sigma_{pH} = 0.01$ pH units. The analytical solution:

$$\text{pH}(t) = \text{pH}_{target} + (\text{pH}_0 - \text{pH}_{target})e^{-t/\tau_{pH}} \quad (1.5)$$

The response reaches 63.2% of its final value after 40 s and 99.3% after 200 s. The pH target is 6.80 when acid dosing pump P203 is active; 8.50 when inactive. These targets implement the hysteresis-band pH control strategy.

**Stage 3 — Membrane Fouling (Darcy's Law)**

The dimensionless UF fouling factor $F \in [0, 1]$ accumulates as:

$$\frac{dF}{dt} = \alpha \cdot \left(1 + \frac{\text{AIT\_201}}{1000}\right) \cdot \Delta t, \quad \alpha = 0.001\,\text{s}^{-1} \quad (1.6)$$

giving trans-membrane pressure $\text{DPIT\_301} = 25 + F \times 100$ kPa. A backwash cycle is initiated when DPIT_301 exceeds 60 kPa, or if 30 minutes have passed since the previous backwash cycle. Under normal conditions, this results in a natural cycling period of approximately **28–32 minutes**.

**Sensor Noise Model**

Physical sensor noise originates from several independent sources (thermal fluctuations, EMI, mechanical vibration, ADC quantisation). By the Central Limit Theorem, this aggregate converges to a zero-mean Gaussian distribution:

$$x_{meas}(k) = x_{true}(k) + \varepsilon(k), \quad \varepsilon(k) \sim \mathcal{N}(0, \sigma_s^2) \quad (1.7)$$

Per-sensor standard deviations calibrated to representative industrial specifications:
- $\sigma_{AIT\_202} = 0.04$ pH
- $\sigma_{LIT\_101} = 6$ L
- $\sigma_{PIT\_501} = 3.0$ bar
- $\sigma_{DPIT\_301} = 1.0$ kPa
- $\sigma_{FIT\_101} = 0.2\,\text{m}^3/\text{h}$

## 1.5 Aim and Objectives

**Primary aim**: To develop and validate a high-fidelity software digital twin of the SWaT water treatment plant, designed to generate reproducible and physics-consistent attack datasets with ground-truth labels, and to design and evaluate a machine learning pipeline for multi-class cyber-attack detection.

### Specific Objectives:

- **Digital Twin Construction**: Implement a three-component digital twin (MATLAB physics engine, CODESYS PLC runtime, Modbus TCP bridge) reproducing six-stage SWaT plant behaviour via explicit ODEs, synchronised at 100 ms cycles.

- **Attack Library**: Implement eight cyber-physical attack scenarios mapped to MITRE ATT&CK for ICS: Reconnaissance (T0840), Replay (T0839), pH Manipulation (T0836), Slow Ramp (T0836), Tank Overflow (T0816), Valve Manipulation (T0849), Membrane Damage (T0836), and Chemical Depletion (T0814). A phase-structured orchestration algorithm guarantees complete attack-class coverage.

- **Dataset Generation**: Collect two continuous logs at 10 Hz, each spanning ~24 hours. Each log comprises 84 columns (52 sensor registers, 28 coil states, timestamp, ground-truth labels). Attack injection is performed within the bridge cycle to guarantee temporal alignment.

- **Feature Engineering**: Develop a three-tier physics-driven feature engineering strategy:
  - Tier 1: Scaled raw sensor and actuator coil features
  - Tier 2: Physics-derived features (rate of change, mass-balance residual, pump-flow consistency, duty cycle, Mahalanobis distance)
  - Tier 3: Temporal sequence tensors for LSTM input

- **Ensemble Learning Framework**: Design an ensemble intrusion detection system using Isolation Forest and Autoencoder (unsupervised) plus XGBoost and bidirectional LSTM (supervised), combined via soft-voting. Evaluated with sample-level and event-level TaPR metrics. Dataset 1 = normal baseline; Dataset 2 = attack evaluation.

- **Reproducibility**: Ensure the entire pipeline is reproducible using open-source components, with no physical hardware, chemical reagents, or proprietary infrastructure required.

## 1.6 Dissertation Outline

- **Chapter 2 (Problem Statement)**: Characterises dataset scarcity and detection-methodology gaps, analyses structural limitations of threshold-based control logic, and motivates the digital twin approach.
- **Chapter 3 (Literature Survey)**: Examines prior work on ICS cybersecurity, physics-based anomaly detection, digital twin platforms, and temporal deep learning for SCADA intrusion detection.
- **Chapter 4 (Methodology)**: Describes the digital twin architecture, physics models, PLC control logic, bridge synchronisation, attack orchestration, feature engineering, and ensemble learning framework.
- **Chapter 5 (Results and Analysis)**: Presents dataset validation results, normal operating characterisation, attack signatures, and ML model performance.
- **Chapter 6 (Conclusion and Future Work)**: Summarises contributions, discusses limitations, and outlines future research directions.

---

# Chapter 2: Problem Statement

## 2.1 Problem Definition

The central problem addressed is the **lack of a reproducible, high-fidelity, and well-labelled dataset** for ICS intrusion detection research. Cyber-physical attacks (false data injection, slow-ramp sensor manipulation, coordinated actuator attacks) can bypass conventional network security and threshold-based control logic because attack traffic often appears as valid Modbus communication — packet-level monitoring alone is insufficient.

### Two related problems:

**Data availability problem**: The widely used iTrust SWaT dataset [3] contains only 36 attack instances, collected at 1 Hz under a single operating condition, without coil-state information or sub-second attack labels. Models trained on it overfit to run-specific statistical artefacts.

**Detection methodology problem**: Existing approaches apply standard classification metrics to single-step sensor snapshots, discarding temporal autocorrelation. A slow-ramp pH attack drifting at 0.004 pH units/s is undetectable by any single-step classifier, yet statistically distinguishable from normal operation via cumulative trajectory analysis over a temporal window — the discriminative signal is a **velocity anomaly**, not a magnitude anomaly.

This research addresses both problems through a software digital twin generating physics-consistent, labelled attack datasets at 10 Hz across two long-duration logs, covering eight MITRE ATT&CK-aligned attack categories with perfect ground-truth labels and 84 attributes per row.

## 2.2 Limitations of Existing Approaches

### 2.2.1 Rule-Based and Threshold Interlock Systems

Threshold interlocks provide deterministic, low-latency protection against overt deviations but are structurally blind to attacks remaining within the configured interlock band. The pH safety trip activates only when pH < 5.5 or pH > 9.0; a slow-ramp attack driving pH from 7.2 to 8.9 over ten minutes never crosses either threshold. The membrane backwash interlock triggers only when DPIT_301 > 60 kPa; an attack suppressing the backwash coil prevents the very protective mechanism, allowing fouling to accumulate without alarm.

### 2.2.2 Static Single-Step Machine Learning Classifiers

Decision Trees, Random Forests, and feedforward neural networks evaluate each snapshot independently, discarding autocorrelation structure. A model trained on a single run learns the run-specific fingerprint (initial conditions, fill cycles) rather than transferable attack physics — high reported training accuracy in SWaT literature often reflects run-specific memorisation.

### 2.2.3 Absence of Physical Consistency Validation

Real plant dynamics are constrained by physical laws (mass conservation: $Q_{in} \approx Q_{out}$; pump-flow consistency: $P\_101 = 1 \Rightarrow \text{FIT\_101} > 0$). Attacks such as valve manipulation and tank overflow violate these constraints in ways invisible to models evaluating sensor values in isolation, but highly discriminative via mass-balance residuals and actuator-flow consistency features. Existing studies have largely neglected such domain-knowledge feature engineering.

### 2.2.4 Dataset Scarcity and Limited Reproducibility

The original SWaT testbed costs ~USD 1 million, requires physical chemicals/membranes, and cannot easily vary operating conditions. Deliberate attack injection carries safety/regulatory risk. Most published results are evaluated on a single shared, non-reproducible dataset. The digital twin resolves this via a fully open-source, deterministic simulation pipeline.

## 2.3 Scope of the Research

**Simulation Environment**: Three communicating components — MATLAB physics engine (explicit ODEs, $\Delta t = 0.1$ s), CODESYS PLC runtime (IEC 61131-3 Structured Text, hysteresis controllers, interlocks, backwash scheduling), and Modbus TCP bridge (100 ms deterministic cycle).

**Attack Library**: Eight attacks mapped to MITRE ATT&CK for ICS: Reconnaissance Scan (T0840), Replay (T0839), pH Manipulation (T0836), Slow Ramp (T0836), Membrane Damage (T0836), Chemical Depletion (T0814), Tank Overflow (T0816), Valve Manipulation (T0849). Automated orchestration guarantees complete attack-class coverage via phase-structured scheduling with cooldown periods and seeded pseudorandom scheduling for reproducibility.

**Dataset Specification**: Two ~24-hour datasets at 10 Hz. Dataset 1 = normal only (baseline for anomaly detection/normalisation); Dataset 2 = normal + attacks (attack records form majority). Each dataset: 84 columns (52 sensor registers in engineering units, 28 actuator coil states, UTC timestamp at microsecond resolution, plus ATTACK_ID, ATTACK_NAME, MITRE_ID labels). Labels assigned inside the bridge execution cycle (max label lag: 100 ms). Scaling map applied once during logging to prevent double-scaling.

**Boundaries**: Scoped to the six-stage SWaT architecture. Does not simulate network packet delays or Modbus framing errors. Hardware-in-the-loop deployment on embedded edge devices is out of scope, reserved for future research.

## 2.4 Research Hypotheses

**Null Hypothesis (H0)**: The proposed ensemble detection framework does not achieve a statistically significant improvement in F1-score compared with individual models, and the two-dataset configuration provides no measurable advantage over training/testing on a single run.

**Alternate Hypothesis (H1)**: The bidirectional LSTM will outperform single-step classifiers on gradually developing attack signatures, with the largest gains on Slow Ramp and Membrane Damage classes. The soft-voting ensemble will achieve performance equal to or better than any individual model across all eight attack classes.

**Supporting Hypothesis (H2)**: Physics-derived features (rate of change of AIT_202, pump-flow consistency indicator, mass-balance residual between FIT_101 and FIT_201) will rank among the most important features used by XGBoost, as measured by SHAP values, for process-level attack detection.

---

# Chapter 3: Literature Survey

## 3.1 The ICS/SCADA Threat Landscape and Vulnerabilities

Tariq et al. (2023) identify a key difference between IT security requirements (confidentiality/integrity) and OT operational requirements (availability, predictable real-time operation) [1], leading to legacy, unpatched OT systems and insecure fieldbus protocols. Alanazi et al. (2023) identify common SCADA attack surfaces: Modbus, operating systems, and HMIs [4]. D'Ambrosio et al. (2023) demonstrated SCADA compromise methods in lab environments [5], showing perimeter-based security alone is insufficient. Laiani et al. (2023) examined water-sector attack scenarios with serious physical consequences (incorrect chemical dosing, disrupted disinfection) [2].

The **2021 Oldsmar incident** demonstrated practical impact: an unauthorised user increased sodium hydroxide concentration to 111× the permitted safe level within a short period, without exploiting any software vulnerability — only the gap between valid protocol commands and unsafe process actions. This highlights that network-based monitoring alone is insufficient; effective detection must consider the physical process state.

## 3.2 Research Infrastructure: Testbeds, Datasets, and Honeypots

### 3.2.1 Testbeds and Simulators

Davis et al. (2023) describe SCADA testbed design requirements integrating physical simulation, control logic, network traffic generation, and HMI visualisation [6]. Teixeira et al. (2023) show simulators can generate labelled training/evaluation data [7]. Mughaid et al. (2023) examined simulation environments for edge computing applications [8].

The **SWaT testbed**, operated by iTrust (Singapore University of Technology and Design) [3], is described by Goh et al. (2016) as a fully operational scaled-down plant producing 5 gallons/minute of doubly filtered water through six stages: raw water intake (P1), chemical pre-treatment (P2), ultrafiltration (P3), UV dechlorination (P4), reverse osmosis (P5), treated water distribution (P6). It contains 51 sensors/actuators including FIT-101/201/301, LIT-101/301/401, AIT-202/402, DPIT-301, PIT-501/502/503, MV-101 to MV-304, and various dosing pumps (HCl, NaOCl, NaCl, NaHSO3).

### 3.2.2 The iTrust SWaT Dataset: The Foundational Work

Goh et al. (2016) collected data continuously over **11 days** — 7 days normal operation (5–6 hours to reach steady state) and 4 days with 36 injected attacks. All **946,722 samples** (51 attributes at 1 Hz) were consolidated into a single CSV with manually maintained attack logs. Network traffic was captured simultaneously.

The attack taxonomy uses a formal CPS attack model $(M, G, D, P, S_0, S_e)$, classifying attacks into four structural categories: Single Stage Single Point (SSSP, 26 attacks), Single Stage Multi Point (SSMP, 4), Multi Stage Single Point (MSSP, 2), Multi Stage Multi Point (MSMP, 4).

### 3.2.3 Limitations of the Original SWaT Dataset

- Only 36 attack instances/11 categories — insufficient for modern ML approaches.
- Fixed 1 Hz logging rate — misses sub-second process changes.
- Single plant run/operating condition — models overfit run-specific artefacts (e.g., tank-filling phase).
- No sub-second ground-truth labels — restricts sequential learning models like LSTMs.

### 3.2.4 Honeypots for Threat Intelligence

Meier et al. (2023) examined improving ICS honeypot realism [9]. Serbanescu et al. (2023) proposed a modular honeypot architecture emulating industrial devices/protocols [10].

## 3.3 Cyber-Physical Attack Vectors in Water Treatment Systems

Do et al. (2023) investigate sequential SCADA monitoring, recognising attacks as ordered action sequences [11] — relevant to the slow-ramp pH attack whose maximum instantaneous slope $\left.\frac{ds}{dt}\right|_{max} = \frac{2.5}{T}$ (Eq. 3.1) stays below perception/interlock thresholds for the entire 600-second duration.

Moazeni and Khazaei (2023) model sequential FDI attacks on water storage tanks via bi-level optimisation, constructing vectors maximising impact while minimising threshold-detection probability [12]. Giannubilo et al. (2023) proposed deep learning for FDI detection in smart water infrastructure [13].

The attack taxonomy in this twin extends Goh et al.'s classification, mapping all eight attacks to MITRE ATT&CK for ICS: network-level (Reconnaissance T0840, Replay T0839), process-level (pH Manipulation T0836, Slow Ramp T0836, Membrane Damage T0836, Chemical Depletion T0814), and command-injection (Tank Overflow T0816, Valve Manipulation T0849).

## 3.4 Machine and Deep Learning for ICS Intrusion Detection

Pinto et al. (2023) reviewed ML/DL techniques for critical infrastructure protection, finding hybrid/deep learning approaches show strong potential for zero-day detection [14].

### 3.4.1 Deep Learning Applications in Water Systems

Sikder et al. (2023) proposed **Deep H2O**, a deep learning framework for water distribution cyberattack detection [15]. Research based on SWaT has explored unsupervised approaches (Isolation Forests, One-Class SVMs, VAEs) trained on normal data only. A common observation: models trained on a single SWaT run achieve strong performance on related test data but higher false-positive rates on separate datasets — motivating the dual-dataset design in this work. Supervised methods (gradient-boosted trees, CNNs) achieve strong performance on abrupt attacks but reduced performance on gradual attacks like slow-ramp FDI; LSTM-based models show promise for these cases.

## 3.5 Evaluation Metrics for Temporal Anomaly Detection

Kim et al. (2022) showed sample-level metrics (accuracy, precision, recall, F1) don't fully capture temporal anomaly detection performance [16], proposing **Time-series Aware Precision and Recall (TaPR)**, which evaluates detections at the attack-event level rather than per-timestep, penalising partial detections and scattered false positives. This is important for attacks like slow-ramp and membrane damage that may remain active for minutes before clear effects appear.

---

# Chapter 4: Methodology

## 4.1 System Overview

The digital twin consists of three software components replicating sensing, control, and actuation layers (Figure 4.1): a **MATLAB physics engine** (ODE-based process dynamics), a **CODESYS PLC runtime** (IEC 61131-3 Structured Text), and a **Python orchestration bridge** (Modbus TCP synchronisation + labelled CSV logging). All operate at a fixed **100 ms cycle**.

The twin mirrors the physical iTrust SWaT two-level network hierarchy: CODESYS as the PLC layer executing control logic and setting actuator coils; the Python bridge as the SCADA historian layer polling registers, forwarding to the physics engine, and maintaining the master dataset log. This architectural fidelity ensures compatibility with the published iTrust SWaT dataset schema (same Modbus register addresses, coil numbering, sensor naming).

**Register ownership**: Sensor holding registers (0–51) written only by the bridge; actuator coils (0–27) written only by CODESYS. An earlier prototype violated this, causing all valve registers to read as zero, invalidating valve-state features in the generated dataset.

*[Figure 4.1: High-level architecture diagram of the SWaT digital twin — MATLAB Physics Engine ↔ CODESYS PLC Runtime ↔ Python Bridge ↔ WebSocket Dashboard, with Control Logic (ST) and Labelled CSV Dataset outputs]*

## 4.2 Plant Physics Model

The MATLAB physics engine listens on a TCP connection and computes full plant state at each $\Delta t = 0.1$ s timestep, receiving an actuator-state vector and returning a sensor-register vector for all six stages, governed by ODEs.

### 4.2.1 Stage 1 – Raw Water Intake: Tank Mass Balance

$$\frac{dV}{dt} = Q_{in}(t) - Q_{out}(t) \quad (4.1)$$

Discrete-time form:

$$V(k+1) = V(k) + \Delta t \cdot \big(Q_{in}(k) - Q_{out}(k)\big) \quad (4.2)$$

with $V(k)$ clamped to [0, 1000] L. Inlet flow:

$$Q_{in}(k) = \text{MV\_101}(k) \cdot \frac{5 + \varepsilon_Q(k)}{3600} \times 1000 \; \text{L/s}, \quad \varepsilon_Q \sim \mathcal{N}(0, \sigma_Q^2) \quad (4.3)$$

$\sigma_Q$ corresponds to a flow measurement uncertainty of ±0.2 m³/h. LIT_101 oscillates within [449, 851] L with ~67 s cycle period, ~117 L standard deviation — this oscillation is the dominant variance source in Stage 1 features and must be characterised to minimise false positives.

### 4.2.2 Stage 2 – Chemical Dosing: pH Buffer Kinetics

$$\frac{d(\text{pH})}{dt} = -\frac{\text{pH}(t) - \text{pH}_{target}}{\tau_{pH}} + \varepsilon_{pH}(t) \quad (4.4)$$

$$\text{pH}(t) = \text{pH}_{target} + (\text{pH}_0 - \text{pH}_{target})e^{-t/\tau_{pH}} \quad (4.5)$$

$\tau_{pH} = 40$ s, $\sigma_{pH} = 0.01$ pH units. Target: 6.80 (P_203 active) or 8.50 (inactive) — implements hysteresis-band pH control.

Chlorine residual: linear increase at 0.3 mg/L/s (up to 8.0 mg/L max) when P_205 active; decreases at 0.1 mg/L/s (down to 1.5 mg/L min) when inactive. Chemical tank refilling uses an SR-latch: starts at 15% level, stops at 80–85% (chemical-dependent), increasing 2% per timestep during refill.

### 4.2.3 Stage 3 – Ultrafiltration: Membrane Fouling

$$\frac{dF}{dt} = \alpha \cdot \left(1 + \frac{\text{AIT\_201}}{1000}\right) \cdot \Delta t, \quad \alpha = 0.001\,\text{s}^{-1} \quad (4.6)$$

$$\text{DPIT\_301}(k) = 25 + F(k) \times 100 \; \text{kPa} \quad (4.7)$$

Backwash starts when DPIT_301 > 60 kPa or after 30 minutes elapsed. During backwash, $F$ decreases by $0.1\Delta t$ per timestep. Normal TMP cycle: 28–32 minutes.

### 4.2.4 Stage 5 – Reverse Osmosis: Pressure and Fouling

$$\text{PIT\_501}(k) = 120 + F_{RO}(k) \times 80 + 5 \cdot \mathbb{1}[\text{LIT\_401} > 600] - 5 \cdot \mathbb{1}[\text{LIT\_401} < 400] \; \text{bar} \quad (4.8)$$

$F_{RO}$ accumulates at $5 \times 10^{-4}$ per step. CIP cycle triggered when $F_{RO} > 0.80$ or after 1000 steps.

### 4.2.5 Sensor Noise Model

$$x_{meas}(k) = x_{true}(k) + \varepsilon(k), \quad \varepsilon(k) \sim \mathcal{N}(0, \sigma_s^2) \quad (4.9)$$

Per-sensor std devs: $\sigma_{AIT\_202} = 0.04$ pH, $\sigma_{LIT\_101} = 6$ L, $\sigma_{PIT\_501} = 3.0$ bar, $\sigma_{DPIT\_301} = 1.0$ kPa, $\sigma_{FIT\_101} = 0.2\,\text{m}^3/\text{h}$.

## 4.3 PLC Control Logic and Cause-Effect Map

The CODESYS PLC executes IEC 61131-3 Structured Text at its native scan rate, implementing hysteresis-band controllers and hard-trip interlocks for safety-critical conditions (Table 4.1, Figure 4.2).

The pH controller: acid dosing activates at pH > 7.5 (AIT_202 > 750), deactivates at pH < 6.8 (AIT_202 < 680). This band creates an interval during which slow-ramp attacks can gradually alter pH without a hysteresis state change. The pH safety interlock stops all major pumps when pH exits [5.5, 9.0] — causing a plant-wide service interruption. The pH manipulation attack avoids this by modifying the AIT_202 register before the interlock evaluation step, exploiting PLC scan-cycle delay.

### Table 4.1: Condensed cause-effect map of the Stage 1 and Stage 2 PLC control logic

| Condition | Effect | Stage |
|---|---|---|
| LIT_101 < 450 | MV_101 := 1 (open) | S1 |
| LIT_101 > 850 | MV_101 := 0 (close) | S1 |
| LIT_101 > 200 ∧ LIT_301 < 800 | P_101 := 1 | S1 |
| LIT_101 > 600 ∧ P_101 | P_102 := 1 | S1 |
| LIT_101 < 50 | P_101 := 0, P_102 := 0 | S1 |
| AIT_202 > 750 | P_203 := 1 (acid on) | S2 |
| AIT_202 < 680 | P_203 := 0 (acid off) | S2 |
| Cl_Res < 20 | P_205 := 1 (chlorine on) | S2 |
| Cl_Res > 50 | P_205 := 0 (chlorine off) | S2 |
| AIT_202 > 900 ∨ AIT_202 < 550 | Trip all major pumps | S2 |
| DPIT_301 > 600 | Trigger UF backwash | S3 |
| RO_Fouling > 80 | Trigger CIP, P_501 := 0 | S5 |
| LIT_101 > 950 | High_Level_Alarm := 1 | Alarm |
| High_Pressure_Alarm ∨ High_Level_Alarm | System_Run := 0 | Alarm |

*[Figure 4.2: Cause-effect logic flow diagram showing Tank Level (LIT_101) and Inflow (FIT_101) → Condition (Low Low / High High) → Cause/Effect → Structured Text code]*

## 4.4 Bridge Synchronisation and Data Logging

The orchestration bridge executes a fixed **five-step cycle every 100 ms** (Figure 4.3):

**Step 1 – Read Actuators**: Modbus FC1 reads pump/valve coil states (addresses 0–27); FC3 reads sensor holding registers (0–51). Motorised valve position registers extracted and retained separately during the write step (an earlier failure to preserve these caused zero open-rate for valve-state features).

**Step 2 – Call Physics Engine**: Actuator state vector serialised and sent to MATLAB via TCP. Read timeout 500 ms; on timeout, most recent sensor values reused.

**Step 3 – Receive Sensors**: Sensor-register vector deserialised; all 52 registers updated (level, flow, pH, chlorine, pressure, TMP, fouling factor, TDS).

**Step 4 – Apply Attack Override**: If an attack is active, sensor values are overridden within the same bridge cycle, between the physics response and CODESYS write — guaranteeing zero label-data misalignment. (An earlier design used a concurrent process at a different rate, causing systematic labelling errors.) Modbus FC16 bulk-writes all 52 holding registers.

**Step 5 – Write Sensors and Log Row**: A CSV row is generated from sensor/actuator dictionaries. A fixed register-to-engineering-unit scaling map is applied once: flow registers ÷10 → m³/h; pH register ÷100; pressure registers ÷10 → bar/kPa; level registers as integer litres; fouling factors as integer percentages. Attack label read from an IPC file (max lag 100 ms). Row appended via buffered writer.

This single-point scaling prevents double-scaling artefacts. A run-duration failsafe ensures logging terminates at configured session length even if the orchestrator's cleanup fails.

*[Figure 4.3: Five-step atomic cycle diagram — Read Actuators → Send to MATLAB → Receive Sensors → Write Sensors → Append to CSV Log, centered around a 100 ms Python Bridge cycle]*

## 4.5 Attack Library and Orchestration

Eight cyber-physical attack scenarios grounded in the underlying plant ODEs (Table 4.2), ensuring injected values remain physically plausible.

### Table 4.2: Attack classes, MITRE identifiers, physical mechanisms, and primary detection signals

| Attack | MITRE ID | Mechanism | Primary Detection Signal |
|---|---|---|---|
| Reconnaissance | T0840 | 20 Hz read-only Modbus scan | Timing jitter and near-zero register variance |
| Replay | T0839 | Freeze actuator coils at onset | Multivariate coil-variance collapse |
| pH Manipulation | T0836 | Overwrite AIT_202 at 25 Hz | AIT_202 rate anomaly; pump duty cycle |
| Slow Ramp | T0836 | Sigmoid drift of AIT_202 over 600 s | Sustained d(pH)/dt over 30-step window |
| Tank Overflow | T0816 | Kill outlet pumps; keep MV_101 open | d(LIT_101)/dt > 0 with pumps off |
| Valve Manipulation | T0849 | Force MV closed; pumps remain active | Pump active, FIT_101 ≈ 0 |
| Membrane Damage | T0836 | Suppress backwash coil | Monotonic DPIT_301 rise |
| Chemical Depletion | T0814 | Force all four dosing pumps active | All tank levels depleting simultaneously |

**pH manipulation**: Overwrites AIT_202 at 25 Hz, following the same first-order exponential trajectory as natural pH response (Eq. 4.5).

**Slow-ramp**: Sigmoid drift profile (Eq. 4.10), $T = 600$ s, giving max drift rate $0.004$ pH units/s (Eq. 4.11) — below both perception and interlock margins throughout the attack.

**Tank overflow**: Disables P_101/P_102, leaving only inlet flow active. With $Q_{out} \approx 0$, tank fills at ~1.4 L/s, reaching 950 L overflow threshold from nominal 449 L in ~360 seconds.

**Membrane damage**: Suppresses backwash coil; fouling accumulates monotonically, reaching 60 kPa TMP in ~575 seconds.

**Chemical depletion**: Forces all four dosing pump coils active; chemical tank levels decrease at 1%/s; Mahalanobis distance spikes immediately due to joint anomalous pump activation.

### 4.5.1 Orchestration Schedule

Three-phase schedule generation guaranteeing complete class coverage:
- **Phase 1**: All network-category attacks in shuffled order.
- **Phase 2**: All temporal and command attacks in shuffled order.
- **Phase 3**: Remaining time budget filled with randomly drawn attack types.

A cooldown period prevents consecutive executions of the same attack. Seeded pseudorandom scheduling ensures reproducibility. At each attack boundary, the orchestrator atomically updates the attack label in the IPC file to prevent incomplete reads by the bridge.

## 4.6 Dataset Structure and Experimental Design

Two continuous data logs collected for ML development/evaluation, each a single uninterrupted session sampled at 10 Hz, approximately **864,000 records** per session (~24 hours simulated operation).

**Dataset 1 – Normal Baseline**: Normal plant operation only. No attacks. Provides baseline behaviour, training source for unsupervised models (no attack labels required), and normalisation statistics/Mahalanobis distance features (prevents attack data influencing scaling).

**Dataset 2 – Attack Dataset**: Normal + attack events; attack samples constitute the majority of records, increasing representation of all eight attack classes. Periods of normal operation interspersed for evaluation context.

### 4.6.1 Dataset Schema

Each CSV log contains **84 columns**:
- 52 sensor registers in engineering units (flow: m³/h; pressure: bar/kPa; levels: litres; pH: dimensionless; fouling: percentages)
- 28 actuator coil states (0 or 1 integers)
- One UTC timestamp (ISO 8601, microsecond resolution)
- Three label fields: `ATTACK_ID` (integer), `ATTACK_NAME` (string), `MITRE_ID` (string)

Scaling map applied once during logging in the bridge to prevent inconsistencies.

### 4.6.2 Data Quality Validation

Four-point validation procedure:
1. **Temporal continuity**: Max inter-sample gap < 10 s (single unbroken session).
2. **Flow scaling**: FIT_101/301/501 within physically plausible engineering-unit ranges.
3. **MV register validity**: MV_101 open fraction > 15% (else valve registers were likely zeroed).
4. **Attack class coverage** (Dataset 2): Non-zero record count for every attack class.

Both datasets passed all four checks. Dataset 1 confirmed expected hysteresis-cycling; Dataset 2 confirmed non-zero counts for all eight classes; no null values in any column.

### 4.6.3 Data Preprocessing

Timestamps parsed to UTC-aware datetimes, sorted ascending. Rows with inter-sample gaps > 2 s flagged but retained (last-good-value substitution preserves continuity). Actuator coils retained as binary integers. Continuous sensors standardised via z-score:

$$\hat{x}_i = \frac{x_i - \mu_i}{\sigma_i} \quad (4.12)$$

$\mu_i, \sigma_i$ estimated exclusively from **Dataset 1** to prevent leakage from attack rows. Labels encoded as integers (0 = Normal; 1–8 = attack types) for multi-class, and binary (0/1) for anomaly detection.

## 4.7 Feature Engineering Strategy

A three-tier physics-driven feature engineering strategy transforms the 84-column dataset into a richer representation (Figure 4.4).

**Tier 1 – Scaled Raw Features**: The 52 sensor registers and 28 actuator coil booleans (80 features) — single-timestep snapshots forming input to single-step classifiers and the base layer for Tier 2.

**Tier 2 – Physics-Derived Features**: Five categories organised into nine feature groups:

*Rate of change*:
$$\dot{x}_i(k) = \frac{x_i(k) - x_i(k-1)}{\Delta t} \quad (4.13)$$
Applied to AIT_202, LIT_101/301/401, DPIT_301, RO fouling. $\dot{\text{AIT\_202}}$ is the most discriminative single feature for slow-ramp and pH manipulation attacks (velocity anomaly, not positional).

*Mass-balance residual*:
$$\Delta Q_1(k) = \text{FIT\_101}(k) - \text{FIT\_201}(k) \quad (4.14)$$
Approximates zero in steady state; valve manipulation/tank overflow produce persistent non-zero residuals.

*Pump-flow consistency indicator*:
$$I_{P101}(k) = \mathbb{1}[\text{P\_101}(k)=1] \wedge \mathbb{1}[\text{FIT\_101}(k) < 0.5\,\text{m}^3/\text{h}] \quad (4.15)$$
Represents a physically impossible condition; triggers within one bridge cycle of a valve manipulation event.

*Dosing pump duty cycle* (rolling window $W$):
$$DP_j(k) = \frac{1}{W}\sum_{i=k-W+1}^{k} P_j(i) \quad (4.16)$$
Computed for P_203, P_205, P_206, P_403 at 10 s and 30 s windows. Normal bisulfate pump duty ≈ 4.3%; during pH manipulation ≈ 71.3%; during chemical depletion, all four pumps near 100%.

*Mahalanobis distance*:
$$d_M(k) = \sqrt{(x(k)-\mu)^\top \Sigma^{-1} (x(k)-\mu)} \quad (4.17)$$
$\mu, \Sigma$ estimated from Dataset 1; regularised with diagonal loading $\epsilon = 10^{-4}$. Particularly effective for replay attacks (near-zero covariance collapse) and chemical depletion (correlated deviations across tank levels).

Nine feature groups in the final implementation:
1. Temporal jitter and inter-sample delays
2. Physical mass-balance differentials and second-order DPIT derivatives
3. PLC control-rule violation flags
4. Six MITRE ATT&CK-aligned binary physics-inconsistency indicators
5. Pump duty cycles at multiple window lengths
6. Per-sensor rates of change
7. Rolling mean, std dev, z-score over 20-step window
8. Lag features at steps {1, 5, 10, 30, 100} for 14 key sensors
9. Multi-sensor rolling std-dev collapse feature for replay detection

After dropping 34 near-zero-variance columns and one noise-dominant signal: **final feature count = 244**.

**Tier 3 – Temporal Sequences**: For the CNN-BiLSTM, input tensors of shape $(N, 150, F)$ using a 150-step sliding window (15 s at 10 Hz). This window length was chosen because the slow-ramp attack requires ~15 s of accumulation before cumulative deviation is statistically distinguishable. Label per window determined by majority vote; windows spanning label transitions discarded.

*[Figure 4.4: Three-tier pipeline diagram — Tier 1 (Scaled Raw Features) → Tier 2 (Physics-Derived Features: Calculated Metrics, Process Relationships, Temporal Patterns, Thermodynamics, Statistical Functions) → Tier 3 (Temporal & Ensemble Features)]*

## 4.8 Ensemble Learning Framework

A two-tier ensemble addressing (a) absence of labelled attack data at deployment, and (b) structural limitation of single-step classifiers on gradual attacks (Figure 4.5).

*[Figure 4.5: Pipeline diagram — Unsupervised Anomaly Detection → Supervised Classification → Cross-Run Validation → SHAP Feature Attribution → Evaluation Metrics]*

### 4.8.1 Unsupervised Anomaly Detection (Layer 1)

Two models trained exclusively on Dataset 1 (normal-only), addressing deployment scenarios with no labelled attack data. Outputs appended as feature columns rather than used as direct votes.

- **Isolation Forest** [17]: 200 random trees. False-positive rate on normal validation data: **5.45%**.
- **Autoencoder**: Symmetric feedforward network (245→128→64→32→64→128→245), MSE loss, trained on normal-only data. Reconstruction error normalised relative to 99th-percentile training error. On held-out attack pool: mean attack reconstruction error (0.157) is **67× higher** than mean normal error (0.002).

### 4.8.2 Supervised Classification (Layer 2)

- **XGBoost** [18]: Single-timestep vectors, dimension 195 (193 continuous features + IF and AE anomaly scores). Binary logistic objective, AUCPR evaluation, 400 trees, max_depth=4, scale_pos_weight from training class ratio. Dataset divided into 100 chronological blocks, stratified-split at block level to prevent temporal leakage.

- **CNN-BiLSTM with Attention** [19]: 150-step sliding windows. Architecture: two causal Conv1D layers (64, 128 filters, kernel 3) with batch norm/dropout; MaxPool1D(2); two bidirectional LSTM layers (128, 64 units); temporal attention module; two-layer dense head with sigmoid output. **510,017 parameters**. Trained with weighted binary cross-entropy, Adam ($lr = 10^{-4}$), early stopping on validation AUC. Block-stratified splitting with 500-step guard bands.

### 4.8.3 Ensemble Fusion

Final predictions via weighted soft-score combination of all four model outputs. Weights selected via Dirichlet-sampled random search over **5,000 configurations**, evaluated across 12 FPR budget levels (0.5%–6.0%). Optimal configuration: IF = 0.007, AE = 0.001, XGB = 0.949, CNN = 0.044, decision threshold = 0.707. The dominant XGBoost weight reflects strong physics-derived feature discriminative power; the smaller CNN-BiLSTM weight nonetheless improves detection of gradually evolving attack classes.

### 4.8.4 Validation Protocol

Dataset 1: normal-only training for unsupervised models (fitting all scalers). Dataset 2: split chronologically 70% train / 15% validation / 15% test. Datasets merged and sorted by timestamp before splitting to reduce run-specific overfitting risk and remove distribution shift at the 24-hour boundary.

### 4.8.5 SHAP Feature Attribution

SHAP values [20] computed for the XGBoost component, ranking feature importance per attack class and evaluating whether physics-derived features outrank raw sensor values.

### 4.8.6 Evaluation Metrics

Sample-level: precision, recall, F1-score per class; macro-averaged F1 as primary metric. Event-level: TaPR (per Kim et al. [16]), penalising partial detection and temporally separated false alarms. False-positive rate on Dataset 1 reported as primary operational safety metric.

## 4.9 Summary of the Research Framework

### Table 4.3: Research framework design decisions and corresponding problem motivations

| Design Decision | Rationale | Problem Addressed |
|---|---|---|
| ODE-based MATLAB physics engine (6 stages) | Reproduces continuous plant dynamics without statistical approximation | Sensor fidelity; physics consistency |
| CODESYS IEC 61131-3 ST control logic | Executes real interlock/hysteresis logic at native scan rate | PLC realism; attack stealth modelling |
| 10 Hz logging; atomic 100 ms bridge cycle | Captures sub-second dynamics; prevents label misalignment | Temporal resolution; label fidelity |
| 8 MITRE ATT&CK-aligned attack types | Covers network, temporal, command-injection categories | Attack diversity; benchmark comparability |
| Dual 24-hour datasets (normal + attack) | Separates training distribution from attack evaluation | Overfitting prevention; leakage-free normalisation |
| In-cycle attack injection | Guarantees zero label-data temporal misalignment | Label fidelity |
| Three-tier, nine-group feature engineering | Encodes mass balance, velocity, duty cycle, lag physics | Discrimination of stealthy process-level attacks |
| Ensemble of IF, AE, XGBoost, CNN-BiLSTM | Covers labelled/unlabelled scenarios; exploits temporal context | Full-spectrum attack detection |
| Dirichlet-searched ensemble weights | Calibrates per-model contribution across FPR budgets | Controlled false-positive rate |
| SHAP attribution analysis | Interpretable, per-class feature importance rankings | Scientific interpretability; hypothesis testing |
| Sample-level and TaPR event-level metrics | Evaluates detection at both timestep and event level | Operationally meaningful evaluation |

---

# Chapter 5: Experimental Setup and Results

## 5.1 Experimental Setup

### 5.1.1 Simulation Environment Configuration

Experiments conducted on a Windows host: **MATLAB R2023b** (physics engine, TCP port 9501), **CODESYS V3.5 SP17** (Structured Text, Modbus TCP port 1502), and the orchestration bridge (atomic 100 ms cycle, 10 Hz logging). No hardware required — CODESYS ran as a software target.

Pre-session verification: LIT_101 cycling range [449, 851] L with ~67 s period; AIT_202 reaching target within 5τ_pH (200 s); DPIT_301 continuously increasing when backwash disabled (matched to Eq. 4.6). Sessions failing these checks discarded and restarted from clean state.

### 5.1.2 Dataset Configuration

### Table 5.1: Summary statistics of the two experimental datasets

| Dataset | Content | Duration (h) | Approx. Rows | Attack Rows (%) |
|---|---|---|---|---|
| Dataset 1 | Normal operation only | 24 | ~864,000 | 0% |
| Dataset 2 | Normal + 8 attack classes | 24 | ~864,000 | >50% |
| **Total** | 8 distinct attack types | 48 | ~1,728,000 | — |

### 5.1.3 Data Quality Validation

Both datasets passed all four checks:
- **Temporal continuity**: max gaps < 1.2 s (threshold 10 s)
- **Flow scaling**: FIT_101 in [0.9, 5.8] m³/h, consistent with theoretical 5.0 m³/h inlet + noise
- **MV register validity**: MV_101 open in ~55–60% of rows
- **Attack class coverage**: non-zero record count for all eight classes; no null values

### 5.1.4 Data Preprocessing

Same as Section 4.6.3: UTC timestamp parsing, sorting, flagging of >2s gaps (retained), z-score normalisation (params from Dataset 1 only), binary coil retention, integer/binary label encoding.

### 5.1.5 Feature Engineering

Rate-of-change via first-order backward difference at 100 ms interval; mass-balance residuals and pump-flow indicators computed directly; duty-cycle features at 10 s/30 s windows; Mahalanobis distance with $\epsilon = 10^{-4}$ diagonal loading. Final feature count: **244** (after dropping 34 near-zero-variance columns + 1 noise-dominant signal). Tier 3 tensors: $(N, 150, F)$ via stride-1 sliding window; label-transition windows discarded.

### 5.1.6 Training, Validation, and Test Splits

Dataset 1: training data for unsupervised models + held-out normal baseline for FPR assessment (no attack data seen by unsupervised models).

Dataset 2: 70% train / 15% validation / 15% test, via 100 chronological blocks stratified-split at block level (prevents temporal leakage).

### 5.1.7 Model Configurations

### Table 5.2: Ensemble model configurations and training data sources

| Model | Input | Configuration | Training Source |
|---|---|---|---|
| Isolation Forest [17] | Tier 1+2 features (244) | 200 trees; anomaly score calibrated to 5.45% FPR | Dataset 1 (normal only) |
| Autoencoder | Tier 1+2 features, normalised | 245→128→64→32→64→128→245; MSE loss | Dataset 1 (normal only) |
| XGBoost [18] | 195-dim vector (Tier 1+2 + IF/AE scores) | 400 trees; max depth 4; scale_pos_weight; AUCPR objective | Dataset 2 training split |
| CNN-BiLSTM [19] | Tier 3 tensor (N, 150, F) | 2×Conv1D (64,128); 2×BiLSTM (128,64); attention; 510,017 params; Adam lr=1e-4; early stopping | Dataset 2 training split |

Class imbalance addressed via block-stratified sampling, `scale_pos_weight` in XGBoost, and weighted binary cross-entropy in CNN-BiLSTM.

### 5.1.8 Evaluation Metrics

Per-class precision/recall/F1 on held-out test subset; macro-averaged F1 as primary metric; AUC-ROC as threshold-independent measure; FPR on Dataset 1 as primary safety metric; event-level TaPR per Kim et al. [16]; 1-second detection tolerance at label transition boundaries.

## 5.2 Results and Analysis

### 5.2.1 Normal Operating Dynamics

Dataset 1 reveals characteristic oscillatory behaviour:
- LIT_101: cycles 449–851 L, period 67±3 s, std dev ~117 L
- AIT_202: oscillates [6.80, 7.50], std dev ~0.15 pH units
- DPIT_301: varies 25–58 kPa, cycle period 28–32 minutes (consistent with 575 s theoretical fouling time)

These oscillations are a major false-positive source: temporary flow variations resemble valve manipulation signatures; brief pH deviations near hysteresis boundaries resemble early slow-ramp attack stages — supporting the use of the 150-step LSTM window.

### 5.2.2 Observed Attack Signatures in Dataset 2

- **Reconnaissance (T0840)**: No physical values modified; detected via Mahalanobis distance capturing statistical freeze of all 244 features during the 20 Hz read-only scan.
- **Replay (T0839)**: Coils freeze at onset; within 5–10 s, growing mass-balance residual + cross-sensor coil variance collapse to near zero provide a strong joint signal.
- **pH Manipulation (T0836)**: $\dot{\text{AIT\_202}}$ exceeds normal range within 2–3 s; bisulfate pump duty cycle rises from ~4.3% to ~71.3%; pH safety interlock trips, producing plant-wide pump shutdown.
- **Slow Ramp (T0836)**: Max drift 0.004 pH units/s within normal noise band at any single timestep — invisible to single-step detection. Cumulative drift becomes statistically significant at ~45th second of attack.
- **Tank Overflow (T0816)**: $I_{P101}$ fires within 100 ms; LIT_101 rises at ~1.4 L/s, reaching 950 L in ~360 s.
- **Valve Manipulation (T0849)**: $I_{P101} = 1$ within 100 ms — most rapidly detectable attack at feature level.
- **Membrane Damage (T0836)**: DPIT_301 rises monotonically 35→60 kPa over ~575 s with no abrupt coil-state change — difficult for single-step classifiers.
- **Chemical Depletion (T0814)**: All four dosing pumps activate simultaneously; duty-cycle features reach 100% within first 10-second window; Mahalanobis distance spikes immediately.

### 5.2.3 Model-Wise Binary Detection Performance

### Table 5.3: Model-wise binary detection performance on the held-out test set

| Model | F1 | AUC-ROC |
|---|---|---|
| Isolation Forest (Layer 1a) | 0.401 | 0.584 |
| Autoencoder (Layer 1b) | 0.751 | 0.961 |
| XGBoost (Layer 2) | 0.965 | 0.985 |
| CNN-BiLSTM (Layer 3) | 0.965 | 0.949 |
| **Ensemble** | **0.878** | **0.984** |

*[Figure 5.1: ROC curves — All Layers. IF (0.5844), AE (0.9610), XGBoost (0.9845), CNN-BiLSTM (0.9485), Ensemble (0.9840)]*

The Isolation Forest acts as a feature contributor rather than a classifier — its ROC curve stays close to $y=x$ (AUC 0.584). XGBoost and CNN-BiLSTM ROC curves stay near the upper-left corner across the FPR range.

*[Figure 5.2: F1-Score Across Pipeline Layers bar chart — IF 0.401, AE 0.751, XGBoost 0.621 (shown differently in figure caption vs table — figure shows different intermediate bar labeled "XGBoost" at 0.621, CNN at 0.965, Ensemble at 0.878, with Target=0.88 dashed line]*

### 5.2.4 Ensemble Binary Classification Performance

### Table 5.4: Ensemble binary classification report on the held-out test set (263,040 windows)

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| Normal | 0.87 | 0.96 | 0.91 | 144,672 |
| Attack | 0.94 | 0.83 | 0.88 | 118,368 |
| Macro avg | 0.90 | 0.89 | 0.89 | 263,040 |
| Weighted avg | 0.90 | 0.90 | 0.90 | 263,040 |

**AUC-ROC: 0.984 | FPR: 4.48% | FNR: 17.50%**

### 5.2.5 Per-Attack-Type Performance

### Table 5.5: Per-attack-type ensemble performance on the held-out test set

| Attack Class | Recall | Precision | F1 |
|---|---|---|---|
| Tank Overflow | 0.986 | 0.640 | 0.776 |
| Reconnaissance | 0.988 | 0.520 | 0.681 |
| pH Manipulation | 0.962 | 0.638 | 0.767 |
| Membrane Damage | 1.000 | 0.709 | 0.829 |
| DoS Flood | 1.000 | 0.762 | 0.865 |
| Valve Manipulation | 0.756 | 0.602 | 0.670 |
| Chemical Depletion | 0.559 | 0.599 | 0.579 |
| Slow Ramp | 0.596 | 0.630 | 0.612 |
| Replay | 0.541 | 0.275 | 0.364 |

*All recall values ≥ 0.50: no critical misses detected.*

*[Figure 5.3: Ensemble Confusion Matrix — Normal/Normal: 138,187; Normal/Attack: 6,485; Attack/Normal: 20,712; Attack/Attack: 97,656]*

Of 118,368 attack windows, 97,656 (82.5%) correctly detected. Of 144,672 normal windows, 138,187 (95.5%) correctly classified, 6,485 (4.5%) false alarms. False-negative count (20,712) concentrated in Slow Ramp, Replay, and Chemical Depletion classes.

### 5.2.6 Discussion of Per-Class Results

**High-Recall Classes**: Membrane Damage and DoS Flood achieve perfect recall (1.000); Tank Overflow 0.986. Physics-derived features (pump-flow consistency, mass-balance residual) drive this. Reconnaissance achieves 0.988 recall despite no physical register modification, via Mahalanobis distance capturing the statistical freeze during the 20 Hz scan. Precision is lower (Tank Overflow 0.640, Reconnaissance 0.520) due to onset/offset transition ambiguity relative to the window-majority threshold.

**pH Manipulation and Chemical Depletion**: pH Manipulation recall 0.962, F1 0.767, precision 0.638 (reduced during onset when exponential divergence isn't yet distinguishable from hysteresis transitions). Chemical Depletion recall 0.559 — despite a distinctive duty-cycle signature, the FPR-calibrated threshold suppresses some shorter attack windows near onset.

**Challenging Classes: Slow Ramp and Replay**: Slow Ramp recall 0.596, F1 0.612 — reflects a physical detection boundary. Drift 0.004 pH units/s within normal noise floor at any single timestep; even with a 15 s LSTM window, cumulative drift exceeds the 95th percentile of normal windowed change only at ~45th second. Replay recall 0.541, F1 0.364 — the Group 9 variance-collapse feature is most visible at window level (BiLSTM), but the ensemble assigns minimal CNN weight (0.044) and near-zero AE weight (0.001), concentrating signal in timestep-level XGBoost; low precision (0.275) indicates the FPR-calibrated threshold is too permissive for this class.

### 5.2.7 Ensemble Weight Analysis

Dirichlet search across 5,000 configurations and 12 FPR budgets: XGBoost dominates (weight ≥ 0.60) across configurations achieving F1 > 0.74; at optimum, XGBoost weight = 0.949, reflecting the effectiveness of physics-derived features. CNN-BiLSTM contributes 0.044 — small but non-trivial, primarily improving recall for Slow Ramp and Membrane Damage. Isolation Forest and Autoencoder receive weights below 0.010 at the optimum, since their anomaly scores are already captured as XGBoost input features.

### 5.2.8 SHAP Feature Attribution

*[Figure 5.4: SHAP — Top 20 Features. LIT_401_rs (top), AE_recon_error, FIT_201_rm, p403_duty_30s, FIT_101_rs100, FIT_101_rs, FIT_201_rs, p203_duty_60s, IF_score, AIT_202, AIT_202_rs100, p403_duty_10s, RO_Last_Cleaning, Chlorine_Tank_Level_L100, UF_Last_Backwash_L100, PIT_501, AIT_202_rm, Chlorine_Tank_Level_L30, DPIT_301_L30, Chlorine_Tank_Level_L10]*

`LIT_401_rs` (rolling std dev of Stage 4 level) is most influential. Autoencoder reconstruction error ranks second. `FIT_201_rm` (rolling mean, Stage 2 flow) ranks next; `p403_duty_30s` (bisulfate pump 30 s duty cycle) also highly ranked. Isolation Forest anomaly score ranks eighth. Physics-based Tier 2 features rank above most raw sensor values, supporting the hypothesis that feature engineering adds domain information beyond raw registers. The two hardest classes (Slow Ramp, Membrane Damage) are characterised by velocity/duty-cycle anomalies rather than positional anomalies.

### 5.2.9 False-Positive Rate Analysis

Ensemble achieves **4.48%** FPR on normal test windows, driven by:
1. Transient sensor excursions during UF backwash and RO clean-in-place cycles.
2. Brief transitions at hysteresis-cycle boundaries (LIT_101, AIT_202) causing rate-of-change features to momentarily approach attack-signature ranges.

Unsupervised components individually exhibit higher FPR (cannot condition on joint sensor-coil state); integrating them as feature inputs rather than voters reduces false alarms overall.

### 5.2.10 Robustness and Limitations

Six of nine attack classes achieve recall above 0.75. XGBoost and CNN-BiLSTM both reliably detect sudden/multi-sensor attacks, offering two independent detection mechanisms. The CNN-BiLSTM is important for gradual-evolution attacks, whose performance is limited by process variable rate of change.

**Three limitations**:
1. Recall of Slow Ramp/Replay bounded by the 15 s observation window; longer windows could improve recall but increase latency/computational cost.
2. 4.48% FPR observed during scheduled maintenance (backwash, CIP) — could be reduced via a maintenance-schedule flag feature.
3. Simulation doesn't model Modbus framing errors or network packet jitter — real plant data performance may differ.

## 5.3 Summary of Findings

### Table 5.6: Mapping of research hypotheses to experimental outcomes

| Hypothesis | Experimental Evidence | Outcome |
|---|---|---|
| Ensemble combining unsupervised and supervised models outperforms any single model on the full attack portfolio | Ensemble AUC = 0.984; all nine classes detected at recall ≥ 0.54; no single component achieves this | Supported |
| Physics-derived features rank above raw sensor values for process-level attack detection | SHAP: Tier 2 duty-cycle, rolling-statistics, mass-balance features rank above raw sensor registers | Supported |
| Slow Ramp is undetectable by any single-step classifier | $\dot{\text{AIT\_202}} = 0.004$ pH/s within normal noise band; single-step IF F1 = 0.401; LSTM first detects at ≈45 s | Supported |
| In-cycle attack injection guarantees label fidelity | Zero label-data temporal misalignment confirmed by construction; max lag 100 ms at transition boundaries | Supported by design |
| 10 Hz sampling captures sub-second attack signatures | Valve Manipulation detected within 100 ms; Tank Overflow fully characterised at 1.4 L/s fill rate | Supported |

**Primary finding**: Physics-driven feature engineering is the dominant contributor to detection performance. XGBoost alone (on 244 physics-derived features) achieves F1 = 0.9941 and AUC = 0.9998 on validation, confirming feature engineering — not model architecture — is the primary source of discriminative power. CNN-BiLSTM provides complementary temporal information, especially for Membrane Damage and Slow Ramp. The two-tier ensemble combines both strengths, maintaining a 4.48% FPR on normal data.

---

# Chapter 6: Conclusion and Future Work

## 6.1 Summary of Contributions

This dissertation presents the design, implementation, and evaluation of a software digital twin of the six-stage SWaT plant for ICS cybersecurity research, generating a physics-consistent, reproducible dataset with labelled attack scenarios and an ensemble learning framework.

The digital twin comprises:
1. **MATLAB physics engine** — ODEs for mass balance, pH buffer kinetics, Darcy's-Law-based membrane fouling, RO pressure dynamics
2. **CODESYS PLC** — IEC 61131-3 Structured Text with hysteresis controllers and safety interlocks
3. **Modbus TCP bridge** — 100 ms synchronisation cycle with in-cycle attack injection, eliminating label-data temporal misalignment

The system produces data at **10 Hz** — 10× the original iTrust SWaT dataset — all in engineering units, with **84 columns** including per-row ground-truth labels. Eight cyber-physical attack scenarios (MITRE ATT&CK-mapped) span network attacks (Reconnaissance, Replay), process manipulation attacks (pH Manipulation, Slow Ramp, Membrane Damage, Chemical Depletion), and command injection attacks (Tank Overflow, Valve Manipulation). A phase-based orchestration engine ensures every dataset contains samples from all classes.

Two 24-hour logs were collected; both passed temporal continuity, flow-scaling, MV register-validity, and attack-class coverage validation. Dataset 1 characterised natural hysteresis-cycling baselines; Dataset 2 confirmed physically consistent attack signatures aligned with theoretical predictions.

A three-tier physics-driven feature engineering strategy was developed: scaled raw features, physics-derived features (rate of change, mass-balance residual, pump-flow consistency, duty cycle, Mahalanobis distance), and temporal sequence tensors for LSTM input. The ensemble learning framework combines an unsupervised tier (Isolation Forest, Autoencoder — trained on Dataset 1 only) and a supervised tier (XGBoost, bidirectional LSTM — trained on stratified Dataset 2), with final predictions from soft-voting.

*Note: Section 6.1 reports somewhat different summary figures (overall AUC 0.94, Replay F1=0.99, Tank Overflow F1=0.98, Reconnaissance F1=0.97, Slow Ramp F1=0.81, FPR 2.1%) than the detailed per-class results in Chapter 5 — reproduced here as stated in the original text.*

The framework achieved an overall AUC of 0.94 on the held-out test subset, with six of eight attack classes achieving F1-scores above 0.91. Replay (F1=0.99), Tank Overflow (F1=0.98), and Reconnaissance (F1=0.97) achieved the strongest per-class performance. Slow Ramp was the hardest class to detect (F1=0.81), reflecting the difficulty of detecting smooth process changes within a limited observation window. Dataset 1's normal data yielded a false-positive rate of 2.1%.

The significance of this work lies in integrating physics-based simulation, realistic MITRE-aligned attack scenarios, and an ensemble detection framework, evaluated across two independent datasets to reduce run-specific overfitting risk. The entire pipeline is reproducible with open-source software, requiring no physical plant infrastructure, supporting independent replication and benchmarking.

## 6.2 Future Work

- **Multi-Class Attack Classification**: Extend from binary to full nine-class classification (Normal + 8 attack types) using existing `ATTACK_ID` labels, revealing inter-class confusion patterns (e.g., pH Manipulation vs. Slow Ramp).

- **Online and Streaming Anomaly Detection**: Adapt the batch pipeline to streaming detection with bounded latency — incremental z-score normalisation, streaming window construction, fixed per-cycle inference budget, and detection-latency evaluation under real-time constraints.

- **Adaptive and Continual Learning**: Address operating-condition drift (sensor calibration, membrane ageing, seasonal demand) via continual learning that updates models incrementally without catastrophic forgetting.

- **Physics-Informed Hybrid Anomaly Detection**: Express PLC cause-effect invariants as differentiable constraints integrated into the LSTM training objective; integrate causal structure learning with the known plant topology.

- **Graph Neural Networks for Multi-Stage Attack Detection**: Model the plant as a directed graph (instruments as nodes, flow paths as edges) using Temporal Graph Convolutional Networks to detect multi-stage coordinated attacks spanning inter-stage dependencies.

- **Transformer-Based Sequence Models**: Use multi-head self-attention to capture non-contiguous temporal dependencies beyond the fixed 30-step LSTM window (e.g., duty-cycle anomalies 200 s before a pH deviation).

- **Deployment on Edge and Embedded ICS Hardware**: Quantise/compile XGBoost and LSTM components for embedded edge platforms; benchmark inference latency, memory footprint, and detection performance under PLC scan-rate constraints.

- **Federated Learning for Distributed Industrial Systems**: Train local detection models at each distributed PLC/SCADA node, sharing only model updates for collaborative anomaly detection without raw data transfer.

- **Evaluation on Larger and More Diverse ICS Datasets**: Assess generalisability on power distribution, gas pipeline, and batch chemical process datasets (e.g., BATADAL, HAI benchmarks).

- **Explainable AI for Industrial Anomaly Analysis**: Extend interpretability to the LSTM component via attention visualisation or integrated gradients, identifying which timesteps contributed most to a detection decision — a prerequisite for regulatory acceptance.

- **Dataset Expansion and Community Release**: Publicly release the digital twin and datasets, enabling replication and extension to new attack scenarios (firmware modification, MITM interception, multi-stage lateral movement), plus operator error/sensor degradation/process upset scenarios as a community benchmark.

---

# Bibliography

[1] Noshina Tariq, Muhammad Asim, and Farrukh Aslam Khan. "Securing SCADA-Based Critical Infrastructures: Challenges and Open Issues". In: *2023 International Conference on Communication, Computing and Digital Systems (C-CODE)*. IEEE, 2023, pp. 1–8.

[2] Matteo Laiani, Alessandro Tugnoli, and Valerio Cozzani. "Critical Cybersecurity Scenarios in Drinking Water Treatment Plants". In: *2023 International Conference on Cyber-Physical Social Intelligence (ICCPSI)*. IEEE, 2023, pp. 1–6.

[3] Jonathan Goh et al. "A Dataset to Support Research in the Design of Secure Water Treatment Systems". In: *Proceedings of the 11th International Conference on Critical Information Infrastructures Security (CRITIS)*. iTrust, Centre for Research in Cyber Security, Singapore University of Technology and Design. Paris, France: Springer, 2016, pp. 88–99.

[4] Manar Alanazi, Abdun Mahmood, and Mohammad Jabed Morshed Chowdhury. "SCADA Vulnerabilities and Attacks: A Review of the State-of-the-Art and Open Issues". In: *Proceedings of the 2023 Australasian Computer Science Week Multiconference (ACSW)*. ACM, 2023, pp. 1–10.

[5] Nicola d'Ambrosio et al. "SCASS: Breaking into SCADA Systems Security". In: *2023 IEEE International Conference on Smart Computing (SMARTCOMP)*. IEEE, 2023, pp. 306–311.

[6] C. M. Davis et al. "SCADA Cyber Security Testbed Development". In: *2023 IEEE 47th Annual Computers, Software, and Applications Conference (COMPSAC)*. IEEE, 2023, pp. 1313–1318.

[7] Marcio Andrey Teixeira et al. "SCADA System Testbed for Cybersecurity Research Using Machine Learning Approach". In: *2023 IEEE Globecom Workshops (GC Wkshps)*. IEEE, 2023, pp. 1095–1100.

[8] Ala Mughaid et al. "Simulation-Based Framework for Authenticating SCADA Systems and Cyber Threat Security in Edge-Based Autonomous Environments". In: *2023 IEEE 13th Annual Computing and Communication Workshop and Conference (CCWC)*. IEEE, 2023, pp. 252–258.

[9] Joseph T. Meier, Thuy D. Nguyen, and Neil C. Rowe. "Hardening Honeypots for Industrial Control Systems". In: *2023 IEEE Conference on Communications and Network Security (CNS)*. IEEE, 2023, pp. 372–380.

[10] Alexandru Vlad Serbanescu, Sebastian Obermeier, and Der-Yeuan Yu. "A Flexible Architecture for Industrial Control System Honeypots". In: *2023 IEEE 1st International Conference on Advanced Networking and Communication (ADNETCOM)*. IEEE, 2023, pp. 1–7.

[11] Van Long Do, Lionel Fillatre, and Igor Nikiforov. "Sequential Monitoring of SCADA Systems Against Cyber/Physical Attacks". In: *2023 62nd IEEE Conference on Decision and Control (CDC)*. IEEE, 2023, pp. 7523–7528.

[12] Faegheh Moazeni and Javad Khazaei. "Sequential False Data Injection Cyberattacks in Water Distribution Systems Targeting Storage Tanks: A Bi-Level Optimization Model". In: *Journal of Water Resources Planning and Management* 149.5 (2023), p. 04023018.

[13] Davide Giannubilo et al. "A Deep Learning Approach for False Data Injection Attacks Detection in Smart Water Infrastructure". In: *Proceedings of the 18th International Conference on Availability, Reliability and Security (ARES)*. ACM, 2023, pp. 1–10.

[14] André Pinto et al. "Survey on Intrusion Detection Systems Based on Machine Learning Techniques for the Protection of Critical Infrastructure". In: *World Conference on Information Systems and Technologies (WorldCIST)*. Springer, 2023, pp. 498–510.

[15] Md Nazmul Kabir Sikder et al. "Deep H2O: Cyber Attacks Detection in Water Distribution Systems Using Deep Learning". In: *2023 IEEE International Conference on Big Data (BigData)*. IEEE, 2023, pp. 6156–6161.

[16] Dong-Hwi Kim et al. "A Study on Performance Metrics for Anomaly Detection Based on Industrial Control System Operation Data". In: *Electronics* 11.1 (2022), p. 148. doi:10.3390/electronics11010148

[17] F. T. Liu, K. M. Ting, and Z.-H. Zhou. "Isolation Forest". In: *Proceedings of the IEEE International Conference on Data Mining (ICDM)*. Dec. 2008, pp. 413–422.

[18] T. Chen and C. Guestrin. "XGBoost: A Scalable Tree Boosting System". In: *Proceedings of the ACM SIGKDD International Conference on Knowledge Discovery and Data Mining (KDD)*. Aug. 2016, pp. 785–794.

[19] S. Hochreiter and J. Schmidhuber. "Long Short-Term Memory". In: *Neural Computation* 9.8 (Nov. 1997), pp. 1735–1780.

[20] S. M. Lundberg and S.-I. Lee. "A Unified Approach to Interpreting Model Predictions". In: *Proceedings of the Neural Information Processing Systems (NeurIPS)*. 2017.

---

# Appendix A: Research Paper

## Cyber-Induced Process Anomalies in Water Treatment Infrastructure: Environmental Consequence Characterisation via a Physics-Grounded Digital Twin

**Dweep Hiten Vira, Sandeep S. Udmale**
Department of Computer Engineering and Information Technology, Veermata Jijabai Technological Institute, Mumbai 400019, India

### Abstract

Cyber attacks on water treatment SCADA systems carry direct environmental and public-health consequences that extend well beyond the informatic domain. The 2021 Oldsmar incident demonstrated that a single unauthorised write command can alter chemical dosing to levels hazardous to approximately 15,000 residents within minutes, yet the process-safety literature lacks a reproducible, high-resolution experimental platform for characterising which attack classes produce environmentally significant deviations and at what temporal scale.

This paper presents a physics-grounded software digital twin of a six-stage water treatment plant, integrating a MATLAB ODE physics engine, a CODESYS IEC 61131-3 PLC, and a Modbus TCP synchronisation bridge operating at 10 Hz. Eight cyber-physical attack scenarios spanning chemical-dosing manipulation, membrane process interference, actuator-state injection, and network-layer reconnaissance are injected across two continuous 24-hour logs totalling approximately 1.73 million rows.

For each scenario, three environmental consequence integrals are derived: a cumulative pH exceedance integral ($I_{pH}$) proxying chemical treatment failure, a dissolved-chemical concentration anomaly integral ($\Phi_{chem}$) proxying acute public-health exposure, and a supply-loss integral ($\Lambda_{supply}$) proxying distribution service disruption. These integrals provide a quantitative bridge between cyber-event severity and regulatory process-safety outcomes.

An ensemble anomaly-detection pipeline characterises the generalisation boundary of current ML detectors: six of eight attack classes are identified at recall exceeding 0.75. Temporally gradual pH manipulation and actuator-replay attacks expose a physical detection limit at the chosen 15-second observation window. The Slow Ramp manipulation (drifting at 0.004 pH s⁻¹) accumulates $I_{pH} > 2.5 \times 10^4$ pH·s before a statistically distinguishable signal emerges — quantifying the environmental cost of detector latency in regulatory units. All platform components are open-source, enabling independent replication and controlled experimentation for cyber-risk assessment of water treatment infrastructure.

**Keywords**: SCADA cybersecurity, water treatment, digital twin, process safety, cyber-physical systems, anomaly detection, environmental risk

### 1. Introduction

Water treatment plays a unique role among critical infrastructure — its outputs (safe water) are consumed directly, making process failures a public health risk requiring immediate attention. pH levels must stay within narrow ranges for disinfection effectiveness and corrosion reduction; chlorine levels must meet minimums to prevent pathogen growth; ultrafiltration pressures must be controlled to prevent particle/microorganism escape. PLCs enforce these limits through Structured Text interlock logic.

The ongoing OT/IT convergence has created new avenues for process disruption. The **February 2021 Oldsmar, Florida** attack illustrates this: a remote hacker increased sodium hydroxide concentration to 111× the safe regulatory limit within five minutes of gaining SCADA access — potentially causing serious chemical harm to ~15,000 residents had an operator not noticed and reversed the command (Iaiani et al., 2022). No zero-day vulnerability was involved; the attack exploited only the semantic gap between valid Modbus commands and physically dangerous process states.

Despite this public-health gravity, process-safety and environmental-risk practice addresses cyber threats largely in isolation from the engineering conditions under which detectors operate. Consequence models (WHO 2017; US EPA 2005) require the temporal magnitude/duration of contamination events as input; security-focussed studies (Tariq et al. 2023; Moazeni and Khazaei 2023) evaluate detection accuracy in informatic units (precision, recall, F1) without connecting missed detections to environmental exposure. This paper addresses that gap through a physics-grounded digital twin of the SWaT process, an environmental consequence framework deriving regulatory-unit integrals from physics trajectories, and an ensemble ML pipeline characterising detector capabilities and failure modes.

### 2. Background

#### 2.1 Environmental and Public-Health Risks in Water Treatment

WHO guidelines (2017) specify a pH operating range of **6.5–9.5** for distribution. Outside these ranges, disinfection by-product chemistry changes, chloramine stability decreases, and pathogens like *Legionella pneumophila* increase in distribution networks (Allen et al., 2004). Acute chemical contamination (e.g., sodium hydroxide over-dosing) can cause mucosal burns at concentrations as low as 500 mg/L, classified as an acute public health event under the US Safe Drinking Water Act (US EPA, 2005).

Iaiani et al. (2022) reviewed cybersecurity scenarios in drinking water treatment, mapping twelve attack pathways to physical consequences, identifying chemical-dosing manipulation as the highest-risk class. Supply-loss events (tank overflow, uncontrolled drainage) can release process chemicals to soil/groundwater and interrupt treated water supply, exposing people to pathogens via untreated water use (Gleick, 2006).

#### 2.2 Cyber-Physical Threats to Water SCADA Systems

Tariq et al. (2023) identify OT/IT convergence and unauthenticated industrial protocols (Modbus) as primary structural weaknesses. Alanazi et al. (2023) catalogue attack vectors at protocol, OS, and HMI layers. Attacks fall into two categories: network-layer events (altering SCADA-to-PLC communication without modifying process variables) and process-layer events (writing directly to sensor registers/actuator coils). Moazeni and Khazaei (2023) model sequential FDI attacks via bi-level optimisation, motivating this study's focus on stealthy, temporally gradual attacks. Do et al. (2023) show sequential monitoring over temporal windows is necessary for such detection. Giannubilo et al. (2023) report empirical evidence that neural network models detect subtle FDI signatures missed by rule-based systems.

#### 2.3 Digital Twin Approaches for Water Process Safety

The iTrust SWaT facility (Goh et al., 2016) cost ~USD 1 million and requires real chemicals/membranes, limiting adversarial manipulation at scale. Software twins allow repeated attack injection with exact ground-truth labels. The SWaT dataset (Goh et al., 2016) covers 11 days at 1 Hz (946,722 samples); detection studies (Goh et al., 2017; Kravchik and Shabtai, 2018) report models overfitting to run-specific characteristics. The present twin's dual-dataset structure is designed to expose and quantify this effect. Existing twins report detection performance in informatic units without linking to environmental consequence — this work couples the physics trajectory to post-hoc environmental consequence computation.

#### 2.4 Research Gap

No existing platform simultaneously provides: (i) physics-consistent multi-stage simulation at sub-second resolution; (ii) a diverse, reproducible attack catalogue with per-row ground-truth labelling; and (iii) a quantitative environmental consequence framework linking cyber-event profiles to process-safety outcomes in regulatory units. This work provides all three.

### 3. System Architecture

#### 3.1 Three-Layer Digital Twin

Three components operating on a deterministic 100 ms cycle: MATLAB physics engine (`swat_physics_server.m`, TCP :9501), Python orchestration bridge (`physics_client.py`, 100 ms cycle), CODESYS PLC runtime (`plant.st`, Modbus TCP :1502), plus an Attack Scheduler and CSV Logger.

Sensor holding registers (0–51) owned exclusively by the bridge; actuator coils (0–27) owned exclusively by CODESYS. An earlier prototype violating this partitioning caused all valve registers to read as zero.

#### 3.2 Plant Physics Model

Same governing equations as the main dissertation (Stage 1 mass balance, Stage 2 pH buffer kinetics, Stage 3 Darcy's Law fouling), reproduced here:

$$\frac{dV}{dt} = Q_{in}(t) - Q_{out}(t) \quad (1)$$

$$\frac{d(\text{pH})}{dt} = -\frac{\text{pH}(t)-\text{pH}_{target}}{\tau_{pH}} + \varepsilon_{pH}(t), \quad \varepsilon_{pH}\sim\mathcal{N}(0,\sigma_{pH}^2) \quad (2)$$

$$\frac{dF}{dt} = \alpha\left(1+\frac{\text{AIT\_201}}{1000}\right)\Delta t, \quad \alpha=0.001\,\text{s}^{-1} \quad (3)$$

Per-sensor noise std devs as before: $\sigma_{AIT\_202}=0.04$ pH, $\sigma_{LIT\_101}=6$ L, $\sigma_{PIT\_501}=3.0$ bar, $\sigma_{DPIT\_301}=1.0$ kPa, $\sigma_{FIT\_101}=0.2\,\text{m}^3/\text{h}$.

#### 3.3 Control Logic and Safety Interlocks

### Table 1: Condensed cause-effect map (PLC control logic, Stages 1 and 2)

| Condition | Effect | Stage |
|---|---|---|
| LIT 101 < 450 | MV 101 := open | S1 |
| LIT 101 > 850 | MV 101 := close | S1 |
| LIT 101 > 200 ∧ LIT 301 < 800 | P 101 := on | S1 |
| LIT 101 > 600 ∧ P 101 | P 102 := on | S1 |
| LIT 101 < 50 | P 101, P 102 := off | S1 |
| AIT 202 > 750 | P 203 := on (acid) | S2 |
| AIT 202 < 680 | P 203 := off | S2 |
| ClRes < 20 | P 205 := on (Cl) | S2 |
| ClRes > 50 | P 205 := off | S2 |
| AIT 202 > 900 ∨ AIT 202 < 550 | Trip pumps | S2 |
| DPIT 301 > 600 | Trigger backwash | S3 |

#### 3.4 Data Collection Protocol

Two 24-hour continuous logs at 10 Hz. Dataset 1 (normal only) provides baseline distribution/reference statistics for normalisation. Dataset 2 (normal + all 8 attack classes) has attack traffic constituting the majority. Combined: ~1.73 million rows, 84 columns (52 sensor registers, 28 coil booleans, timestamp, 3 label fields). Maximum label lag of one bridge cycle (100 ms) at each attack boundary.

### 4. Attack Scenarios and Environmental Consequence Framework

#### 4.1 Attack Catalogue and Environmental Consequence Pathways

### Table 2: Attack scenarios — injection mechanism, primary detection signal, environmental consequence pathway

| Attack Class | Injection Mechanism | Primary Detection Signal | Environmental Consequence Pathway |
|---|---|---|---|
| Reconnaissance | 20 Hz read-only Modbus scan | Timing jitter; near-zero register variance | No immediate physical consequence; enables intelligence for subsequent attack |
| Replay | Freeze actuator coils at onset | Multivariate coil-variance collapse to near zero | Progressive mass-balance violation; tank overflow or drainage |
| pH Manipulation | Overwrite AIT 202 at 25 Hz | AIT 202 rate-of-change anomaly within 2–3 s; pump duty spike 4.3%→71.3% | Acute chemical-dosing exceedance; elevated $I_{pH}$, $\Phi_{chem}$; NaOH/HCl over-dosing risk |
| Slow Ramp | Sigmoid drift of AIT 202 over 600 s at 0.004 pH s⁻¹ | Sustained d(pH)/dt over 30-step window; undetectable at single timestep | Accumulating pH exceedance below interlock threshold; $I_{pH}$ grows without triggering trip |
| Tank Overflow | Disable outlet pumps; keep MV 101 open | Pump-flow consistency flag within 100 ms | Tank overflow; chemical contamination of local environment; $\Lambda_{supply}$ ≈ 1.4 L/s |
| Valve Manipulation | Force MV closed; pumps active | Pump active, FIT 101 ≈ 0; mass-balance residual > 0 | Immediate supply loss; elevated $\Lambda_{supply}$; pump damage risk |
| Membrane Damage | Suppress backwash coil | Monotonic DPIT 301 rise without coil-state change | Progressive filtration failure; particulate/microbial breakthrough risk |
| Chemical Depletion | Force all four dosing pumps active | All tank levels depleting; Mahalanobis spike | Simultaneous chlorine overdosing/pH dysregulation; disinfection by-product risk |

Slow Ramp detectability boundary:

$$s(t) = \frac{1}{1+e^{-(10t/T-5)}}, \quad T=600\,\text{s} \quad (4)$$

$$\left.\frac{ds}{dt}\right|_{max} = \frac{2.5}{T} = 0.004\,\text{pH s}^{-1} \quad (5)$$

#### 4.2 Environmental Consequence Integrals

**pH exceedance integral**:
$$I_{pH}(t_0,t_1) = \int_{t_0}^{t_1} \max\big(0, |\text{pH}(t)-\text{pH}_{nominal}| - \delta_{pH}\big)\,dt \quad (6)$$
where $\text{pH}_{nominal}=7.15$, $\delta_{pH}=0.35$ pH units. Units: pH·s.

**Chemical concentration anomaly integral**:
$$\Phi_{chem}(t_0,t_1) = \int_{t_0}^{t_1} \big(|\Delta\hat{C}_{cl}(t)| + |\Delta\hat{C}_{pH}(t)|\big)\,dt \quad (7)$$
Dimensionless, normalised to WHO guideline values.

**Supply-loss integral**:
$$\Lambda_{supply}(t_0,t_1) = \int_{t_0}^{t_1} \max\big(0, Q_{nominal}-Q_{out}(t)\big)\,dt \quad (8)$$
Units: litres — the volume of safe water not delivered during the attack window.

These integrals are computed post-hoc from physics trajectories, quantifying environmental cost and detection-latency cost when the ensemble fails to identify an attack.

### 5. Anomaly Detection Framework

#### 5.1 Physics-Derived Feature Engineering

A three-tier strategy expands the 84-column dataset to 244 features. Base layer: 52 sensors + 28 coils. Physics-derived layer: rates of change $\dot{x}_i(k) = (x_i(k)-x_i(k-1))/\Delta t$; Stage 1 mass-balance residual $\Delta Q_1(k) = \text{FIT\,101}(k)-\text{FIT\,201}(k)$ (Eq. 9); pump-flow consistency indicator $I_{P101}(k)$ (Eq. 10); dosing duty cycles (10 s/30 s windows); Mahalanobis distance $d_M(k)$ (Eq. 11) with $\epsilon=10^{-4}$ regularisation.

Temporal sequence layer: $(N, 150, F)$ tensors via 150-step (15 s) sliding window — chosen because the Slow Ramp attack requires ~15 s of accumulation before cumulative drift exceeds the 95th percentile of normal hysteresis-band variation. This window length is both an ML design parameter and a **process-safety observable**, setting the minimum detection latency and minimum $I_{pH}$ accumulated before any statistical detector can fire.

#### 5.2 Ensemble Architecture

Two-tier architecture: unsupervised tier (Isolation Forest [Liu et al., 2008]; feedforward Autoencoder 245→128→64→32→64→128→245) trained on Dataset 1 only, feeding normalised anomaly scores into the feature matrix; supervised tier (XGBoost [Chen and Guestrin, 2016] on 244-dim vectors; bidirectional CNN-LSTM with temporal attention [Hochreiter and Schmidhuber, 1997] on 150-step windows). Final predictions combine four soft scores via Dirichlet-sampled weights (5,000 configurations, 12 FPR budgets). Optimal weights: XGBoost 0.949, CNN-LSTM 0.044. Feature normalisation from Dataset 1 only; Dataset 2 split into 100 chronological blocks, stratified at block level.

### 6. Results and Environmental Consequence Analysis

#### 6.1 Dataset Characterisation and Validation

Both datasets passed all four quality checks (inter-sample gap < 1.2 s; FIT 101 in [0.9, 5.8] m³/h; MV 101 open 55–60%; non-zero record counts for all 8 classes, no nulls). LIT 101 cycles 449–851 L (period 67±3 s); AIT 202 oscillates [6.80, 7.50] (std dev 0.15 pH); DPIT 301 cycles 28–32 min (matching 575 s theoretical fouling period).

#### 6.2 Detection Performance

### Table 3: Component-level binary detection performance (263,040 windows)

| Model | F1 | AUC-ROC |
|---|---|---|
| Isolation Forest (unsupervised) | 0.401 | 0.584 |
| Autoencoder (unsupervised) | 0.751 | 0.961 |
| XGBoost (supervised) | 0.965 | 0.985 |
| CNN-BiLSTM (supervised) | 0.965 | 0.949 |
| **Ensemble** | **0.878** | **0.984** |

Ensemble achieves AUC-ROC = 0.984, binary F1 = 0.878, FPR = 4.48% on normal windows. XGBoost alone achieves F1 = 0.9941, indicating the physics-derived feature set — not model architecture — is the primary source of discriminative power. SHAP attribution places four physics-derived features at the top: LIT 401 rolling std dev, Autoencoder reconstruction error, FIT 201 rolling mean, and bisulfate pump duty over 30 s.

### Table 4: Per-attack-type ensemble performance (held-out test set)

| Attack Class | Recall | Precision | F1 |
|---|---|---|---|
| Membrane Damage | 1.000 | 0.709 | 0.829 |
| DoS Flood | 1.000 | 0.762 | 0.865 |
| Reconnaissance | 0.988 | 0.520 | 0.681 |
| Tank Overflow | 0.986 | 0.640 | 0.776 |
| pH Manipulation | 0.962 | 0.638 | 0.767 |
| Valve Manipulation | 0.756 | 0.602 | 0.670 |
| Slow Ramp | 0.596 | 0.630 | 0.612 |
| Chemical Depletion | 0.559 | 0.599 | 0.579 |
| Replay | 0.541 | 0.275 | 0.364 |

The 4.48% FPR on normal windows is concentrated around UF backwash and RO CIP transitions — this can trigger unnecessary process shutdowns which themselves accumulate $\Lambda_{supply}$.

#### 6.3 Environmental Cost of Detection Failure Modes

### Table 5: Environmental consequence characterisation

| Attack Class | Dominant Consequence | Integral on Miss | Latency Cost | Recall |
|---|---|---|---|---|
| pH Manipulation | $I_{pH}$ (acute chemical exceedance) | ~1.4×10⁴ pH·s | ~1.2×10¹ pH·s | 0.962 |
| Slow Ramp | $I_{pH}$ (sub-threshold accumulation) | ~2.5×10⁴ pH·s | ~2.6×10³ pH·s (at 45 s) | 0.596 |
| Chemical Depletion | $\Phi_{chem}$ (disinfection by-product risk) | High (all dosing pumps) | Low (rapid Mahalanobis spike) | 0.559 |
| Tank Overflow | $\Lambda_{supply}$ (overflow + soil contamination) | ~3.0×10⁴ L | <10 L (100 ms detection) | 0.986 |
| Valve Manipulation | $\Lambda_{supply}$ (immediate supply loss) | ~1.5×10⁴ L | <10 L (100 ms detection) | 0.756 |
| Membrane Damage | Filtration breakthrough (particulate/microbial) | Elevated (TMP→60 kPa) | Negligible (perfect recall) | 1.000 |
| Replay | Variable (depends on frozen state) | Variable | Variable | 0.541 |
| Reconnaissance | None (intelligence only) | None | None | 0.988 |

The **Slow Ramp attack produces the largest environmental consequence** among all failure modes: at recall 0.596, ~40% of Slow Ramp windows go undetected, each accumulating $I_{pH} \approx 2.5\times10^4$ pH·s over the 30-minute attack duration. Even in detected windows, the 45-second minimum latency yields $I_{pH} \approx 2.6\times10^3$ pH·s before the ensemble fires. This is analogous to slow equipment degradation in process-safety literature, where threshold-based monitoring is insufficient and model-based residual monitoring over extended windows is required (Frank, 1990).

The pH Manipulation attack (detected at recall 0.962, 2–3 s time-to-detection) limits $I_{pH}$ in detected windows to ~1.2×10¹ pH·s — a two-order-of-magnitude gap versus Slow Ramp's undetected exposure, demonstrating the environmental benefit of longer temporal observation windows.

### 7. Discussion

Results characterise a non-uniform threat landscape from an environmental-consequence perspective. Attacks with abrupt, multi-sensor joint signatures (Tank Overflow, pH Manipulation, Chemical Depletion, Membrane Damage) are detected at high recall with short latency, limiting consequences to a small fraction of missed windows. Attacks with temporally gradual/covert signatures (Slow Ramp, Replay) are difficult to detect due to physical process behaviour rather than ML architecture limitations — no detector at a 15-second observation window can identify a 0.004 pH s⁻¹ drift before it accumulates into a statistically distinguishable signal. Increasing the observation window improves recall but increases detection latency and inference overhead — a process-safety design trade-off that the environmental consequence integrals help quantify.

The digital twin contributes to process-safety practice by: (1) producing sub-second process dynamics under adversarial conditions that physical testbeds cannot generate; and (2) coupling physics trajectories to environmental consequence integrals expressed in the same units as regulatory risk thresholds, supporting risk-informed allocation of monitoring resources.

The 4.48% false-positive rate concentrated around UF backwash/RO CIP transitions has two practical effects: unnecessary protective trips increase $\Lambda_{supply}$, and repeated false alarms reduce operator trust in automated detection — motivating context-aware detection logic that accounts for scheduled maintenance events.

This study is scoped to the SWaT six-stage architecture; distribution networks, desalination plants, and multi-site configurations involve different physics, thresholds, and attack vectors, requiring recharacterisation of feature engineering and ensemble weights. The simulation does not model Modbus framing errors or network packet jitter — relevant limitations for Reconnaissance and Replay, whose signatures depend on network-layer timing.

### 8. Conclusion

This paper presented a physics-grounded software digital twin of a six-stage water treatment plant coupled to an environmental consequence framework. Eight cyber-physical attack classes were simulated; missed-detection cost was expressed as $I_{pH}$, $\Phi_{chem}$, and $\Lambda_{supply}$ integrals derived from the physics trajectory. An ensemble detection pipeline demonstrates a non-uniform detection landscape: six of eight classes identified at recall exceeding 0.75; temporally gradual manipulation and replay attacks expose a physical detection limit at the 15-second observation window. The Slow Ramp manipulation accumulates $I_{pH} > 2.5\times10^4$ pH·s in undetected windows, providing a quantitative environmental basis for prioritising extended temporal coverage in process-safety monitoring.

Three future-work directions: extending consequence integrals to distribution-network pathogen risk models; evaluating transformer-based sequence detectors for reduced Slow Ramp detection latency; and adding maintenance-schedule conditioning to reduce false-alarm rates during planned process transitions.

### References (Research Paper)

- Alanazi, M., Mahmood, A., Chowdhury, M.J.M., 2023. SCADA vulnerabilities and attacks: a review of the state-of-the-art and open issues. In: *Proceedings of the 2023 Australasian Computer Science Week Multiconference (ACSW)*. ACM, pp. 1–10.
- Allen, M.J., Edberg, S.C., Reasoner, D.J., 2004. Heterotrophic plate count bacteria—what is their significance in drinking water? *International Journal of Food Microbiology* 92, 265–274. doi:10.1016/j.ijfoodmicro.2003.08.017
- Chen, T., Guestrin, C., 2016. XGBoost: a scalable tree boosting system. In: *Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining*. ACM, pp. 785–794.
- D'Ambrosio, N., Capodagli, G., Perrone, G., Romano, S.P., 2023. SCASS: breaking into SCADA systems security. In: *Proceedings of the 2023 IEEE International Conference on Smart Computing (SMARTCOMP)*. IEEE, pp. 306–311.
- Do, V.L., Fillatre, L., Nikiforov, I., 2023. Sequential monitoring of SCADA systems against cyber/physical attacks. In: *Proceedings of the 62nd IEEE Conference on Decision and Control (CDC)*. IEEE, pp. 7523–7528.
- Frank, P.M., 1990. Fault diagnosis in dynamic systems using analytical and knowledge-based redundancy. *Automatica* 26, 459–474. doi:10.1016/0005-1098(90)90018-D
- Giannubilo, D., Giorgeschi, T., Carminati, M., Zanero, S., Longari, S., 2023. A deep learning approach for false data injection attacks detection in smart water infrastructure. In: *Proceedings of the 18th International Conference on Availability, Reliability and Security (ARES)*. ACM, pp. 1–10.
- Gleick, P.H., 2006. Water and terrorism. *Water Policy* 8, 481–503. doi:10.2166/wp.2006.035
- Goh, J., Adepu, S., Junejo, K.N., Mathur, A., 2016. A dataset to support research in the design of secure water treatment systems. In: *Proceedings of the 11th International Conference on Critical Information Infrastructures Security (CRITIS)*. Springer, pp. 88–99.
- Goh, J., Adepu, S., Tan, M., Lee, Z.S., 2017. Anomaly detection in cyber physical systems using recurrent neural networks. In: *Proceedings of the IEEE International Symposium on High Assurance Systems Engineering (HASE)*. IEEE, pp. 140–145.
- Hochreiter, S., Schmidhuber, J., 1997. Long short-term memory. *Neural Computation* 9, 1735–1780. doi:10.1162/neco.1997.9.8.1735
- Iaiani, M., Tugnoli, A., Cozzani, V., 2022. Outage and asset damage triggered by malicious manipulation of the control system in process plants. *Reliability Engineering & System Safety* 217, 108044. doi:10.1016/j.ress.2021.108044
- Kim, D.-H., Noh, I.-Y., Choi, H.-Y., Kang, B.-H., Lee, Y.-J., 2022. A study on performance metrics for anomaly detection based on industrial control system operation data. *Electronics* 11, 148. doi:10.3390/electronics11010148
- Kravchik, M., Shabtai, A., 2018. Detecting cyber attacks in industrial control systems using convolutional neural networks. In: *Proceedings of the ACM Workshop on Cyber-Physical Systems Security and Privacy (CPS-SPC)*. ACM, pp. 72–83.
- Liu, F.T., Ting, K.M., Zhou, Z.-H., 2008. Isolation forest. In: *Proceedings of the IEEE International Conference on Data Mining (ICDM)*. IEEE, pp. 413–422.
- Lundberg, S.M., Lee, S.-I., 2017. A unified approach to interpreting model predictions. In: *Advances in Neural Information Processing Systems (NeurIPS)*. Vol. 30. Curran Associates, pp. 4765–4774.
- Moazeni, F., Khazaei, J., 2023. Sequential false data injection cyberattacks in water distribution systems targeting storage tanks: a bi-level optimisation model. *Journal of Water Resources Planning and Management* 149, 04023018. doi:10.1061/JWRMD5.WRENG-5752
- Sikder, M.N.K., Nguyen, M.B.T., Elliott, E.D., Batarseh, F.A., 2023. Deep H2O: cyber attacks detection in water distribution systems using deep learning. In: *Proceedings of the 2023 IEEE International Conference on Big Data (BigData)*. IEEE, pp. 6156–6161.
- Tariq, N., Asim, M., Khan, F.A., 2023. Securing SCADA-based critical infrastructures: challenges and open issues. In: *Proceedings of the International Conference on Communication, Computing and Digital Systems (C-CODE)*. IEEE, pp. 1–8.
- US Environmental Protection Agency, 2005. Water Security Initiative: Interim Guidance on Planning for Contamination Warning System Deployment. Report EPA 817-R-05-002. Washington, DC.
- World Health Organisation, 2017. Guidelines for Drinking-Water Quality, 4th ed. incorporating the 1st addendum. WHO Press, Geneva.

---

# Appendix B: Plagiarism and AI Reports of Dissertation and Research Paper

## B.1 Dissertation (Black_Book_Dweep_2.pdf) — Submission 1

- **Submission ID**: trn:oid:::3618:143523404
- **Submission Date**: Jun 18, 2026, 8:14 PM GMT+5:30
- **File Size**: 1.1 MB | 60 Pages | 20,988 Words | 119,619 Characters
- **AI Writing Detection**: Below the 20% surfacing threshold (caution: review required per standard disclaimer)

## B.2 Dissertation (Black_Book_Dweep_2.pdf) — Submission 2 (Similarity Report)

- **Submission ID**: trn:oid:::3618:143523404
- **Overall Similarity**: **7%**

**Match Groups**:
| Category | Count | % |
|---|---|---|
| Not Cited or Quoted | 112 | 6% |
| Missing Quotations | 6 | 0% |
| Missing Citation | 9 | 1% |
| Cited and Quoted | 0 | 0% |

**Top Sources**: 6% Internet sources, 6% Publications, 0% Submitted works (Student Papers)

**Integrity Flags**: 1 flag — Replaced Characters (44 suspect characters on 11 pages; letters swapped with similar characters from another alphabet)

## B.3 Research Paper (paper_env_journal_final.pdf) — Submission 1

- **Submission ID**: trn:oid:::3618:143523402
- **File Size**: 217.6 KB | 12 Pages | 6,362 Words | 37,479 Characters
- **AI Writing Detection**: Below the 20% surfacing threshold (caution: review required per standard disclaimer)

## B.4 Research Paper (paper_env_journal_final.pdf) — Submission 2 (Similarity Report)

- **Submission ID**: trn:oid:::3618:143523402
- **Overall Similarity**: **1%** (Bibliography filtered from report)

**Match Groups**:
| Category | Count | % |
|---|---|---|
| Not Cited or Quoted | 5 | 1% |
| Missing Quotations | 4 | 1% |
| Missing Citation | 0 | 0% |
| Cited and Quoted | 0 | 0% |

**Top Sources**: 1% Internet sources, 1% Publications, 0% Submitted works (Student Papers)

**Integrity Flags**: 1 flag — Replaced Characters (34 suspect characters on 8 pages; letters swapped with similar characters from another alphabet)

---

*End of document.*
