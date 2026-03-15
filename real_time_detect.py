#!/usr/bin/env python3
"""
Real-Time SWAT Attack Detection & Remediation System
=====================================================
Input sensor values → Predict attack → Recommend actions
"""

import numpy as np
import pandas as pd
import joblib
import json
from pathlib import Path
from datetime import datetime
from collections import deque


class SWATAttackDetector:
    """Real-time attack detection with remediation advice."""
    
    # Attack ID to name mapping
    ATTACK_NAMES = {
        0: 'Normal Operation',
        8: 'Tank Overflow Attack',
        9: 'Chemical Depletion Attack',
        10: 'Membrane Damage Attack',
        11: 'pH Manipulation Attack',
        12: 'Slow Ramp Attack',
        13: 'Reconnaissance Scan',
        14: 'Denial of Service',
        15: 'Replay Attack',
        16: 'Valve Manipulation Attack',
        17: 'Multi-Variable Stealth',
        18: 'Single Register Attack',
        19: 'Single Coil Attack',
        20: 'Multi-Point Attack',
    }
    
    # Remediation actions
    REMEDIATION = {
        8: {  # Tank Overflow
            'severity': 'CRITICAL',
            'immediate': [
                'STOP feed pumps P_101, P_102 immediately',
                'Open drain valve MV_101 to maximum',
                'Activate overflow diversion to backup tank'
            ],
            'investigation': [
                'Check level sensor LIT_101 calibration',
                'Verify pump control logic (should stop at 900L)',
                'Review command logs for unauthorized writes',
                'Inspect for Modbus FC06 writes to register 1'
            ],
            'prevention': [
                'Implement hard limit in PLC (stop pumps at 850L)',
                'Add redundant level sensor with voting logic',
                'Enable write verification on critical registers'
            ]
        },
        9: {  # Chemical Depletion
            'severity': 'HIGH',
            'immediate': [
                'Switch to backup chemical tanks',
                'Reduce dosing rate to minimum safe level',
                'Alert chemical supplier for emergency refill'
            ],
            'investigation': [
                'Check tank level sensors (Acid_Tank_Level, etc.)',
                'Review dosing pump runtime logs',
                'Verify no unauthorized pump activations',
                'Inspect Modbus writes to registers 8-10'
            ],
            'prevention': [
                'Set minimum tank level alarm at 30%',
                'Implement automatic ordering at 20%',
                'Add flow meters on chemical lines for mass balance'
            ]
        },
        10: {  # Membrane Damage
            'severity': 'CRITICAL',
            'immediate': [
                'STOP UF feed pump P_301 immediately',
                'Initiate emergency backwash cycle',
                'Reduce transmembrane pressure to <30 kPa'
            ],
            'investigation': [
                'Read DPIT_301 history - check for exponential rise',
                'Verify backwash schedule (should be every 4 hours)',
                'Check for disabled UF_Backwash_Active coil',
                'Inspect membrane integrity with visual/pressure test'
            ],
            'prevention': [
                'Enforce maximum TMP limit in PLC (50 kPa)',
                'Automate backwash - cannot be manually disabled',
                'Add fouling prediction model (predict before critical)'
            ]
        },
        11: {  # pH Manipulation
            'severity': 'HIGH',
            'immediate': [
                'Verify pH sensor AIT_202 with manual test',
                'If sensor OK: increase acid dosing (P_203 ON)',
                'If sensor spoofed: switch to backup pH sensor',
                'Divert water to holding tank until pH normalized'
            ],
            'investigation': [
                'Compare AIT_202 vs manual pH meter reading',
                'Check acid pump P_203 status vs pH trend',
                'Review Modbus writes to register 4 (pH sensor)',
                'Verify acid tank level vs pump runtime'
            ],
            'prevention': [
                'Install redundant pH sensor with cross-validation',
                'Implement rate-of-change limits (pH cannot change >0.5/min)',
                'Lock critical sensor registers (read-only for SCADA)'
            ]
        },
        12: {  # Slow Ramp
            'severity': 'MEDIUM',
            'immediate': [
                'Identify ramping parameter (use derivative analysis)',
                'Reset parameter to safe setpoint',
                'Enable stricter rate-of-change alarms'
            ],
            'investigation': [
                'Analyze all sensor trends for gradual drift',
                'Check for repeated small Modbus writes',
                'Review parameter change logs',
                'Identify attack source IP from network logs'
            ],
            'prevention': [
                'Implement slope detection (alert if sustained drift)',
                'Add parameter change velocity limits',
                'Require authentication for setpoint changes'
            ]
        },
        13: {  # Reconnaissance
            'severity': 'MEDIUM',
            'immediate': [
                'Enable Modbus request logging',
                'Monitor for abnormal read patterns',
                'Block suspicious source IPs at firewall'
            ],
            'investigation': [
                'Identify source IP of scan',
                'Check if internal or external origin',
                'Review firewall logs for entry point',
                'Analyze scanned address range for attack planning'
            ],
            'prevention': [
                'Implement rate limiting (max 10 reads/sec per client)',
                'Require authentication for Modbus access',
                'Use network segmentation (ICS on isolated VLAN)'
            ]
        },
        14: {  # Denial of Service
            'severity': 'CRITICAL',
            'immediate': [
                'Identify attack source IP',
                'Block source at firewall immediately',
                'Restart PLC Modbus service if unresponsive',
                'Switch to backup communication path if available'
            ],
            'investigation': [
                'Analyze packet capture for flood pattern',
                'Check PLC CPU load and memory usage',
                'Review network switch logs for traffic spike',
                'Determine if coordinated attack (multiple sources)'
            ],
            'prevention': [
                'Deploy IDS/IPS with rate limiting',
                'Implement connection limits per IP',
                'Use hardware firewall with DDoS protection',
                'Add redundant communication channels'
            ]
        },
        15: {  # Replay Attack
            'severity': 'HIGH',
            'immediate': [
                'Compare sensor values to physical measurements',
                'If frozen values detected: switch to backup sensors',
                'Disable Modbus write access temporarily'
            ],
            'investigation': [
                'Identify repeating sensor patterns (same values)',
                'Check timestamp consistency',
                'Analyze Modbus write sequences',
                'Correlate with actual process behavior'
            ],
            'prevention': [
                'Implement timestamp validation',
                'Add sequence numbers to Modbus messages',
                'Use challenge-response authentication',
                'Enable integrity checks (HMAC signatures)'
            ]
        },
        16: {  # Valve Manipulation
            'severity': 'HIGH',
            'immediate': [
                'Manually verify valve positions (MV_101, MV_201, etc.)',
                'Force valves to safe positions via local control',
                'Isolate affected stage if necessary'
            ],
            'investigation': [
                'Check valve position sensors vs commanded position',
                'Review Modbus writes to valve registers',
                'Verify no stuck/failed actuators',
                'Inspect for mechanical tampering'
            ],
            'prevention': [
                'Add position feedback sensors (confirm valve state)',
                'Implement interlocks (cannot close valve if pump running)',
                'Require dual confirmation for critical valves'
            ]
        },
    }
    
    def __init__(self, model_dir='trained_models'):
        """Load trained model and supporting files."""
        self.model_dir = Path(model_dir)
        
        
        print("Loading model...")
        
        # Load metadata
        with open(self.model_dir / 'model_metadata.json') as f:
            self.metadata = json.load(f)
        
        print(f"  Model type: {self.metadata['model_type']}")
        print(f"  Accuracy: {self.metadata['accuracy']:.2%}")
        
        # Load model
        model_file = list(self.model_dir.glob('best_model_*.pkl'))[0]
        loaded_model = joblib.load(model_file)
        if isinstance(loaded_model, tuple):
            self.model = loaded_model[0]   # actual model
            self.label_encoder = loaded_model[1] if len(loaded_model) > 1 else None
        else:
            self.model = loaded_model
        self.label_encoder = None
        
        # Load scaler
        self.scaler = joblib.load(self.model_dir / 'scaler.pkl')
        
        # Load feature names
        with open(self.model_dir / 'feature_names.txt') as f:
            self.feature_names = [line.strip() for line in f]
        
        print(f"  Features: {len(self.feature_names)}")
        
        # History for temporal features
        self.history = deque(maxlen=30)
        self.base_state = {
            'FIT_101': 50, 'LIT_101': 650, 'MV_101': 1,
            'P_101': 1, 'P_102': 0, 'AIT_202': 720,
            'FIT_201': 48, 'P_203': 1, 'P_205': 1, 'P_206': 0,
            'Acid_Tank_Level': 75, 'Chlorine_Tank_Level': 80,
            'DPIT_301': 250, 'FIT_301': 45, 'LIT_301': 750,
            'PIT_501': 1260, 'FIT_501': 45
        }
        
        print("✓ Model loaded successfully\n")
    
    def preprocess_input(self, sensor_data: dict) -> np.ndarray:
        """
        Convert raw sensor data to feature vector.
        
        Args:
            sensor_data: Dict of sensor_name: value
            
        Returns:
            Feature vector ready for prediction
        """
        current_state = self.base_state.copy()
        if self.history:
            current_state.update(self.history[-1])
        current_state.update(sensor_data)
        self.history.append(current_state)
        
        # If not enough history, duplicate
        while len(self.history) < 30:
            self.history.append(current_state.copy())
        
        # Calculate temporal features
        features = self._calculate_features(current_state)
        
        # Ensure all features present
        feature_vector = np.zeros(len(self.feature_names))
        for i, name in enumerate(self.feature_names):
            if name in features:
                feature_vector[i] = features[name]
        
        # Scale
        feature_df = pd.DataFrame([feature_vector], columns=self.feature_names)
        feature_vector_scaled = self.scaler.transform(feature_df)
        
        return pd.DataFrame(feature_vector_scaled, columns=self.feature_names)
    
    def _calculate_features(self, current: dict) -> dict:
        """Calculate engineered features from history."""
        features = current.copy()
        
        # Get historical values
        tracked_keys = set(current.keys())
        tracked_keys.update({
            'AIT_202', 'LIT_101', 'DPIT_301', 'PIT_501',
            'FIT_101', 'FIT_301', 'LIT_301', 'FIT_501',
            'MV_101', 'P_101', 'P_102', 'P_203', 'P_205', 'P_206'
        })
        history_array = {key: [h.get(key, 0) for h in self.history] for key in tracked_keys}
        
        # Temporal features
        for sensor in ['AIT_202', 'LIT_101', 'DPIT_301', 'PIT_501', 'FIT_101', 'FIT_301', 'LIT_301']:
            if sensor not in history_array:
                continue
            
            values = history_array[sensor]
            
            # Rate of change
            if len(values) > 1:
                features[f'{sensor}_rate'] = values[-1] - values[-2]
                features[f'{sensor}_accel'] = (values[-1] - values[-2]) - (values[-2] - values[-3] if len(values) > 2 else 0)
            
            # Rolling stats
            for window in [5, 10, 30]:
                w = min(window, len(values))
                features[f'{sensor}_mean_{window}s'] = np.mean(values[-w:])
                features[f'{sensor}_std_{window}s'] = np.std(values[-w:])
                features[f'{sensor}_max_{window}s'] = np.max(values[-w:])
                features[f'{sensor}_min_{window}s'] = np.min(values[-w:])
        
        # Physics features
        if 'LIT_101' in current and 'FIT_101' in current:
            expected_rate = current['FIT_101'] * 100 / 3600
            actual_rate = features.get('LIT_101_rate', 0)
            features['mass_balance_violation_s1'] = abs(expected_rate - actual_rate)
        
        if 'AIT_202' in current and 'P_203' in current:
            ph_rising = 1 if features.get('AIT_202_rate', 0) > 0 else 0
            pump_off = 0 if current['P_203'] else 1
            features['ph_pump_anomaly'] = ph_rising * pump_off

        if 'DPIT_301' in history_array:
            values = history_array['DPIT_301']
            prev = values[-2] if len(values) > 1 else values[-1]
            features['tmp_fouling_rate'] = (values[-1] - prev) / (abs(prev) + 1e-6)
            features['tmp_exp_indicator'] = int(features['tmp_fouling_rate'] > 0.05)

        if 'PIT_501' in current and 'FIT_501' in current:
            features['pressure_flow_ratio'] = current['PIT_501'] / (current['FIT_501'] + 1)

        if all(sensor in current for sensor in ['FIT_101', 'LIT_101', 'MV_101']):
            features['stage1_avg'] = np.mean([current['FIT_101'], current['LIT_101'], current['MV_101']])

        pump_cols = [key for key in current if key.startswith('P_') and key[2:].isdigit()]
        if pump_cols:
            features['total_pumps_on'] = sum(int(bool(current[p])) for p in pump_cols)

        if 'LIT_101' in current and 'LIT_301' in current:
            features['tank_ratio_101_301'] = current['LIT_101'] / (current['LIT_301'] + 1)

        for sensor in ['AIT_202', 'LIT_101', 'DPIT_301', 'PIT_501']:
            if sensor not in history_array:
                continue
            values = np.asarray(history_array[sensor], dtype=float)
            prior = values[:-1]
            if len(prior) >= 5:
                mean = prior.mean()
                std = prior.std()
                features[f'{sensor}_zscore'] = (values[-1] - mean) / (std + 1e-6)
                q25 = np.quantile(prior[-30:], 0.25)
                q75 = np.quantile(prior[-30:], 0.75)
                iqr = q75 - q25
                lower = q25 - 1.5 * iqr
                upper = q75 + 1.5 * iqr
                features[f'{sensor}_outlier_dist'] = max(0, lower - values[-1], values[-1] - upper)
            else:
                features[f'{sensor}_zscore'] = 0
                features[f'{sensor}_outlier_dist'] = 0
        
        return features
    
    def predict(self, sensor_data: dict) -> dict:
        """
        Predict attack from sensor data.
        
        Args:
            sensor_data: Dict of sensor values
            
        Returns:
            Dict with prediction results and recommendations
        """
        # Preprocess
        X = self.preprocess_input(sensor_data)
        
        # Predict
        if hasattr(self.model, 'predict_proba'):
            proba = self.model.predict_proba(X)[0]
            class_labels = getattr(self.model, 'classes_', np.arange(len(proba)))
            best_idx = int(np.argmax(proba))
            prediction = class_labels[best_idx]
            confidence = proba[best_idx]
        else:
            prediction = self.model.predict(X)[0]
            if self.label_encoder is not None:
                prediction = self.label_encoder.inverse_transform([prediction])[0]
            confidence = 1.0
        
        # Get attack info
        attack_id = int(prediction)
        attack_name = self.ATTACK_NAMES.get(attack_id, 'Unknown')
        
        # Get remediation if attack detected
        remediation = None
        if attack_id != 0 and attack_id in self.REMEDIATION:
            remediation = self.REMEDIATION[attack_id]
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'attack_detected': attack_id != 0,
            'attack_id': attack_id,
            'attack_name': attack_name,
            'confidence': float(confidence),
            'sensor_data': sensor_data,
            'remediation': remediation
        }
        
        return result
    
    def print_result(self, result: dict):
        """Pretty print prediction result."""
        print("="*70)
        print("ATTACK DETECTION RESULT")
        print("="*70)
        print(f"Timestamp: {result['timestamp']}")
        print(f"\nPrediction: {result['attack_name']} (ID: {result['attack_id']})")
        print(f"Confidence: {result['confidence']:.2%}")
        
        if result['attack_detected']:
            print(f"\n⚠ ATTACK DETECTED: {result['attack_name']}")
            
            if result['remediation']:
                rem = result['remediation']
                print(f"\nSeverity: {rem['severity']}")
                
                print("\n🚨 IMMEDIATE ACTIONS:")
                for i, action in enumerate(rem['immediate'], 1):
                    print(f"  {i}. {action}")
                
                print("\n🔍 INVESTIGATION STEPS:")
                for i, step in enumerate(rem['investigation'], 1):
                    print(f"  {i}. {step}")
                
                print("\n🛡️  PREVENTION MEASURES:")
                for i, measure in enumerate(rem['prevention'], 1):
                    print(f"  {i}. {measure}")
        else:
            print("\n✓ System operating normally")
        
        print("\nCurrent Sensor Readings:")
        for sensor, value in result['sensor_data'].items():
            print(f"  {sensor}: {value}")
        
        print("="*70)


