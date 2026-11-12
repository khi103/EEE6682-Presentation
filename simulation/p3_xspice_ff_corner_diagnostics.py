#!/usr/bin/env python3
"""Independent FF-corner failure analysis of the DB HiTek MOS reference PLL.

Explicit negative-evidence sweep of the XSPICE PFD/4, MOS switched charge
pump, loop filter, and MOS ring VCO. All tested changes are hypothetical
reconstructed-design parameters, not the original 2004 P3 sizing.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from pathlib import Path

import p3_transistor_driver as TX
import p3_xspice_physical_mos_pll as PLL

# label, total simulation time in ns, circuit text substitution, MOS pump scale
CASES = (
    ("ff_nominal_1200ns", 1200., None, 1.0),
    ("ff_nominal_2000ns", 2000., None, 1.0),
    ("ff_Rzero_4kohm", 1200., ("RZERO loopctrl lpcap 2k", "RZERO loopctrl lpcap 4k"), 1.0),
    ("ff_Cpost_20pF", 1200., ("CPOST vcobias 0 8p", "CPOST vcobias 0 20p"), 1.0),
    ("ff_Cfast_20pF", 1200., ("CFAST loopctrl 0 5p", "CFAST loopctrl 0 20p"), 1.0),
    ("ff_CP_75pct", 1200., None, 0.75),
    ("ff_CP_125pct", 1200., None, 1.25),
)
FREQ_TOL_PPM = 1500.
PHASE_STD_TOL_PS = 8.
VCO_RIPPLE_TOL_MV = 5.

def characterize(rows):
    m = PLL.metrics(rows)
    m.update(PLL.aligned_phase_errors_ps(rows, start_ns=PLL.TIME_NS-80))
    vco = m.get("vco_GHz")
    m["freq_error_ppm"] = 1e6 * (vco / 1.8 - 1) if vco else None
    m["passes_frequency"] = bool(m["freq_error_ppm"] is not None and
                                 abs(m["freq_error_ppm"]) < FREQ_TOL_PPM)
    m["passes_reference_phase_stability"] = bool(
        m.get("std_phase_ps") is not None and
        m["std_phase_ps"] < PHASE_STD_TOL_PS and
        m.get("n_reference_edges", 0) >= 25)
    m["passes_control_ripple"] = bool(
        m.get("physical_vco_gate_ripple_mV") is not None and
        m["physical_vco_gate_ripple_mV"] < VCO_RIPPLE_TOL_MV)
    m["qualifies"] = (m["passes_frequency"] and
                      m["passes_reference_phase_stability"] and
                      m["passes_control_ripple"])
    return m

def run(out):
    out.mkdir(parents=True, exist_ok=True)
    working = TX.ENGINE_DIR / "p3_xspice_FF_diagnosis"
    runner = TX.SpiceRunner(working)
    source = TX.model_path("ff")
    dest = working / source.name
    if not dest.exists() or source.stat().st_mtime > dest.stat().st_mtime:
        shutil.copy2(source, dest)

    t0, up0, down0 = PLL.TIME_NS, PLL.I_SOURCE_W_UM, PLL.I_SINK_W_UM
    results = {}
    for label, total_ns, patch, pump_scale in CASES:
        PLL.TIME_NS = total_ns
        PLL.I_SOURCE_W_UM = up0 * pump_scale
        PLL.I_SINK_W_UM = down0 * pump_scale
        try:
            deck = PLL.circuit(63, corner="ff", initial_bias=0.96)
            if patch:
                old, new = patch
                if deck.count(old) != 1:
                    raise RuntimeError(f"Cannot uniquely replace {old}")
                deck = deck.replace(old, new)
            runner.run(deck, label)
            wave = PLL.read(working / "physical_pll.csv")
            m = characterize(wave)
            m.update({
                "status": "simulated", "corner": "ff",
                "sim_duration_ns": total_ns,
                "filter_patch": patch,
                "pump_width_scale": pump_scale,
            })
            results[label] = m
            if label in ("ff_nominal_1200ns", "ff_nominal_2000ns"):
                with (out / f"{label}_waveform.csv").open("w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=list(wave[0]))
                    w.writeheader()
                    w.writerows(wave[::max(1, len(wave) // 4000)])
            print(
                f"FF_DIAG {label} freq={m['vco_GHz']} GHz "
                f"freq_ppm={m['freq_error_ppm']} "
                f"phase_std_ps={m.get('std_phase_ps')} "
                f"Vgate_ripple_mV={m.get('physical_vco_gate_ripple_mV')} "
                f"full_lock_screen={m['qualifies']}",
                flush=True,
            )
            del wave
        except Exception as exc:
            results[label] = {
                "status": "simulator_failed", "sim_duration_ns": total_ns,
                "filter_patch": patch,
                "pump_width_scale": pump_scale, "qualifies": False,
                "exception": f"{type(exc).__name__}: {exc}",
            }
            print(f"FF_DIAG {label} FAILED {exc}", flush=True)
        finally:
            PLL.TIME_NS, PLL.I_SOURCE_W_UM, PLL.I_SINK_W_UM = (
                t0, up0, down0)

    qualified = [k for k, value in results.items() if value["qualifies"]]
    summary = {
        "study": "Independently reconstructed 450MHz-reference MOS PLL FF corner",
        "device_corner": "DB HiTek 180nm SVT FF, 27 C",
        "screen": {"frequency_error_abs_lt_ppm": FREQ_TOL_PPM,
                   "reference_phase_std_lt_ps": PHASE_STD_TOL_PS,
                   "physical_gate_ripple_lt_mV": VCO_RIPPLE_TOL_MV},
        "all_cases": results,
        "tested": len(CASES),
        "qualified_cases": qualified,
        "qualified_count": len(qualified),
        "not_original_paper_sizing": True,
        "not_data_CDR": True,
        "not_HSPICE_correlated": True,
    }
    (out / "ff_corner_diagnostic.json").write_text(
        json.dumps(summary, indent=2) + "\n")
    print(f"FF_DIAG_TOTAL qualified={len(qualified)}/{len(CASES)}", flush=True)
    return summary

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path,
      default=Path("results/spice/p3_xspice_pll_ff_corner"))
    run(p.parse_args().out)
