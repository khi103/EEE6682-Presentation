#!/usr/bin/env python3
"""Characterize robustness of the independent 450-MHz reference MOS PLL.

This is a *diagnostic sweep*, not a claim of universal PLL lock:
- Actual XSPICE PFD /4, MOS switched charge pump, passive loop filter and
  DB HiTek 180-nm MOS VCO share one ngspice transient deck.
- Compare different PDK corners, startup biases and reference frequencies.
- Require output-frequency tracking, low reference-edge phase variation and
  low filtered VCO-control ripple simultaneously.
- Record failed/non-converged cases without suppressing negative evidence.

The original Wong et al. Fig. 18-20 circuit, real-data CDR, jitter and
foundry HSPICE correlation are NOT reproduced by this experiment.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

import p3_transistor_driver as TX
import p3_xspice_physical_mos_pll as PLL

# Nominal is an independent rerun of the previously qualified 450-MHz case.
CASES = (
    ("tt_baseline", "tt", 0.96, 450.0, 63),
    ("tt_bias_low", "tt", 0.86, 450.0, 63),
    ("tt_bias_high", "tt", 1.06, 450.0, 63),
    ("ff_baseline_bias", "ff", 0.96, 450.0, 63),
    ("ss_baseline_bias", "ss", 0.96, 450.0, 63),
    ("tt_reference_449MHz", "tt", 0.96, 449.0, 63),
    ("tt_reference_451MHz", "tt", 0.96, 451.0, 63),
)

def window_frequency(rows, key, first_ns, last_ns):
    times = [t for t in PLL.rising(rows, key, start_ns=first_ns)
             if t <= last_ns * 1e-9]
    if len(times) < 5:
        return None
    avg_period = (times[-1] - times[0]) / (len(times) - 1)
    if avg_period <= 0:
        return None
    return 1.0 / avg_period / 1e9

def diagnostics(rows, reference_mhz):
    m = PLL.metrics(rows)
    m.update(PLL.aligned_phase_errors_ps(rows))
    target_ghz = 4.0 * reference_mhz / 1000.0
    measured = m.get("vco_GHz")
    m["nominal_target_GHz"] = target_ghz
    m["reference_requested_MHz"] = reference_mhz
    m["frequency_error_ppm"] = (
        1e6 * (measured / target_ghz - 1.0)
        if measured is not None else None
    )
    m["frequency_by_window_GHz"] = {
        "700_to_780_ns": window_frequency(rows, "vco_V", 700, 780),
        "900_to_980_ns": window_frequency(rows, "vco_V", 900, 980),
        "1120_to_1200_ns": window_frequency(rows, "vco_V", 1120, 1200),
    }
    # These are defined electrical-screening criteria, not chip BER/jitter specs.
    m["meets_reference_PLL_screen"] = bool(
        m["frequency_error_ppm"] is not None
        and abs(m["frequency_error_ppm"]) < 1500.0
        and m.get("std_phase_ps") is not None
        and m["std_phase_ps"] < 8.0
        and m.get("physical_vco_gate_ripple_mV") is not None
        and m["physical_vco_gate_ripple_mV"] < 5.0
        and m.get("n_reference_edges", 0) >= 25
    )
    return m

def save_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def run(out):
    out.mkdir(parents=True, exist_ok=True)
    work = TX.ENGINE_DIR / "p3_xspice_pll_robustness"
    runner = TX.SpiceRunner(work)
    for corner in sorted({c[1] for c in CASES}):
        source = TX.model_path(corner)
        dest = work / source.name
        if not dest.exists() or source.stat().st_mtime > dest.stat().st_mtime:
            shutil.copy2(source, dest)

    original_period = PLL.REF_PERIOD_PS
    results = {}
    for label, corner, bias, reference_mhz, code in CASES:
        PLL.REF_PERIOD_PS = 1e12 / (reference_mhz * 1e6)
        try:
            runner.run(
                PLL.circuit(code, corner=corner, initial_bias=bias), label
            )
            rows = PLL.read(work / "physical_pll.csv")
            m = diagnostics(rows, reference_mhz)
            m.update({
                "status": "simulated",
                "corner": corner,
                "start_bias_V": bias,
                "7bit_pump_code": code,
            })
            results[label] = m
            print(
                f"PLL_ROBUSTNESS {label}: "
                f"f={m.get('vco_GHz')} GHz "
                f"error={m.get('frequency_error_ppm')} ppm "
                f"phase_std={m.get('std_phase_ps')} ps "
                f"gate_ripple={m.get('physical_vco_gate_ripple_mV')} mV "
                f"qualified={m['meets_reference_PLL_screen']}",
                flush=True,
            )
            if label in ("tt_baseline", "ff_baseline_bias", "ss_baseline_bias"):
                stride = max(1, len(rows) // 6000)
                save_csv(out / f"{label}_decimated_waveform.csv", rows[::stride])
            del rows
        except Exception as exc:
            results[label] = {
                "status": "simulation_failed",
                "corner": corner,
                "start_bias_V": bias,
                "reference_requested_MHz": reference_mhz,
                "7bit_pump_code": code,
                "meets_reference_PLL_screen": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
            print(f"PLL_ROBUSTNESS {label}: SIMULATION_FAILED {exc}", flush=True)
        finally:
            PLL.REF_PERIOD_PS = original_period

    qualified = [name for name, r in results.items()
                 if r["meets_reference_PLL_screen"]]
    summary = {
        "experiment": "450-MHz-reference physical MOS PLL robustness sweep",
        "physical": "DB HiTek 180nm NMOS/PMOS charge pump, ring VCO and loop capacitors",
        "mixed_signal": "XSPICE digital PFD, divider and analog/digital bridges",
        "sweep": "PVT TT/FF/SS, +/-0.10 V startup bias, 449/450/451-MHz reference",
        "note": "A lock-screen pass is not proof of measured phase noise, full CDR, or original ASIC equivalence",
        "screen": {
            "frequency_error_absolute_lt_ppm": 1500.0,
            "phase_standard_deviation_lt_ps": 8.0,
            "physical_VCO_gate_ripple_lt_mV": 5.0,
            "minimum_reference_edges": 25,
        },
        "tests_attempted": len(CASES),
        "tests_simulated": sum(r["status"] == "simulated" for r in results.values()),
        "tests_screen_passed": len(qualified),
        "qualified_cases": qualified,
        "results": results,
        "physical_data_CDR_verified": False,
        "original_paper_PLL_reconstructed": False,
    }
    (out / "xspice_pll_robustness_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        f"PLL_ROBUSTNESS_SUMMARY: qualified={len(qualified)}/{len(CASES)}; "
        f"nominal_tt={'tt_baseline' in qualified}",
        flush=True,
    )
    # Do not declare CI success for a broken nominal model. All other failure
    # results are purposefully captured as limits, not hidden or tuned away.
    if "tt_baseline" not in qualified:
        raise AssertionError("Previously qualified TT nominal reference PLL no longer passes")
    return summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", type=Path,
        default=Path("results/spice/p3_xspice_pll_robustness"),
    )
    run(parser.parse_args().out)
