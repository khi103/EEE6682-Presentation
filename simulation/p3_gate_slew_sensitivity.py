#!/usr/bin/env python3
"""Gate-edge slew sensitivity in a reconstructed 180nm 8:4:2:1 NMOS TX.

Uses same TT MOS models, widths, PRBS, 50-ohm termination and -12dB RC
channel for every case. Replaces ideal gate PWL edge duration only.
Not the paper's actual slew-rate control circuit or predriver timing.
"""
from __future__ import annotations
import argparse
import csv
import json
import shutil
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import p3_transistor_driver as TX

GATE_RISE_FALL_PS=(2.,25.,60.,110.,180.)
SYMBOLS=128
SAMPLE_DELAY_UI=1.20

def sweep(out: Path):
    out.mkdir(parents=True,exist_ok=True)
    base=json.loads((out/"driver_summary.json").read_text())
    wu=base["calibration"]["up"]["unit_w_um"]
    wd=base["calibration"]["down"]["unit_w_um"]
    work=TX.ENGINE_DIR/"p3_slew_sensitivity"
    runner=TX.SpiceRunner(work)
    tt=TX.model_path("tt")
    if not (work/tt.name).exists() or tt.stat().st_mtime>(work/tt.name).stat().st_mtime:
        shutil.copy2(tt,work/tt.name)
    bits=TX.prbs7(SYMBOLS)
    records=[]
    for slew in GATE_RISE_FALL_PS:
        for label,alpha in (("no_ffe",0.),("two_tap_ffe",.30)):
            codes=TX.ffe_codes(bits,alpha)
            deck=TX.make_transient(codes,wu,wd,gate_transition_ps=slew)
            log=runner.run(deck,f"slew_{int(slew):03d}ps_{label}")
            wave=TX.parse_wrdata(work/"tx_waveform.csv")
            ideal_eye=TX.eye_at_fixed_phase(wave,bits,"rx_V",SAMPLE_DELAY_UI)
            best_eye=TX.eye_from_transient(wave,bits,"rx_V")["eye_mV"]
            t=np.asarray([x["time_s"] for x in wave])
            vout=np.asarray([x["pad_V"] for x in wave])
            vsup=np.asarray([x["supply_A"] for x in wave])
            # Proper time-weighted average with adaptive ngspice step sizes.
            power_mW=float(-TX.V_SIGNAL*np.trapezoid(vsup,t)/
                           (t[-1]-t[0])*1e3)
            rec={
                "gate_ideal_0to100_edge_ps":slew,
                "ffe_alpha":alpha,"name":label,
                "eye_common_sample_mV":ideal_eye,
                "eye_optimized_mV":best_eye,
                "time_weighted_signal_supply_mW":power_mW,
                "pad_min_mV":float(vout.min()*1e3),
                "pad_max_mV":float(vout.max()*1e3),
                "samples":len(wave)
            }
            records.append(rec)
            print(f"Slew={slew:g}ps {label}: common eye={ideal_eye:.3f}mV"
                  f", power 0.5V-only={power_mW:.3f}mW",flush=True)
    with (out/"gate_slew_sensitivity.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]))
        w.writeheader();w.writerows(records)
    d={"status":"passed_ideal_gate_slew_sensitivity_sweep",
       "basis":"ngspice DB HiTek 180nm NMOS TX output, ideal PWL gate controls",
       "rate_Gbps":3.6, "fixed_sampling_delay_UI":SAMPLE_DELAY_UI,
       "gate_edge_ps":GATE_RISE_FALL_PS,"results":records,
       "notes":["PWL 0-to-100 gate edge is not the measured TX 10-to-90 data edge",
                "Not the actual published predriver or slew-control circuit",
                "Measured power is only the 0.5V signal supply, not the digital gate drivers/clock",
                "Same receiver channel RC2 surrogate; source impedance calibration only TT"] }
    (out/"gate_slew_sensitivity.json").write_text(json.dumps(d,indent=2)+"\n")
    fig,axs=plt.subplots(1,2,figsize=(12,4.7),layout="constrained")
    for label in ("no_ffe","two_tap_ffe"):
        rr=[r for r in records if r["name"]==label]
        xx=[r["gate_ideal_0to100_edge_ps"] for r in rr]
        axs[0].plot(xx,[r["eye_common_sample_mV"] for r in rr],marker="o",
                    label="2-tap FFE" if label=="two_tap_ffe" else "No FFE")
        axs[1].plot(xx,[r["time_weighted_signal_supply_mW"] for r in rr],
                    marker="o",label="2-tap FFE" if label=="two_tap_ffe" else "No FFE")
    axs[0].set(ylabel="Common-phase RX eye height (mV)",
               xlabel="Ideal MOS gate 0-to-100% edge time (ps)",
               title="FFE compensation vs drive slew")
    axs[1].set(ylabel="0.5-V source time-averaged power (mW)",
               xlabel="Ideal MOS gate edge time (ps)",
               title="Switching power sensitivity (incomplete)")
    for ax in axs:
        ax.legend()
        ax.grid(alpha=.3)
    fig.savefig(out/"fig_gate_slew_sensitivity.png",dpi=170)
    plt.close(fig)
    assert all(np.isfinite(r["eye_common_sample_mV"]) for r in records)
    print("PASS: Gate slew sensitivity sweep, consistent testbench",flush=True)
    return d

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=TX.DEFAULT_OUT)
    args=p.parse_args()
    sweep(args.out)
