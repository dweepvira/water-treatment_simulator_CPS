#!/usr/bin/env python3
"""
SWAT DATASET COMPREHENSIVE ANALYSIS SCRIPT
==========================================
Complete data validation, cleaning, analysis, and visualization

This script performs:
1. Data loading with type validation
2. Column-by-column statistical analysis
3. Attack pattern detection and validation
4. Missing data handling
5. Outlier detection (physics-based)
6. Temporal consistency checks
7. Correlation analysis
8. Comprehensive visualization
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Set visualization style
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")


# ═══════════════════════════════════════════════════════════════════════════
# 1. DATA LOADING & VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

class SWATDataValidator:
    """
    Validates SWAT dataset structure and content.
    
    Expected structure:
    - Timestamp (datetime)
    - 51 sensor registers (numeric)
    - 25 actuator coils (boolean/int 0-1)
    - ATTACK_ID (int 0-20)
    - ATTACK_NAME (string)
    - MITRE_ID (string)
    """
    
    # Expected columns (from SWAT system)
    SENSOR_COLUMNS = [
        'FIT_101', 'LIT_101', 'MV_101',  # Stage 1
        'AIT_201', 'AIT_202', 'FIT_201', 'MV_201', 
        'Acid_Tank_Level', 'Chlorine_Tank_Level', 'Coagulant_Tank_Level',  # Stage 2
        'FIT_301', 'DPIT_301', 'LIT_301', 'MV_301', 'MV_302', 'MV_303', 'MV_304',
        'UF_Feed_Flow', 'UF_Permeate_Flow', 'UF_Hours_Since_BW', 'UF_Total_Filtered',  # Stage 3
        'FIT_401', 'LIT_401',  # Stage 4
        'AIT_501', 'AIT_502', 'AIT_503', 'FIT_501', 'PIT_501', 'TDS_Permeate',  # Stage 5
        'FIT_601', 'TEMP_101', 'TEMP_201',  # Stage 6
    ]
    
    ACTUATOR_COLUMNS = [
        'P_101', 'P_102', 'P_201', 'P_202', 'P_203', 'P_204', 'P_205', 'P_206',
        'P_301', 'P_302', 'P_401', 'P_402', 'P_501', 'P_601',
        'UV_401', 'System_Run', 'UF_Backwash_Active',
        'High_Level_Alarm', 'Chemical_Low_Alarm', 'High_Fouling_Alarm', 'High_Pressure_Alarm',
    ]
    
    LABEL_COLUMNS = ['ATTACK_ID', 'ATTACK_NAME', 'MITRE_ID']
    
    # Physical limits (from engineering specs)
    PHYSICAL_LIMITS = {
        'FIT_101': (0, 100),      # 0-10 m³/h
        'LIT_101': (0, 1200),     # 0-1200 L
        'AIT_202': (0, 1400),     # pH 0-14 (×100)
        'DPIT_301': (0, 1000),    # 0-100 kPa (×10)
        'PIT_501': (0, 2500),     # 0-250 bar (×10)
        'TEMP_101': (0, 500),     # 0-50°C (×10)
        'Acid_Tank_Level': (0, 100),  # 0-100%
    }
    
    def __init__(self, csv_path: str):
        self.csv_path = Path(csv_path)
        self.df = None
        self.validation_report = {
            'total_rows': 0,
            'total_columns': 0,
            'missing_columns': [],
            'type_errors': [],
            'range_violations': [],
            'duplicates': 0,
            'missing_values': {},
            'issues': []
        }
    
    def load(self):
        """Load CSV with validation."""
        print("\n" + "="*70)
        print("STEP 1: DATA LOADING & VALIDATION")
        print("="*70)
        
        if not self.csv_path.exists():
            raise FileNotFoundError(f"Dataset not found: {self.csv_path}")
        
        # Load CSV
        print(f"\nLoading: {self.csv_path}")
        self.df = pd.read_csv(self.csv_path)
        
        self.validation_report['total_rows'] = len(self.df)
        self.validation_report['total_columns'] = len(self.df.columns)
        
        print(f"  ✓ Loaded: {len(self.df):,} rows × {len(self.df.columns)} columns")
        print(f"  ✓ File size: {self.csv_path.stat().st_size / 1024 / 1024:.2f} MB")
        
        return self
    
    def validate_structure(self):
        """Validate column structure."""
        print("\n" + "-"*70)
        print("Validating Structure...")
        print("-"*70)
        
        # Check for timestamp
        if 'Timestamp' in self.df.columns:
            print("  ✓ Timestamp column present")
            try:
                self.df['Timestamp'] = pd.to_datetime(self.df['Timestamp'])
                print(f"    Date range: {self.df['Timestamp'].min()} to {self.df['Timestamp'].max()}")
                print(f"    Duration: {self.df['Timestamp'].max() - self.df['Timestamp'].min()}")
            except Exception as e:
                self.validation_report['type_errors'].append(f"Timestamp conversion failed: {e}")
                print(f"  ✗ Timestamp conversion error: {e}")
        else:
            self.validation_report['issues'].append("Timestamp column missing")
            print("  ✗ Timestamp column missing")
        
        # Check for required columns
        all_required = self.SENSOR_COLUMNS + self.ACTUATOR_COLUMNS + self.LABEL_COLUMNS
        missing = [col for col in all_required if col not in self.df.columns]
        
        if missing:
            self.validation_report['missing_columns'] = missing
            print(f"\n  ⚠ Missing columns ({len(missing)}):")
            for col in missing[:10]:  # Show first 10
                print(f"    - {col}")
            if len(missing) > 10:
                print(f"    ... and {len(missing)-10} more")
        else:
            print("  ✓ All expected columns present")
        
        # Check for extra columns
        extra = [col for col in self.df.columns if col not in all_required + ['Timestamp']]
        if extra:
            print(f"\n  ℹ Extra columns ({len(extra)}): {extra[:5]}")
        
        return self
    
    def validate_data_types(self):
        """Validate data types and ranges."""
        print("\n" + "-"*70)
        print("Validating Data Types & Ranges...")
        print("-"*70)
        
        # Sensor columns should be numeric
        for col in self.SENSOR_COLUMNS:
            if col in self.df.columns:
                if not pd.api.types.is_numeric_dtype(self.df[col]):
                    self.validation_report['type_errors'].append(f"{col} is not numeric")
                    print(f"  ✗ {col}: Expected numeric, got {self.df[col].dtype}")
                else:
                    # Check physical limits
                    if col in self.PHYSICAL_LIMITS:
                        min_val, max_val = self.PHYSICAL_LIMITS[col]
                        violations = ((self.df[col] < min_val) | (self.df[col] > max_val)).sum()
                        
                        if violations > 0:
                            self.validation_report['range_violations'].append({
                                'column': col,
                                'violations': int(violations),
                                'min': float(self.df[col].min()),
                                'max': float(self.df[col].max()),
                                'expected_range': (min_val, max_val)
                            })
                            print(f"  ⚠ {col}: {violations:,} values outside [{min_val}, {max_val}]")
                            print(f"    Actual range: [{self.df[col].min():.2f}, {self.df[col].max():.2f}]")
        
        # Actuator columns should be boolean (0/1)
        for col in self.ACTUATOR_COLUMNS:
            if col in self.df.columns:
                unique_vals = self.df[col].unique()
                if not set(unique_vals).issubset({0, 1, True, False}):
                    self.validation_report['type_errors'].append(f"{col} has invalid values: {unique_vals}")
                    print(f"  ✗ {col}: Expected 0/1, got {unique_vals}")
        
        # ATTACK_ID should be integer 0-20
        if 'ATTACK_ID' in self.df.columns:
            if self.df['ATTACK_ID'].min() < 0 or self.df['ATTACK_ID'].max() > 20:
                print(f"  ⚠ ATTACK_ID range: [{self.df['ATTACK_ID'].min()}, {self.df['ATTACK_ID'].max()}]")
                print(f"    Expected: [0, 20]")
        
        print("\n  ✓ Data type validation complete")
        return self
    
    def validate_missing_data(self):
        """Check for missing values."""
        print("\n" + "-"*70)
        print("Validating Missing Data...")
        print("-"*70)
        
        missing = self.df.isnull().sum()
        missing_pct = (missing / len(self.df)) * 100
        
        cols_with_missing = missing[missing > 0]
        
        if len(cols_with_missing) > 0:
            print(f"\n  ⚠ Found missing values in {len(cols_with_missing)} columns:")
            for col, count in cols_with_missing.items():
                pct = missing_pct[col]
                print(f"    {col:30s}: {count:6,} ({pct:5.2f}%)")
                self.validation_report['missing_values'][col] = {
                    'count': int(count),
                    'percentage': float(pct)
                }
        else:
            print("  ✓ No missing values found")
        
        return self
    
    def validate_duplicates(self):
        """Check for duplicate rows."""
        print("\n" + "-"*70)
        print("Validating Duplicates...")
        print("-"*70)
        
        duplicates = self.df.duplicated().sum()
        self.validation_report['duplicates'] = int(duplicates)
        
        if duplicates > 0:
            print(f"  ⚠ Found {duplicates:,} duplicate rows ({duplicates/len(self.df)*100:.2f}%)")
        else:
            print("  ✓ No duplicate rows found")
        
        return self
    
    def validate_temporal_consistency(self):
        """Check temporal properties."""
        print("\n" + "-"*70)
        print("Validating Temporal Consistency...")
        print("-"*70)
        
        if 'Timestamp' not in self.df.columns:
            print("  ✗ No timestamp column to validate")
            return self
        
        # Check if sorted
        is_sorted = self.df['Timestamp'].is_monotonic_increasing
        if is_sorted:
            print("  ✓ Timestamps are monotonically increasing (properly sorted)")
        else:
            print("  ⚠ Timestamps are NOT sorted (this may affect temporal analysis)")
            self.validation_report['issues'].append("Timestamps not sorted")
        
        # Check sampling rate
        time_diffs = self.df['Timestamp'].diff().dt.total_seconds()
        median_interval = time_diffs.median()
        
        print(f"\n  Sampling interval:")
        print(f"    Median: {median_interval:.2f} seconds")
        print(f"    Min: {time_diffs.min():.2f} seconds")
        print(f"    Max: {time_diffs.max():.2f} seconds")
        
        # Expected: 1 second (1 Hz sampling)
        if abs(median_interval - 1.0) < 0.1:
            print("  ✓ Sampling rate consistent (~1 Hz)")
        else:
            print(f"  ⚠ Sampling rate inconsistent (expected ~1 Hz, got ~{median_interval:.2f} Hz)")
        
        # Check for gaps
        gaps = (time_diffs > 10).sum()  # Gaps > 10 seconds
        if gaps > 0:
            print(f"  ⚠ Found {gaps:,} large time gaps (>10s)")
        else:
            print("  ✓ No large time gaps detected")
        
        return self
    
    def print_summary(self):
        """Print validation summary."""
        print("\n" + "="*70)
        print("VALIDATION SUMMARY")
        print("="*70)
        
        print(f"\nDataset: {self.csv_path.name}")
        print(f"  Rows: {self.validation_report['total_rows']:,}")
        print(f"  Columns: {self.validation_report['total_columns']}")
        
        # Issues
        issues = []
        if self.validation_report['missing_columns']:
            issues.append(f"{len(self.validation_report['missing_columns'])} missing columns")
        if self.validation_report['type_errors']:
            issues.append(f"{len(self.validation_report['type_errors'])} type errors")
        if self.validation_report['range_violations']:
            issues.append(f"{len(self.validation_report['range_violations'])} range violations")
        if self.validation_report['duplicates'] > 0:
            issues.append(f"{self.validation_report['duplicates']:,} duplicates")
        if self.validation_report['missing_values']:
            issues.append(f"{len(self.validation_report['missing_values'])} columns with missing data")
        
        if issues:
            print(f"\n⚠ Issues found:")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("\n✓ Dataset validation passed - no issues found")
        
        return self.df


# ═══════════════════════════════════════════════════════════════════════════
# 2. STATISTICAL ANALYSIS PER COLUMN
# ═══════════════════════════════════════════════════════════════════════════

class ColumnAnalyzer:
    """Detailed statistical analysis for each column."""
    
    def __init__(self, df):
        self.df = df
        self.stats = {}
    
    def analyze_all(self):
        """Analyze all columns."""
        print("\n" + "="*70)
        print("STEP 2: COLUMN-BY-COLUMN STATISTICAL ANALYSIS")
        print("="*70)
        
        # Separate by type
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns
        categorical_cols = self.df.select_dtypes(include=['object']).columns
        
        print(f"\nFound:")
        print(f"  Numeric columns: {len(numeric_cols)}")
        print(f"  Categorical columns: {len(categorical_cols)}")
        
        # Analyze numeric columns
        for col in numeric_cols:
            if col != 'ATTACK_ID':  # Skip label
                self.analyze_numeric_column(col)
        
        # Analyze categorical columns
        for col in categorical_cols:
            self.analyze_categorical_column(col)
        
        return self.stats
    
    def analyze_numeric_column(self, col):
        """Detailed analysis of numeric column."""
        data = self.df[col].dropna()
        
        stats = {
            'count': len(data),
            'missing': self.df[col].isnull().sum(),
            'mean': data.mean(),
            'std': data.std(),
            'min': data.min(),
            'q25': data.quantile(0.25),
            'median': data.median(),
            'q75': data.quantile(0.75),
            'max': data.max(),
            'skewness': data.skew(),
            'kurtosis': data.kurtosis(),
        }
        
        # Outlier detection (IQR method)
        iqr = stats['q75'] - stats['q25']
        lower_fence = stats['q25'] - 1.5 * iqr
        upper_fence = stats['q75'] + 1.5 * iqr
        outliers = ((data < lower_fence) | (data > upper_fence)).sum()
        stats['outliers'] = outliers
        stats['outlier_pct'] = (outliers / len(data)) * 100
        
        self.stats[col] = stats
    
    def analyze_categorical_column(self, col):
        """Analysis of categorical column."""
        stats = {
            'count': len(self.df[col]),
            'missing': self.df[col].isnull().sum(),
            'unique': self.df[col].nunique(),
            'top_value': self.df[col].mode()[0] if len(self.df[col].mode()) > 0 else None,
            'top_count': self.df[col].value_counts().iloc[0] if len(self.df[col]) > 0 else 0,
            'value_counts': self.df[col].value_counts().to_dict()
        }
        
        self.stats[col] = stats
    
    def print_summary(self, col):
        """Print statistics for a column."""
        if col not in self.stats:
            print(f"No stats for {col}")
            return
        
        stats = self.stats[col]
        
        print(f"\n{col}:")
        print("-" * 50)
        
        if 'mean' in stats:  # Numeric
            print(f"  Count: {stats['count']:,}  Missing: {stats['missing']:,}")
            print(f"  Mean: {stats['mean']:.2f}  Std: {stats['std']:.2f}")
            print(f"  Min: {stats['min']:.2f}")
            print(f"  Q25: {stats['q25']:.2f}")
            print(f"  Median: {stats['median']:.2f}")
            print(f"  Q75: {stats['q75']:.2f}")
            print(f"  Max: {stats['max']:.2f}")
            print(f"  Skewness: {stats['skewness']:.3f}")
            print(f"  Kurtosis: {stats['kurtosis']:.3f}")
            print(f"  Outliers: {stats['outliers']:,} ({stats['outlier_pct']:.2f}%)")
        else:  # Categorical
            print(f"  Count: {stats['count']:,}  Missing: {stats['missing']:,}")
            print(f"  Unique values: {stats['unique']}")
            print(f"  Most common: {stats['top_value']} ({stats['top_count']:,} times)")


# ═══════════════════════════════════════════════════════════════════════════
# 3. ATTACK PATTERN ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

class AttackPatternAnalyzer:
    """Analyze attack patterns and signatures."""
    
    def __init__(self, df):
        self.df = df
        self.attack_stats = {}
    
    def analyze(self):
        """Complete attack analysis."""
        print("\n" + "="*70)
        print("STEP 3: ATTACK PATTERN ANALYSIS")
        print("="*70)
        
        if 'ATTACK_ID' not in self.df.columns:
            print("\n⚠ No ATTACK_ID column - skipping attack analysis")
            return
        
        # Overall distribution
        self.analyze_distribution()
        
        # Per-attack statistics
        self.analyze_per_attack()
        
        # Temporal patterns
        self.analyze_temporal_patterns()
        
        # Affected sensors
        self.analyze_affected_sensors()
    
    def analyze_distribution(self):
        """Attack distribution analysis."""
        print("\n" + "-"*70)
        print("Attack Distribution")
        print("-"*70)
        
        total = len(self.df)
        normal = (self.df['ATTACK_ID'] == 0).sum()
        attack = (self.df['ATTACK_ID'] > 0).sum()
        
        print(f"\n  Total rows: {total:,}")
        print(f"  Normal: {normal:,} ({normal/total*100:.2f}%)")
        print(f"  Attack: {attack:,} ({attack/total*100:.2f}%)")
        
        # Per attack type
        print(f"\n  Attack type breakdown:")
        for (aid, name), count in self.df[self.df['ATTACK_ID']>0].groupby(['ATTACK_ID', 'ATTACK_NAME']).size().items():
            pct = count / total * 100
            print(f"    ID {aid:2d} - {name:35s}: {count:6,} ({pct:5.2f}%)")
    
    def analyze_per_attack(self):
        """Per-attack statistics."""
        print("\n" + "-"*70)
        print("Per-Attack Statistics")
        print("-"*70)
        
        for attack_id in sorted(self.df['ATTACK_ID'].unique()):
            if attack_id == 0:
                continue
            
            attack_data = self.df[self.df['ATTACK_ID'] == attack_id]
            name = attack_data['ATTACK_NAME'].iloc[0]
            
            # Duration
            if 'Timestamp' in self.df.columns:
                duration = (attack_data['Timestamp'].max() - attack_data['Timestamp'].min()).total_seconds()
            else:
                duration = len(attack_data)  # In rows
            
            print(f"\n  Attack ID {attack_id}: {name}")
            print(f"    Rows: {len(attack_data):,}")
            print(f"    Duration: {duration:.0f} seconds ({duration/60:.1f} min)")
    
    def analyze_temporal_patterns(self):
        """Temporal attack patterns."""
        print("\n" + "-"*70)
        print("Temporal Patterns")
        print("-"*70)
        
        if 'Timestamp' not in self.df.columns:
            print("  ⚠ No timestamp - skipping temporal analysis")
            return
        
        # Find attack transitions
        self.df['attack_changed'] = self.df['ATTACK_ID'].diff().fillna(0) != 0
        transitions = self.df[self.df['attack_changed']].copy()
        
        print(f"\n  Attack transitions: {len(transitions):,}")
        print(f"  Average attacks: {len(transitions)/2:.1f}")
    
    def analyze_affected_sensors(self):
        """Which sensors change during attacks."""
        print("\n" + "-"*70)
        print("Affected Sensors")
        print("-"*70)
        
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns
        numeric_cols = [c for c in numeric_cols if c != 'ATTACK_ID']
        
        normal_data = self.df[self.df['ATTACK_ID'] == 0]
        attack_data = self.df[self.df['ATTACK_ID'] > 0]
        
        print("\n  Sensor variance comparison (Normal vs Attack):")
        print(f"  {'Sensor':30s} {'Normal Std':>12s} {'Attack Std':>12s} {'Ratio':>10s}")
        print("  " + "-"*66)
        
        for col in numeric_cols[:20]:  # First 20 sensors
            if col in normal_data.columns and col in attack_data.columns:
                normal_std = normal_data[col].std()
                attack_std = attack_data[col].std()
                
                if normal_std > 0:
                    ratio = attack_std / normal_std
                    print(f"  {col:30s} {normal_std:12.2f} {attack_std:12.2f} {ratio:10.2f}x")


# ═══════════════════════════════════════════════════════════════════════════
# 4. DATA CLEANING
# ═══════════════════════════════════════════════════════════════════════════

class DataCleaner:
    """Clean and prepare dataset."""
    
    def __init__(self, df):
        self.df = df.copy()
        self.cleaning_log = []
    
    def clean(self):
        """Execute all cleaning steps."""
        print("\n" + "="*70)
        print("STEP 4: DATA CLEANING")
        print("="*70)
        
        initial_rows = len(self.df)
        initial_cols = len(self.df.columns)
        
        self.remove_duplicates()
        self.handle_missing_values()
        self.clip_outliers()
        self.sort_by_time()
        
        final_rows = len(self.df)
        final_cols = len(self.df.columns)
        
        print("\n" + "-"*70)
        print("Cleaning Summary")
        print("-"*70)
        print(f"  Initial: {initial_rows:,} rows × {initial_cols} columns")
        print(f"  Final: {final_rows:,} rows × {final_cols} columns")
        print(f"  Removed: {initial_rows - final_rows:,} rows ({(initial_rows-final_rows)/initial_rows*100:.2f}%)")
        
        for log_entry in self.cleaning_log:
            print(f"  • {log_entry}")
        
        return self.df
    
    def remove_duplicates(self):
        """Remove duplicate rows."""
        before = len(self.df)
        self.df = self.df.drop_duplicates()
        after = len(self.df)
        
        removed = before - after
        if removed > 0:
            self.cleaning_log.append(f"Removed {removed:,} duplicate rows")
            print(f"\n  ✓ Removed {removed:,} duplicates")
        else:
            print("\n  ✓ No duplicates to remove")
    
    def handle_missing_values(self):
        """Handle missing values."""
        missing_before = self.df.isnull().sum().sum()
        
        if missing_before == 0:
            print("  ✓ No missing values to handle")
            return
        
        print(f"\n  Handling {missing_before:,} missing values...")
        
        # Strategy 1: Forward fill for sensor values (temporal continuity)
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns
        self.df[numeric_cols] = self.df[numeric_cols].fillna(method='ffill')
        
        # Strategy 2: Backward fill remaining
        self.df[numeric_cols] = self.df[numeric_cols].fillna(method='bfill')
        
        # Strategy 3: Fill remaining with 0
        self.df = self.df.fillna(0)
        
        missing_after = self.df.isnull().sum().sum()
        
        self.cleaning_log.append(f"Filled {missing_before - missing_after:,} missing values")
        print(f"  ✓ Filled {missing_before - missing_after:,} missing values")
    
    def clip_outliers(self):
        """Clip outliers to physical limits."""
        print("\n  Clipping outliers to physical limits...")
        
        limits = {
            'LIT_101': (0, 1200),
            'LIT_301': (0, 1200),
            'LIT_401': (0, 1200),
            'AIT_202': (0, 1400),  # pH 0-14
            'DPIT_301': (0, 1000),  # TMP
            'PIT_501': (0, 2500),  # RO pressure
        }
        
        clipped_count = 0
        for col, (min_val, max_val) in limits.items():
            if col in self.df.columns:
                before = ((self.df[col] < min_val) | (self.df[col] > max_val)).sum()
                self.df[col] = self.df[col].clip(min_val, max_val)
                clipped_count += before
        
        if clipped_count > 0:
            self.cleaning_log.append(f"Clipped {clipped_count:,} outliers")
            print(f"  ✓ Clipped {clipped_count:,} outliers")
        else:
            print("  ✓ No outliers to clip")
    
    def sort_by_time(self):
        """Sort by timestamp."""
        if 'Timestamp' in self.df.columns:
            self.df = self.df.sort_values('Timestamp').reset_index(drop=True)
            self.cleaning_log.append("Sorted by timestamp")
            print("  ✓ Sorted by timestamp")


# ═══════════════════════════════════════════════════════════════════════════
# 5. VISUALIZATION
# ═══════════════════════════════════════════════════════════════════════════

class DataVisualizer:
    """Comprehensive visualization suite."""
    
    def __init__(self, df, output_dir='analysis_output'):
        self.df = df
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
    
    def visualize_all(self):
        """Generate all visualizations."""
        print("\n" + "="*70)
        print("STEP 5: VISUALIZATION")
        print("="*70)
        
        print("\nGenerating plots...")
        
        self.plot_attack_distribution()
        self.plot_sensor_timeseries()
        self.plot_correlation_matrix()
        self.plot_attack_signatures()
        self.plot_distribution_comparison()
        
        print(f"\n✓ All plots saved to: {self.output_dir}/")
    
    def plot_attack_distribution(self):
        """Attack distribution pie chart."""
        if 'ATTACK_ID' not in self.df.columns:
            return
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        
        # Pie chart: Normal vs Attack
        counts = [
            (self.df['ATTACK_ID'] == 0).sum(),
            (self.df['ATTACK_ID'] > 0).sum()
        ]
        labels = ['Normal', 'Attack']
        colors = ['#2ecc71', '#e74c3c']
        
        ax1.pie(counts, labels=labels, autopct='%1.1f%%', colors=colors, startangle=90)
        ax1.set_title('Normal vs Attack Distribution', fontsize=14, fontweight='bold')
        
        # Bar chart: Per attack type
        attack_counts = self.df[self.df['ATTACK_ID'] > 0].groupby(['ATTACK_ID', 'ATTACK_NAME']).size()
        
        if len(attack_counts) > 0:
            attack_names = [name[:25] for (_, name) in attack_counts.index]
            ax2.barh(attack_names, attack_counts.values, color='#3498db')
            ax2.set_xlabel('Count', fontsize=12)
            ax2.set_title('Attack Type Distribution', fontsize=14, fontweight='bold')
            ax2.grid(axis='x', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'attack_distribution.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print("  ✓ attack_distribution.png")
    
    def plot_sensor_timeseries(self):
        """Time series plots for key sensors."""
        if 'Timestamp' not in self.df.columns:
            return
        
        key_sensors = ['AIT_202', 'LIT_101', 'DPIT_301', 'PIT_501']
        key_sensors = [s for s in key_sensors if s in self.df.columns]
        
        if len(key_sensors) == 0:
            return
        
        fig, axes = plt.subplots(len(key_sensors), 1, figsize=(14, 3*len(key_sensors)))
        
        if len(key_sensors) == 1:
            axes = [axes]
        
        for ax, sensor in zip(axes, key_sensors):
            # Plot sensor values
            ax.plot(self.df['Timestamp'], self.df[sensor], linewidth=0.5, alpha=0.7)
            
            # Highlight attacks
            if 'ATTACK_ID' in self.df.columns:
                attack_mask = self.df['ATTACK_ID'] > 0
                ax.scatter(self.df.loc[attack_mask, 'Timestamp'], 
                          self.df.loc[attack_mask, sensor],
                          c='red', s=1, alpha=0.5, label='Attack')
            
            ax.set_ylabel(sensor, fontsize=12)
            ax.grid(alpha=0.3)
            ax.legend()
        
        axes[-1].set_xlabel('Time', fontsize=12)
        axes[0].set_title('Key Sensor Time Series', fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'sensor_timeseries.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print("  ✓ sensor_timeseries.png")
    
    def plot_correlation_matrix(self):
        """Correlation heatmap."""
        key_sensors = ['AIT_202', 'LIT_101', 'DPIT_301', 'PIT_501', 
                      'FIT_101', 'FIT_301', 'FIT_501']
        key_sensors = [s for s in key_sensors if s in self.df.columns]
        
        if len(key_sensors) < 2:
            return
        
        corr = self.df[key_sensors].corr()
        
        fig, ax = plt.subplots(figsize=(10, 8))
        sns.heatmap(corr, annot=True, fmt='.2f', cmap='coolwarm', center=0,
                   square=True, linewidths=1, cbar_kws={"shrink": 0.8})
        ax.set_title('Sensor Correlation Matrix', fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'correlation_matrix.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print("  ✓ correlation_matrix.png")
    
    def plot_attack_signatures(self):
        """Attack signatures visualization."""
        if 'ATTACK_ID' not in self.df.columns or 'AIT_202' not in self.df.columns:
            return
        
        # Focus on pH manipulation attack (ID=11)
        attack_11 = self.df[self.df['ATTACK_ID'] == 11].copy()
        
        if len(attack_11) < 10:
            return
        
        # Reset time to relative
        attack_11['relative_time'] = range(len(attack_11))
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Plot pH trajectory
        ax.plot(attack_11['relative_time'], attack_11['AIT_202'] / 100, 
               linewidth=2, label='pH', color='#e74c3c')
        
        # Add fitted exponential (if enough points)
        if len(attack_11) > 30:
            from scipy.optimize import curve_fit
            
            def exp_func(t, start, target, tau):
                return target + (start - target) * np.exp(-t / tau)
            
            try:
                t = attack_11['relative_time'].values
                pH = (attack_11['AIT_202'] / 100).values
                
                popt, _ = curve_fit(exp_func, t, pH, p0=[pH[0], pH[-1], 40])
                
                pH_fit = exp_func(t, *popt)
                ax.plot(t, pH_fit, '--', linewidth=2, label=f'Exponential fit (τ={popt[2]:.1f}s)', 
                       color='#3498db')
            except:
                pass
        
        ax.set_xlabel('Time (seconds)', fontsize=12)
        ax.set_ylabel('pH', fontsize=12)
        ax.set_title('pH Manipulation Attack Signature', fontsize=14, fontweight='bold')
        ax.grid(alpha=0.3)
        ax.legend()
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'attack_signature_pH.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print("  ✓ attack_signature_pH.png")
    
    def plot_distribution_comparison(self):
        """Distribution comparison: Normal vs Attack."""
        key_sensors = ['AIT_202', 'LIT_101', 'DPIT_301']
        key_sensors = [s for s in key_sensors if s in self.df.columns]
        
        if 'ATTACK_ID' not in self.df.columns or len(key_sensors) == 0:
            return
        
        fig, axes = plt.subplots(1, len(key_sensors), figsize=(5*len(key_sensors), 4))
        
        if len(key_sensors) == 1:
            axes = [axes]
        
        normal_data = self.df[self.df['ATTACK_ID'] == 0]
        attack_data = self.df[self.df['ATTACK_ID'] > 0]
        
        for ax, sensor in zip(axes, key_sensors):
            ax.hist(normal_data[sensor], bins=50, alpha=0.6, label='Normal', color='#2ecc71')
            ax.hist(attack_data[sensor], bins=50, alpha=0.6, label='Attack', color='#e74c3c')
            
            ax.set_xlabel(sensor, fontsize=12)
            ax.set_ylabel('Frequency', fontsize=12)
            ax.legend()
            ax.grid(alpha=0.3)
        
        fig.suptitle('Value Distribution: Normal vs Attack', fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'distribution_comparison.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print("  ✓ distribution_comparison.png")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """Main analysis pipeline."""
    print("\n" + "="*70)
    print("SWAT DATASET COMPREHENSIVE ANALYSIS")
    print("="*70)
    print(f"Started: {datetime.now()}")
    
    # Find dataset
    possible_paths = [
        # 'dataset/master_dataset.csv',
        # 'automated_dataset/master_dataset.csv',
        # 'complete_dataset/master_dataset.csv',
        # 'test_dataset/master_dataset.csv',
        # 'master_dataset.csv',
        'final.csv'
    ]
    
    csv_path = None
    for path in possible_paths:
        if Path(path).exists():
            csv_path = path
            break
    
    if not csv_path:
        print("\n❌ No dataset found. Please provide path:")
        print("   python analyze_dataset.py --csv path/to/master_dataset.csv")
        return
    
    try:
        # 1. Load & Validate
        validator = SWATDataValidator(csv_path)
        df = validator.load() \
                     .validate_structure() \
                     .validate_data_types() \
                     .validate_missing_data() \
                     .validate_duplicates() \
                     .validate_temporal_consistency() \
                     .print_summary()
        
        # 2. Statistical Analysis
        analyzer = ColumnAnalyzer(df)
        stats = analyzer.analyze_all()
        
        # Print a few key columns
        for col in ['AIT_202', 'LIT_101', 'DPIT_301', 'ATTACK_ID']:
            if col in stats:
                analyzer.print_summary(col)
        
        # 3. Attack Analysis
        attack_analyzer = AttackPatternAnalyzer(df)
        attack_analyzer.analyze()
        
        # 4. Data Cleaning
        cleaner = DataCleaner(df)
        df_clean = cleaner.clean()
        
        # Save cleaned data
        output_path = Path(csv_path).parent / 'master_dataset_cleaned.csv'
        df_clean.to_csv(output_path, index=False)
        print(f"\n✓ Cleaned dataset saved: {output_path}")
        
        # 5. Visualization
        visualizer = DataVisualizer(df_clean)
        visualizer.visualize_all()
        
        # Final summary
        print("\n" + "="*70)
        print("ANALYSIS COMPLETE")
        print("="*70)
        print(f"Completed: {datetime.now()}")
        print(f"\nOutputs:")
        print(f"  Cleaned CSV: {output_path}")
        print(f"  Plots: analysis_output/")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--csv':
        csv_path = sys.argv[2]
        # Override default path
        main()
    else:
        main()