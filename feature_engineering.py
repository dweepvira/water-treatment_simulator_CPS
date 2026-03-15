#!/usr/bin/env python3
"""
Enhanced SWAT Dataset Analysis with Feature Engineering
========================================================
Fixes low accuracy by adding:
- Temporal features (rate of change, rolling stats)
- Physics-based features (mass balance violations)
- Correlation features (multi-sensor patterns)
"""

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.preprocessing import StandardScaler, RobustScaler
import warnings
warnings.filterwarnings('ignore')


class SWATFeatureEngineer:
    """Extract physics-based and temporal features."""
    
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.features_created = []
    
    def add_temporal_features(self, windows=[5, 10, 30]):
        """Rate of change and rolling statistics."""
        print("Adding temporal features...")
        
        sensors = ['AIT_202', 'LIT_101', 'DPIT_301', 'PIT_501', 
                   'FIT_101', 'FIT_301', 'LIT_301']
        
        for sensor in sensors:
            if sensor not in self.df.columns:
                continue
            
            # Rate of change (derivative)
            self.df[f'{sensor}_rate'] = self.df[sensor].diff()
            self.features_created.append(f'{sensor}_rate')
            
            # Acceleration (2nd derivative)
            self.df[f'{sensor}_accel'] = self.df[f'{sensor}_rate'].diff()
            self.features_created.append(f'{sensor}_accel')
            
            # Rolling statistics
            for window in windows:
                self.df[f'{sensor}_mean_{window}s'] = self.df[sensor].rolling(window).mean()
                self.df[f'{sensor}_std_{window}s'] = self.df[sensor].rolling(window).std()
                self.df[f'{sensor}_max_{window}s'] = self.df[sensor].rolling(window).max()
                self.df[f'{sensor}_min_{window}s'] = self.df[sensor].rolling(window).min()
                
                self.features_created.extend([
                    f'{sensor}_mean_{window}s',
                    f'{sensor}_std_{window}s',
                    f'{sensor}_max_{window}s',
                    f'{sensor}_min_{window}s'
                ])
        
        print(f"  Created {len(self.features_created)} temporal features")
        return self
    
    def add_physics_features(self):
        """Physics-based violation detection."""
        print("Adding physics-based features...")
        
        # Mass balance: Stage 1
        if all(c in self.df.columns for c in ['FIT_101', 'LIT_101']):
            # dV/dt should match inflow - outflow
            expected_rate = self.df['FIT_101'] * 100 / 3600  # m³/h → L/s
            actual_rate = self.df['LIT_101'].diff()
            self.df['mass_balance_violation_s1'] = np.abs(expected_rate - actual_rate)
            self.features_created.append('mass_balance_violation_s1')
        
        # pH-pump correlation
        # pH-pump correlation
        if all(c in self.df.columns for c in ['AIT_202', 'P_203']):

            ph_rising = (self.df['AIT_202'].diff() > 0).astype(int)

            pump_state = self.df['P_203'].fillna(0).astype(int)
            pump_off = (pump_state == 0).astype(int)

            self.df['ph_pump_anomaly'] = (ph_rising & pump_off).astype(int)
            self.features_created.append('ph_pump_anomaly')
        
        # Membrane fouling rate
        if 'DPIT_301' in self.df.columns:
            # Exponential growth indicator
            self.df['tmp_fouling_rate'] = self.df['DPIT_301'].pct_change()
            self.df['tmp_exp_indicator'] = (self.df['tmp_fouling_rate'] > 0.05).astype(int)
            self.features_created.extend(['tmp_fouling_rate', 'tmp_exp_indicator'])
        
        # Pressure consistency
        if all(c in self.df.columns for c in ['PIT_501', 'FIT_501']):
            # High pressure should correlate with flow
            self.df['pressure_flow_ratio'] = self.df['PIT_501'] / (self.df['FIT_501'] + 1)
            self.features_created.append('pressure_flow_ratio')
        
        print(f"  Created {len([f for f in self.features_created if 'violation' in f or 'anomaly' in f])} physics features")
        return self
    
    def add_correlation_features(self):
        """Multi-sensor correlation patterns."""
        print("Adding correlation features...")
        
        # Stage-level aggregates
        stage1_sensors = ['FIT_101', 'LIT_101', 'MV_101']
        if all(c in self.df.columns for c in stage1_sensors):
            self.df['stage1_avg'] = self.df[stage1_sensors].mean(axis=1)
            self.features_created.append('stage1_avg')
        
        # Pump count
        pump_cols = [c for c in self.df.columns if c.startswith('P_') and c[2:].isdigit()]
        if pump_cols:
            self.df['total_pumps_on'] = self.df[pump_cols].sum(axis=1)
            self.features_created.append('total_pumps_on')
        
        # Tank levels ratio
        if all(c in self.df.columns for c in ['LIT_101', 'LIT_301']):
            self.df['tank_ratio_101_301'] = self.df['LIT_101'] / (self.df['LIT_301'] + 1)
            self.features_created.append('tank_ratio_101_301')
        
        print(f"  Created correlation features")
        return self
    
    def add_statistical_features(self):
        """Causal statistical anomaly indicators using only past data."""
        print("Adding statistical features...")
        
        key_sensors = ['AIT_202', 'LIT_101', 'DPIT_301', 'PIT_501']
        
        for sensor in key_sensors:
            if sensor not in self.df.columns:
                continue
            
            prior = self.df[sensor].shift(1)
            mean = prior.expanding(min_periods=5).mean()
            std = prior.expanding(min_periods=5).std()
            self.df[f'{sensor}_zscore'] = (self.df[sensor] - mean) / (std + 1e-6)
            self.features_created.append(f'{sensor}_zscore')
            
            recent = prior.rolling(30, min_periods=5)
            q25 = recent.quantile(0.25)
            q75 = recent.quantile(0.75)
            iqr = q75 - q25
            lower = q25 - 1.5 * iqr
            upper = q75 + 1.5 * iqr
            
            self.df[f'{sensor}_outlier_dist'] = np.maximum(
                0, 
                np.maximum(lower - self.df[sensor], self.df[sensor] - upper)
            )
            self.features_created.append(f'{sensor}_outlier_dist')
        
        print(f"  Created statistical features")
        return self
    
    def get_feature_matrix(self):
        """Return cleaned feature matrix."""
        # Forward fill preserves time direction; backfill leaks future values.
        self.df = self.df.ffill().fillna(0)
        
        # Get all numeric columns
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns.tolist()
        
        # Exclude labels
        exclude = ['ATTACK_ID', 'Timestamp']
        feature_cols = [c for c in numeric_cols if c not in exclude]
        
        print(f"\nTotal features: {len(feature_cols)}")
        print(f"  Original sensors: ~76")
        print(f"  Engineered: {len(self.features_created)}")
        
        return self.df[feature_cols], self.df['ATTACK_ID']


