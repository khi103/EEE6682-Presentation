#!/usr/bin/env python3
"""Controlled TX-FFE ablation with physically locked reference PLL and MOS RX.

All four tests use the SAME 3.6-Gb/s PRBS7 data, 50-ohm-terminated
two-pole RC surrogate channel, DB HiTek 180-nm MOS TX, RX latches,
physical MOS VCO and MOS switched charge pump. XSPICE PFD locks the
oscillator to an ideal 450-MHz reference, NOT to recovered serial data.

Only TX pre-emphasis alpha changes between runs. All RX observations are
from actual MOS latch outputs at a fixed delay after actual MOS clock
edges; integer frame alignment is used solely for post-run scoring.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from pathlib import Path

import p3_transistor_driver as TX
import p3_reference_pll_integrated_mos_link as LINK

RATES = (0.0, 0.15, 0.30, 0.45)
REGEN_MV = 150.
VREF = 0.25

def pct(sorted_items, fraction):
    if not sorted_items:
        return None
    i = (len(sorted_items)-1)*fraction
    lo, hi = math.floor(i), math.ceil(i)
    return sorted_items[lo]*(hi-i) + sorted_items[hi]*(i-lo) if hi!=lo else sorted_items[lo]

def weighted_supply_power_mw(rows, field, supply):
    if len(rows)<2:
        return None
    charge = sum((b["time_s"]-a["time_s"])*.5*
                 (a[field]+b[field]) for a,b in zip(rows, rows[1:]))
    duration = rows[-1]["time_s"]-rows[0]["time_s"]
    return -charge / duration * supply * 1000. if duration>0 else None

def evaluate_electrical(rows, bits, samples, scoreboard):
    from collections import Counter
    times = [r["time_s"] for r in rows]
    lag = scoreboard["best_integer_frame_alignment_for_postrun_scoring"]
    symbol = Counter(s["estimated_symbol_index"]+lag for s in samples)
    signed_v_margin = []
    diffs = []
    unresolved = wrong_resolved = 0
    for s in samples:
        index = s["estimated_symbol_index"] + lag
        if not 0<=index<len(bits):
            continue
        rx = LINK.interp(rows, s["physical_clock_sample_s"], "rx_V", times)
        signed_v_margin.append((2*bits[index]-1)*(rx-VREF)*1e3)
        diff = abs(s["Q_minus_QB_V"])*1e3
        diffs.append(diff)
        unresolved += int(diff<REGEN_MV)
        wrong_resolved += int(diff>=REGEN_MV and
                              (s["Q_minus_QB_V"]>0) != bool(bits[index]))
    signed_v_margin.sort()
    diffs.sort()
    duplicates = {n:k for n,k in symbol.items() if k>1}
    start_ns = LINK.START_DATA_NS
    stop_ns = start_ns+LINK.BITS*TX.UI_PS*1e-3
    focused = [r for r in rows if
               (start_ns+5*TX.UI_PS*1e-3)*1e-9 <= r["time_s"] <= stop_ns*1e-9]
    return {
        "latch_output_regen_threshold_mV": REGEN_MV,
        "total_clock_samples": len(samples),
        "different_symbol_indices": len(symbol),
        "duplicate_symbol_index_events": len(duplicates),
        "max_samples_per_symbol": max(symbol.values()) if symbol else None,
        "unresolved_150mV": unresolved,
        "wrong_but_regenerated": wrong_resolved,
        "total_errors_including_unresolved": scoreboard["bit_errors_including_unresolved"],
        "median_abs_Q_minus_QB_mV": pct(diffs,.5),
        "p05_abs_Q_minus_QB_mV": pct(diffs,.05),
        "p05_signed_RX_margin_mV": pct(signed_v_margin,.05),
        "median_signed_RX_margin_mV": pct(signed_v_margin,.5),
        "negative_RX_margins": sum(v<0 for v in signed_v_margin),
        "partial_0p5V_TX_source_average_mW": weighted_supply_power_mw(
            focused,"power_tx_source_A",.5),
        "partial_1p8V_PLL_RX_source_average_mW": weighted_supply_power_mw(
            focused,"power_vdd_source_A",1.8),
    }

def save(path,rows):
    if not rows:
        return
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

def run(out,alpha):
    if alpha not in RATES:
        raise ValueError(f"Unsupported alpha {alpha}; choices {RATES}")
    out.mkdir(parents=True,exist_ok=True)
    label=f"alpha_{alpha:.2f}".replace(".","p")
    working=TX.ENGINE_DIR/f"p3_physical_refpll_ffe_{label}"
    runner=TX.SpiceRunner(working)
    model=TX.model_path("tt")
    target=working/model.name
    if not target.exists() or model.stat().st_mtime>target.stat().st_mtime:
        shutil.copy2(model,target)
    bits=TX.prbs7(LINK.BITS)
    runner.run(LINK.netlist(bits,alpha),label)
    wave=LINK.read(working/"pll_driven_rx_wave.csv")
    pll=LINK.frequency(wave)
    samples,scored=LINK.evaluate(wave,bits,LINK.START_DATA_NS)
    electrical=evaluate_electrical(wave,bits,samples,scored)
    result={
       "alpha":alpha,"bits_transmitted":len(bits),
       "bit_rate_Gbps":3.6,"physical_latch_threshold_mV":REGEN_MV,
       "pll":pll,"original_scoring":scored,
       "electrical_diagnostics":electrical,
       "actual_mos":"DB HiTek 180nm NMOS TX, PMOS-input RX latches, switched-MOS CP, MOS VCO",
       "hybrid":"XSPICE reference PFD/4 and ideal 450MHz reference clock",
       "channel":"ideal-buffered two-pole -12dB at 1.8GHz, NOT measured RG58/FR4",
       "controller":"450MHz reference PLL, NO data-phase feedback",
       "postrun_integer_frame_alignment_only":True,
       "not_statistical_BER":True,
       "not_total_link_power":True
    }
    (out/f"{label}_ablation.json").write_text(json.dumps(result,indent=2)+"\n")
    save(out/f"{label}_mos_latch_samples.csv",samples)
    # Save last 1/12 waveform points for independent external inspection.
    data=[x for x in wave if x["time_s"]>=LINK.START_DATA_NS*1e-9]
    save(out/f"{label}_rx_eye_waveform.csv",data[::12])
    print(
       f"TX_FFE_ABLATION {label}: PLL={pll['vco_GHz']:.9f}GHz "
       f"phase_std={pll['phase_standard_deviation_ps']:.3f}ps "
       f"MOS_RX={electrical['total_errors_including_unresolved']}/"
       f"{electrical['total_clock_samples']} "
       f"unresolved={electrical['unresolved_150mV']} "
       f"wrong_resolved={electrical['wrong_but_regenerated']} "
       f"unique_UI={electrical['different_symbol_indices']} "
       f"duplicates={electrical['duplicate_symbol_index_events']} "
       f"RX_p05_margin={electrical['p05_signed_RX_margin_mV']:.3f}mV "
       f"TX_mW={electrical['partial_0p5V_TX_source_average_mW']:.4f}",
       flush=True
    )
    if abs(pll["vco_GHz"]-1.8)>=.025:
        raise AssertionError("Reference PLL with physical TX/RX not frequency near 1.8 GHz")
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,
                   default=Path("results/spice/p3_mos_reference_ffe_ablation"))
    p.add_argument("--alpha",type=float,choices=RATES,required=True)
    args=p.parse_args()
    run(args.out,args.alpha)
