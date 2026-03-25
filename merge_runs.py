"""
SWaT Multi-Run Dataset Merge Pipeline
======================================
Usage:
    python merge_runs.py --runs run_01/master_dataset.csv run_02/master_dataset.csv run_03/master_dataset.csv ...
    python merge_runs.py --dir ./runs/               # auto-discovers all master_dataset.csv files
    python merge_runs.py --runs r1.csv r2.csv --output merged_dataset.csv

What this script does:
  1. Loads each run, assigns run_id + elapsed_seconds
  2. Validates schema consistency across runs
  3. Reports per-run attack coverage
  4. Checks normal-state baseline drift between runs
  5. Identifies dead columns globally (zero variance across ALL runs combined)
  6. Removes label-boundary leakage rows (±2s around attack transitions)
  7. Drops dead columns, normalises bool dtypes
  8. Concatenates and outputs clean merged CSV + validation report
"""

import argparse
import glob
import os
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

# ── Known attack registry ────────────────────────────────────────────────────
ATTACK_REGISTRY = {
    0:  "Normal",
    8:  "Tank Overflow Attack",
    9:  "Chemical Depletion Attack",
    10: "Membrane Damage Attack",
    11: "pH Manipulation Attack",
    12: "Slow Ramp Attack",
    13: "Reconnaissance Scan",
    14: "Denial of Service",
    15: "Replay Attack",
    16: "Valve Manipulation Attack",
}

# Sensors expected to carry real signal (used for baseline drift check)
BASELINE_SENSORS = [
    'LIT_101', 'LIT_301', 'LIT_401',
    'Acid_Tank_Level', 'Chlorine_Tank_Level', 'Coagulant_Tank_Level',
    'Chlorine_Residual', 'AIT_202', 'FIT_101', 'FIT_201',
]

# ── Helpers ──────────────────────────────────────────────────────────────────
def load_run(path: str, run_id: int) -> pd.DataFrame:
    """Load a single run CSV, parse timestamps safely, add run_id + elapsed_seconds."""
    print(f"  Loading run_{run_id:02d}: {path}")
    df = pd.read_csv(path)

    # ✅ FIXED TIMESTAMP PARSING (handles mixed formats)
    df['Timestamp'] = pd.to_datetime(
        df['Timestamp'],
        format='ISO8601',
        errors='coerce'
    )

    # Drop bad timestamps
    bad_ts = df['Timestamp'].isna().sum()
    if bad_ts > 0:
        print(f"    ⚠ Dropping {bad_ts} rows with invalid timestamps")
        df = df.dropna(subset=['Timestamp'])

    df = df.sort_values('Timestamp').reset_index(drop=True)

    # elapsed_seconds from this run's start
    t0 = df['Timestamp'].iloc[0]
    df['elapsed_seconds'] = (df['Timestamp'] - t0).dt.total_seconds().round(3)

    # run_id
    df['run_id'] = run_id

    # Fix bool columns
    bool_candidates = df.select_dtypes(include=['object', 'int64']).columns
    for c in bool_candidates:
        unique_vals = set(df[c].dropna().unique())
        if unique_vals <= {True, False, 'True', 'False', 1, 0, '1', '0'}:
            df[c] = df[c].map(
                {True: True, False: False, 'True': True, 'False': False,
                 1: True, 0: False, '1': True, '0': False}
            ).astype(bool)

    return df

def check_schema(dfs: list[pd.DataFrame], run_ids: list[int]) -> list[str]:
    """Verify all runs have consistent column sets. Returns list of warnings."""
    warnings = []
    ref_cols = set(dfs[0].columns) - {'run_id', 'elapsed_seconds'}
    for i, df in enumerate(dfs[1:], start=1):
        cur_cols = set(df.columns) - {'run_id', 'elapsed_seconds'}
        extra   = cur_cols - ref_cols
        missing = ref_cols - cur_cols
        if extra:
            warnings.append(f"run_{run_ids[i]:02d} has extra columns: {sorted(extra)}")
        if missing:
            warnings.append(f"run_{run_ids[i]:02d} missing columns: {sorted(missing)}")
    return warnings