def analyze_and_prepare_dataset(csv_path: str, output_dir: str = 'ml_ready'):
    """Complete pipeline: load → engineer → save."""
    
    print(f"Loading dataset: {csv_path}")
    df = pd.read_csv(csv_path)
    pump_cols = [c for c in df.columns if c.startswith('P_')]
    df[pump_cols] = df[pump_cols].fillna(0).astype(int)
    
    print(f"  Shape: {df.shape}")
    print(f"  Classes: {df['ATTACK_ID'].nunique()}")
    print(f"  Class distribution:\n{df['ATTACK_ID'].value_counts()}")
    
    # Feature engineering
    engineer = SWATFeatureEngineer(df)
    engineer.add_temporal_features(windows=[5, 10, 30])
    engineer.add_physics_features()
    engineer.add_correlation_features()
    engineer.add_statistical_features()
    
    X, y = engineer.get_feature_matrix()
    
    # Save
    Path(output_dir).mkdir(exist_ok=True)
    
    # Save features
    X.to_csv(f'{output_dir}/features.csv', index=False)
    y.to_csv(f'{output_dir}/labels.csv', index=False)
    
    # Save feature names
    with open(f'{output_dir}/feature_names.txt', 'w') as f:
        for col in X.columns:
            f.write(f"{col}\n")
    
    print(f"\nSaved to {output_dir}/")
    print(f"  Features: {X.shape}")
    print(f"  Labels: {y.shape}")
    
    return X, y


if __name__ == '__main__':
    import sys
    
    csv_path = sys.argv[1] if len(sys.argv) > 1 else 'dataset/master_dataset.csv'
    X, y = analyze_and_prepare_dataset(csv_path)
