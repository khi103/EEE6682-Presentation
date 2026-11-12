#!/usr/bin/env python3
"""Test whether an *ideal* shared NMOS gate-bias adjustment could recover 50 ohms.

This is control AUTHORITY characterization for our independent MOS TX stage,
not the paper's transistor bias/replica loop, not dynamic closed-loop recovery.
Gate biases tested 0.9-1.8 V, with 0.5-V signaling supply and 0.25-V clamp.
All widths are fixed at their TT-calibrated nominal values across corners.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import p3_transistor_driver as TX

GATE_VOLTAGES = (0.9, 1.1, 1.3, 1.5, 1.65, 1.8)
TARGET_OHM = 50.0
TEST_CODE = 7

def measure(out: Path):
    original=json.loads((out/"driver_summary.json").read_text())
    wu=float(original["calibration"]["up"]["unit_w_um"])
    wd=float(original["calibration"]["down"]["unit_w_um"])
    work=TX.ENGINE_DIR/"p3_gate_bias_authority"
    runner=TX.SpiceRunner(work)
    for corner in TX.CORNER_NAMES:
        src=TX.model_path(corner)
        shutil.copy2(src,work/src.name)
    data=[]
    for corner in TX.CORNER_NAMES:
        for gate_v in GATE_VOLTAGES:
            currents=[]
            for offset in (-.001,+.001):
                deck=TX.make_dc(TEST_CODE,wu,wd,corner,
                                TX.V_COMMON+offset)
                # Only modify gate driver voltage SOURCES; do not touch
                # PDK model MOSFET thresholds or channel parameters.
                deck,count=re.subn(
                    r"(?m)^(VG[UD][1248]\s+\S+\s+0\s+DC\s+)1\.8\s*$",
                    lambda match:f"{match.group(1)}{gate_v:.6g}",deck)
                if gate_v!=1.8 and count==0:
                    raise RuntimeError("No high gate biases were replaced")
                log=runner.run(deck,f"authority_{runner.calls:05d}")
                currents.append(TX.spice_vector(log,"i(vclamp)"))
            rout=.002/abs(currents[1]-currents[0])
            data.append({"corner":corner,"gate_high_V":gate_v,
                         "code":TEST_CODE,"unit_pullup_width_um":wu,
                         "unit_pulldown_width_um":wd,
                         "rout_ohm":rout,"error_from_50_percent":100*(rout/50-1)})
    path=out/"gate_bias_authority.csv"
    with path.open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]))
        w.writeheader();w.writerows(data)
    report={}
    for corner in TX.CORNER_NAMES:
        a=sorted((r for r in data if r["corner"]==corner),
                 key=lambda r:r["gate_high_V"])
        v50=None
        for p,q in zip(a,a[1:]):
            y0,y1=p["rout_ohm"],q["rout_ohm"]
            if (y0-50)*(y1-50)<=0 and y0!=y1:
                v50=p["gate_high_V"]+(50-y0)*(q["gate_high_V"]-p["gate_high_V"])/(y1-y0)
                break
        report[corner]={
            "rout_at_1p8V_ohm":a[-1]["rout_ohm"],
            "rout_at_0p9V_ohm":a[0]["rout_ohm"],
            "crosses_50_ohm_in_tested_bias_range":bool(v50 is not None),
            "estimated_interpolated_gate_voltage_V":v50,
            "note":"Single operating point/code with independent ideal gate source. Not real replica/feedback."
        }
    dest=out/"gate_bias_authority.json"
    doc={
      "status":"simulated_independent_gate_bias_control_authority",
      "tested_corners":TX.CORNER_NAMES,
      "scope":"code 7, TT-sized 8:4:2:1 NMOS stage, 0.5-V signal supply, 1.8-V upper gate limit",
      "gate_high_V":GATE_VOLTAGES,
      "ngspice_calls":runner.calls,
      "per_corner":report,
      "limitations":[
        "No physical impedance feedback or closed-loop convergence",
        "Only one output code and 0.25-V DC operating point was tested",
        "Only gate-bias adjustments 0.9-1.8 V; other hardware controls could provide extra authority",
        "ngspice/HSPICE model numerical compatibility not established",
      ]
    }
    dest.write_text(json.dumps(doc,indent=2)+"\n")
    fig,ax=plt.subplots(figsize=(8,5.5),layout="constrained")
    for corner in TX.CORNER_NAMES:
        a=sorted((r for r in data if r["corner"]==corner),
                 key=lambda r:r["gate_high_V"])
        ax.plot([r["gate_high_V"] for r in a],
                [r["rout_ohm"] for r in a],marker="o",
                label=corner.upper())
    ax.axhline(50,ls="--",color="black",label="50 ohm target")
    ax.set(xlabel="Ideal shared gate-high bias (V)",
           ylabel="Incremental output resistance (ohm)",
           title="PVT gate-bias control authority: independent 180nm NMOS driver")
    ax.grid(alpha=.3)
    ax.legend()
    fig.savefig(out/"fig_gate_bias_control_authority.png",dpi=170)
    plt.close(fig)
    print("PASS: Gate-bias control-authority study",json.dumps(report))
    return doc

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=TX.DEFAULT_OUT)
    measure(p.parse_args().out)