def attack_coverage(dfs: list[pd.DataFrame], run_ids: list[int]) -> pd.DataFrame:
    """Build attack coverage matrix: rows=attacks, cols=runs."""
    all_ids = sorted(set().union(*[set(df['ATTACK_ID'].unique()) for df in dfs]))
    rows = []
    for aid in all_ids:
        row = {'ATTACK_ID': aid, 'ATTACK_NAME': ATTACK_REGISTRY.get(aid, f"Unknown_{aid}")}
        for df, rid in zip(dfs, run_ids):
            sub = df[df['ATTACK_ID'] == aid]
            row[f'run_{rid:02d}'] = len(sub) if len(sub) > 0 else 0
        rows.append(row)
    return pd.DataFrame(rows)


def baseline_drift(dfs: list[pd.DataFrame], run_ids: list[int]) -> pd.DataFrame:
    """Compare normal-state sensor means across runs to detect drift."""
    rows = []
    sensors = [c for c in BASELINE_SENSORS if all(c in df.columns for df in dfs)]
    for c in sensors:
        row = {'sensor': c}
        means = []
        for df, rid in zip(dfs, run_ids):
            normal = df[df['ATTACK_ID'] == 0][c]
            if normal.std() == 0:
                row[f'run_{rid:02d}_mean'] = f"{normal.iloc[0]:.3f} (FLAT)"
            else:
                m = normal.mean()
                row[f'run_{rid:02d}_mean'] = round(m, 3)
                means.append(m)
        if len(means) > 1:
            row['max_drift'] = round(max(means) - min(means), 3)
            row['drift_flag'] = '!! WARN' if row['max_drift'] > (
                dfs[0][dfs[0]['ATTACK_ID']==0][c].std() * 0.5
            ) else 'OK'
        rows.append(row)
    return pd.DataFrame(rows)


def find_dead_columns(df_combined: pd.DataFrame) -> list[str]:
    """Find columns with zero variance across the ENTIRE merged dataset."""
    drop = []
    skip = {'Timestamp', 'run_id', 'elapsed_seconds', 'ATTACK_ID', 'ATTACK_NAME', 'MITRE_ID'}
    for c in df_combined.columns:
        if c in skip:
            continue
        try:
            if df_combined[c].nunique() <= 1:
                drop.append(c)
        except Exception:
            pass
    return drop


def remove_boundary_leakage(df: pd.DataFrame, window_s: float = 2.0) -> pd.DataFrame:
    """
    Drop rows within ±window_s seconds of any ATTACK_ID transition.
    This removes label leakage where sensor state hasn't caught up to label.
    Applied per run (uses elapsed_seconds).
    """
    runs = []
    for rid, grp in df.groupby('run_id'):
        grp = grp.sort_values('elapsed_seconds').reset_index(drop=True)
        transitions = grp['ATTACK_ID'].diff().abs() > 0
        transition_times = grp.loc[transitions, 'elapsed_seconds'].values

        mask = pd.Series(False, index=grp.index)
        for t in transition_times:
            mask |= (grp['elapsed_seconds'] - t).abs() <= window_s

        removed = mask.sum()
        grp = grp[~mask].reset_index(drop=True)
        print(f"    run_{rid:02d}: removed {removed} boundary-leakage rows "
              f"({removed/(removed+len(grp))*100:.1f}% of run)")
        runs.append(grp)
    return pd.concat(runs, ignore_index=True)


