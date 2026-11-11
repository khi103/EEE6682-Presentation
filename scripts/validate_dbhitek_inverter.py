#!/usr/bin/env python3
"""Validate the actual ngspice 1.8-V CMOS inverter smoke-test waveform.

This is a minimal physical plausibility check, NOT foundry model validation,
HSPICE numeric correlation, or P3 TX-driver verification.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path


def read_ngspice_wrdata(path: Path):
    """ngspice wrdata can repeat x-axis columns per saved vector."""
    rows = []
    for line_number, raw in enumerate(path.read_text().splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith(("#", "*")):
            continue
        try:
            a = [float(x) for x in raw.split()]
        except ValueError as e:
            raise ValueError(f"Invalid numeric row {line_number}: {raw[:60]}") from e
        if len(a) < 3 or not all(math.isfinite(x) for x in a):
            raise ValueError(f"Invalid data row {line_number}, columns={len(a)}")
        # Last data value is V(out). In a repeated-scale file, the next-to-last
        # data value is V(in), at index -3. For a 3-column file it is index 1.
        t = a[0]
        vin = a[-3] if len(a) >= 4 else a[1]
        vout = a[-1]
        rows.append((t, vin, vout))
    return rows


def verify(path: Path):
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Transient output missing or empty: {path}")
    rows = read_ngspice_wrdata(path)
    if len(rows) < 500:
        raise ValueError(f"Expected dense transient output, got only {len(rows)} rows")
    times, vin, vout = map(list, zip(*rows))
    if times[-1] - times[0] < 7.5e-9:
        raise ValueError("Transient analysis did not span the expected 8-ns window")
    if any(y < x for x, y in zip(times, times[1:])):
        raise ValueError("Time column is not nondecreasing")
    vmin, vmax = min(vout), max(vout)
    if not (vmin < 0.30 and vmax > 1.50):
        raise ValueError(f"Inverter did not swing approximately 0 to 1.8 V: [{vmin}, {vmax}]")
    high_inputs = [vo for vi, vo in zip(vin, vout) if vi > 1.70]
    low_inputs = [vo for vi, vo in zip(vin, vout) if vi < 0.10]
    if len(high_inputs) < 20 or len(low_inputs) < 20:
        raise ValueError("The test did not exercise both logic input states")
    hi_logic_out = statistics.median(low_inputs)
    lo_logic_out = statistics.median(high_inputs)
    if not (hi_logic_out > 1.50 and lo_logic_out < 0.30):
        raise ValueError(
            f"Logic inversion test failed: Vout|VinLow={hi_logic_out:.3f} V, "
            f"Vout|VinHigh={lo_logic_out:.3f} V"
        )
    metrics = {
        "status": "passed_basic_inverter_transient_checks",
        "data_rows": len(rows),
        "time_start_ns": times[0] * 1e9,
        "time_end_ns": times[-1] * 1e9,
        "input_min_V": min(vin), "input_max_V": max(vin),
        "output_min_V": vmin, "output_max_V": vmax,
        "output_median_when_input_low_V": hi_logic_out,
        "output_median_when_input_high_V": lo_logic_out,
        "limitations": [
            "HSPICE-only model parameters ignored in ngspice need numerical correlation",
            "No P3 segmented driver, impedance, power or PVT verified",
            "DTEMP forwarding removed only in local zero-DTEMP model copy"
        ],
    }
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--file", type=Path,
        default=Path("pdk_private/ngspice_compat/inverter_transient.csv"),
    )
    parser.add_argument(
        "--out", type=Path,
        default=Path("pdk_private/ngspice_compat/smoke_metrics.json"),
    )
    args = parser.parse_args()
    metrics = verify(args.file)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(metrics, indent=2) + "\n")
    print("PASS: Basic DB HiTek CMOS inverter transient plausibility")
    print(json.dumps(metrics, indent=2))