def interactive_mode():
    """Interactive command-line interface."""
    detector = SWATAttackDetector()
    
    print("\n" + "="*70)
    print("SWAT REAL-TIME ATTACK DETECTION")
    print("="*70)
    print("\nEnter sensor values (or 'quit' to exit)")
    print("Format: sensor_name=value (e.g., LIT_101=650)")
    print("Enter 'auto' to use example scenarios\n")
    
    while True:
        print("\n" + "-"*70)
        choice = input("Input (manual/auto/quit): ").strip().lower()
        
        if choice == 'quit':
            break
        
        elif choice == 'auto':
            # Example scenarios
            scenarios = {
                'normal': {
                    'FIT_101': 50, 'LIT_101': 650, 'MV_101': 1,
                    'P_101': True, 'P_102': False,
                    'AIT_202': 720, 'FIT_201': 48,
                    'P_203': True, 'P_205': True, 'P_206': False,
                    'Acid_Tank_Level': 75, 'Chlorine_Tank_Level': 80,
                    'DPIT_301': 250, 'FIT_301': 45, 'LIT_301': 750,
                    'PIT_501': 1260, 'TDS_Permeate': 95
                },
                'tank_overflow': {
                    'FIT_101': 50, 'LIT_101': 985, 'MV_101': 0,  # High level!
                    'P_101': True, 'P_102': True,  # Pumps still running!
                    'AIT_202': 720, 'FIT_201': 48,
                    'DPIT_301': 250, 'PIT_501': 1260
                },
                'ph_attack': {
                    'FIT_101': 50, 'LIT_101': 650,
                    'AIT_202': 480,  # Low pH!
                    'P_203': False,  # Pump off!
                    'Acid_Tank_Level': 75,  # But tank has acid
                    'DPIT_301': 250, 'PIT_501': 1260
                },
                'membrane_damage': {
                    'FIT_101': 50, 'LIT_101': 650,
                    'AIT_202': 720,
                    'DPIT_301': 620,  # Very high TMP!
                    'UF_Backwash_Active': False,  # No backwash
                    'PIT_501': 1260
                }
            }
            
            print("\nAvailable scenarios:")
            for i, name in enumerate(scenarios.keys(), 1):
                print(f"  {i}. {name}")
            
            idx = input("Choose scenario (1-4): ").strip()
            scenario_names = list(scenarios.keys())
            
            if idx.isdigit() and 1 <= int(idx) <= len(scenarios):
                sensor_data = scenarios[scenario_names[int(idx)-1]]
                result = detector.predict(sensor_data)
                detector.print_result(result)
            
        else:
            # Manual input
            sensor_data = {}
            print("Enter sensor values (empty line to finish):")
            while True:
                line = input("  ").strip()
                if not line:
                    break
                
                try:
                    key, val = line.split('=')
                    key = key.strip()
                    parsed = float(val.strip()) if '.' in val else int(val.strip())
                    if key == 'AIT_202' and parsed <= 14:
                        parsed = int(parsed * 100)
                    sensor_data[key] = parsed
                except:
                    print("  Invalid format, use: sensor_name=value")
            
            if sensor_data:
                result = detector.predict(sensor_data)
                detector.print_result(result)


def batch_mode(csv_file: str, output_file: str = 'predictions.csv'):
    """Batch prediction on CSV file."""
    detector = SWATAttackDetector()
    
    print(f"Loading data from {csv_file}...")
    df = pd.read_csv(csv_file)
    
    print(f"Processing {len(df)} samples...")
    
    predictions = []
    for idx, row in df.iterrows():
        sensor_data = row.to_dict()
        result = detector.predict(sensor_data)
        
        predictions.append({
            'timestamp': result['timestamp'],
            'attack_id': result['attack_id'],
            'attack_name': result['attack_name'],
            'confidence': result['confidence']
        })
        
        if idx % 1000 == 0:
            print(f"  Processed {idx}/{len(df)}")
    
    # Save
    pred_df = pd.DataFrame(predictions)
    pred_df.to_csv(output_file, index=False)
    
    print(f"\n✓ Saved predictions to {output_file}")
    
    # Summary
    print("\nPrediction Summary:")
    print(pred_df['attack_name'].value_counts())


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        # Batch mode
        csv_file = sys.argv[1]
        output = sys.argv[2] if len(sys.argv) > 2 else 'predictions.csv'
        batch_mode(csv_file, output)
    else:
        # Interactive mode
        interactive_mode()