def per_attack_signal_quality(df: pd.DataFrame) -> pd.DataFrame:
    """Quick signal quality check per attack in merged dataset."""
    key_sensors = ['LIT_101', 'LIT_301', 'LIT_401',
                   'Acid_Tank_Level', 'Chlorine_Tank_Level', 'AIT_202',
                   'FIT_101', 'FIT_401', 'DPIT_301']
    key_sensors = [c for c in key_sensors if c in df.columns and df[c].std() > 0]

    normal = df[df['ATTACK_ID'] == 0]
    rows = []
    for aid, grp in df[df['ATTACK_ID'] > 0].groupby('ATTACK_ID'):
        name = ATTACK_REGISTRY.get(int(aid), f"Unknown_{aid}")
        best_signal = []
        for c in key_sensors:
            diff = abs(grp[c].mean() - normal[c].mean())
            ns = normal[c].std()
            z = diff / ns if ns > 0 else 0
            best_signal.append((c, round(z, 2)))
        best_signal.sort(key=lambda x: -x[1])
        rows.append({
            'ATTACK_ID': int(aid),
            'ATTACK_NAME': name,
            'total_rows': len(grp),
            'runs_present': df[df['ATTACK_ID']==aid]['run_id'].nunique(),
            'top_signal_1': f"{best_signal[0][0]} (z={best_signal[0][1]})" if len(best_signal)>0 else "-",
            'top_signal_2': f"{best_signal[1][0]} (z={best_signal[1][1]})" if len(best_signal)>1 else "-",
            'invisible': '!! YES' if best_signal[0][1] < 0.5 else 'NO',
        })
    return pd.DataFrame(rows)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Merge SWaT run CSVs into one ML-ready dataset")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument('--runs', nargs='+', help='Paths to individual run CSVs in order')
    grp.add_argument('--dir',  type=str,   help='Directory to auto-discover master_dataset.csv files')
    parser.add_argument('--output',         default='merged_dataset.csv',  help='Output CSV path')
    parser.add_argument('--report',         default='merge_report.txt',    help='Validation report path')
    parser.add_argument('--boundary-window', type=float, default=2.0,
                        help='Seconds to exclude around attack transitions (default 2.0)')
    parser.add_argument('--keep-dead',      action='store_true',
                        help='Keep dead/constant columns (not recommended)')
    parser.add_argument('--no-leakage-fix', action='store_true',
                        help='Skip boundary leakage removal')
    args = parser.parse_args()

    # ── Discover files ────────────────────────────────────────────────────
    if args.dir:
        paths = sorted(glob.glob(os.path.join(args.dir, '**/master_dataset.csv'), recursive=True))
        if not paths:
            paths = sorted(glob.glob(os.path.join(args.dir, '*.csv')))
        print(f"Found {len(paths)} CSV files in {args.dir}")
    else:
        paths = args.runs

    if len(paths) < 2:
        print("ERROR: Need at least 2 run files to merge.")
        sys.exit(1)

    run_ids = list(range(1, len(paths) + 1))
    report_lines = [
        "=" * 70,
        "SWaT DATASET MERGE REPORT",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Runs merged: {len(paths)}",
        "=" * 70, ""
    ]

    # ── Load all runs ─────────────────────────────────────────────────────
    print("\n[1/7] Loading runs...")
    dfs = []
    for i, (path, rid) in enumerate(zip(paths, run_ids)):
        df = load_run(path, rid)
        dt = df['Timestamp'].diff().dt.total_seconds().dropna()
        print(f"       → {len(df):,} rows  |  {df['elapsed_seconds'].max()/60:.1f}min  "
              f"|  poll={dt.mean():.3f}s  |  attacks={sorted(df['ATTACK_ID'].unique())}")
        dfs.append(df)

    # ── Schema check ─────────────────────────────────────────────────────
    print("\n[2/7] Checking schema consistency...")
    schema_warns = check_schema(dfs, run_ids)
    if schema_warns:
        for w in schema_warns: print(f"  ⚠  {w}")
        report_lines += ["SCHEMA WARNINGS:"] + [f"  {w}" for w in schema_warns] + [""]
    else:
        print("  ✓  All runs have consistent columns")
        report_lines += ["SCHEMA: All runs consistent\n"]

    # Align columns — use union, fill missing with NaN
    all_cols = list(dict.fromkeys(
        col for df in dfs for col in df.columns
    ))
    dfs = [df.reindex(columns=all_cols) for df in dfs]

    # ── Attack coverage ───────────────────────────────────────────────────
    print("\n[3/7] Attack coverage matrix...")
    cov = attack_coverage(dfs, run_ids)
    print(cov.to_string(index=False))
    report_lines += ["ATTACK COVERAGE:"]
    report_lines += [cov.to_string(index=False), ""]

    # ── Baseline drift ────────────────────────────────────────────────────
    print("\n[4/7] Normal-state baseline drift check...")
    drift = baseline_drift(dfs, run_ids)
    print(drift.to_string(index=False))
    report_lines += ["NORMAL-STATE BASELINE DRIFT:"]
    report_lines += [drift.to_string(index=False), ""]

    # ── Concatenate ───────────────────────────────────────────────────────
    print("\n[5/7] Concatenating runs...")
    combined = pd.concat(dfs, ignore_index=True)
    print(f"  Combined shape: {combined.shape}")

    # ── Boundary leakage removal ──────────────────────────────────────────
    if not args.no_leakage_fix:
        print(f"\n[6/7] Removing boundary leakage (±{args.boundary_window}s)...")
        before = len(combined)
        combined = remove_boundary_leakage(combined, window_s=args.boundary_window)
        after = len(combined)
        msg = f"  Removed {before-after:,} leakage rows ({(before-after)/before*100:.2f}% of total)"
        print(msg)
        report_lines += [f"BOUNDARY LEAKAGE REMOVAL: {msg.strip()}\n"]
    else:
        print("\n[6/7] Skipping boundary leakage removal (--no-leakage-fix set)")

    # ── Drop dead columns ─────────────────────────────────────────────────
    print("\n[7/7] Identifying and dropping dead columns...")
    if not args.keep_dead:
        dead = find_dead_columns(combined)
        if dead:
            print(f"  Dropping {len(dead)} zero-variance columns:")
            for c in dead:
                val = combined[c].iloc[0]
                print(f"    {c}: always={val}")
            combined.drop(columns=dead, inplace=True)
            report_lines += [f"DROPPED {len(dead)} DEAD COLUMNS:"]
            report_lines += [f"  {c}" for c in dead] + [""]
        else:
            print("  ✓  No dead columns found")
    else:
        print("  Skipping dead column removal (--keep-dead set)")

    # ── Signal quality summary ────────────────────────────────────────────
    print("\n── Attack signal quality in merged dataset ──")
    quality = per_attack_signal_quality(combined)
    print(quality.to_string(index=False))
    report_lines += ["ATTACK SIGNAL QUALITY (merged):"]
    report_lines += [quality.to_string(index=False), ""]

    # ── Final stats ───────────────────────────────────────────────────────
    n = (combined.ATTACK_ID == 0).sum()
    a = (combined.ATTACK_ID > 0).sum()
    print(f"\n── Final merged dataset ──")
    print(f"  Rows:     {len(combined):,}")
    print(f"  Columns:  {len(combined.columns)}")
    print(f"  Normal:   {n:,} ({n/len(combined)*100:.1f}%)")
    print(f"  Attack:   {a:,} ({a/len(combined)*100:.1f}%)")
    print(f"  Ratio:    {n/a:.2f}:1")
    print(f"  Attacks present: {sorted(combined[combined.ATTACK_ID>0]['ATTACK_ID'].unique())}")
    print(f"  Runs:     {combined['run_id'].nunique()}")
    print(f"  Duration: {combined['elapsed_seconds'].max()/60:.1f} min total across all runs")

    report_lines += [
        "FINAL MERGED DATASET:",
        f"  Rows:    {len(combined):,}",
        f"  Columns: {len(combined.columns)}",
        f"  Normal:  {n:,} ({n/len(combined)*100:.1f}%)",
        f"  Attack:  {a:,} ({a/len(combined)*100:.1f}%)",
        f"  N:A ratio: {n/a:.2f}:1",
        f"  Attack IDs: {sorted(combined[combined.ATTACK_ID>0]['ATTACK_ID'].unique())}",
        ""
    ]

    # ── Save outputs ──────────────────────────────────────────────────────
    combined.to_csv(args.output, index=False)
    print(f"\n✓  Saved merged dataset → {args.output}")

    with open(args.report, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    print(f"✓  Saved validation report → {args.report}")


if __name__ == '__main__':
    main()