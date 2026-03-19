# Custom Attack Command Guide (Your Runs)

This file gives copy-paste commands for your custom dataset runs with mixed network + temporal attacks.

## Important CLI Notes

- Correct script name is `automated_dataset_generator.py`.
- Use `--include-attacks` (not `--include attacks`).
- Attack list must be comma-separated without spaces.

Example format:

```cmd
python automated_dataset_generator.py --host 192.168.0.134 --port 1502 --total 70 --attack 30 --output run_01 --include-attacks reconnaissance,dos_flood,replay,ph_manipulation,tank_overflow,chemical_depletion,membrane_damage,valve_manipulation,slow_ramp
```

## Attack Names You Can Use

Network attacks:
- `reconnaissance`
- `dos_flood`
- `replay`

Temporal attacks:
- `ph_manipulation`
- `tank_overflow`
- `chemical_depletion`
- `membrane_damage`
- `valve_manipulation`
- `slow_ramp`

## Your Requested Custom Combinations

### 1) Full mixed pool: network + temporal (3 + 6), random

```cmd
python automated_dataset_generator.py --host 192.168.0.134 --port 1502 --total 70 --attack 30 --output run_01 --include-attacks reconnaissance,dos_flood,replay,ph_manipulation,tank_overflow,chemical_depletion,membrane_damage,valve_manipulation,slow_ramp
```

### 2) Four-attack pool (2 network + 2 temporal), random

```cmd
python automated_dataset_generator.py --host 192.168.0.134 --port 1502 --total 70 --attack 30 --output run_02_2plus2 --include-attacks reconnaissance,replay,ph_manipulation,slow_ramp
```

Alternative 2+2:

```cmd
python automated_dataset_generator.py --host 192.168.0.134 --port 1502 --total 70 --attack 30 --output run_02b_2plus2 --include-attacks dos_flood,replay,tank_overflow,membrane_damage
```

### 3) Four-attack pool (1 network + 3 temporal), random

```cmd
python automated_dataset_generator.py --host 192.168.0.134 --port 1502 --total 70 --attack 30 --output run_03_1plus3 --include-attacks replay,ph_manipulation,chemical_depletion,valve_manipulation
```

Alternative 1+3:

```cmd
python automated_dataset_generator.py --host 192.168.0.134 --port 1502 --total 70 --attack 30 --output run_03b_1plus3 --include-attacks reconnaissance,tank_overflow,membrane_damage,slow_ramp
```

## Quick Validation After Run

Check generated schedule and outputs:

```cmd
type run_01\attack_timeline.log
type run_01\execution_details.log
```

Check how many attack types appeared:

```cmd
findstr /I "ATTACK START" run_01\execution_details.log
```

## Behavior Note (Important)

`--include-attacks` defines the allowed attack pool.
The scheduler then picks from that pool with random durations and timing.

This means:
- You get random mixed attacks from your selected list.
- Exact count pattern (for example exactly 2+2 occurrences) is not strictly guaranteed in current code.
