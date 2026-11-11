#!/usr/bin/env python3
"""Plot verified outputs from the *reconstructed* P3 NMOS driver ngspice run.
Neither traces nor device data are the published silicon measurements.
"""
from pathlib import Path
import argparse
import csv
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def rows(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))

def plot(out):
    doc=json.loads((out/"driver_summary.json").read_text())
    dac=rows(out/"tt_code_sweep.csv")
    cv=[int(r["code"]) for r in dac]
    v=[float(r["vout_V"])*1000 for r in dac]
    ideal=[float(r["ideal_loaded_V"])*1000 for r in dac]
    z=[float(r["rout_ohm_at_vref"]) for r in dac]
    p=[float(r["p_signal_supply_mW"]) for r in dac]
    fig, axes=plt.subplots(2,1,figsize=(10,8),layout="constrained")
    axes[0].plot(cv,v,"o-",label="DB HiTek SVT, reconstructed NMOS driver")
    axes[0].plot(cv,ideal,"--",label="Ideal 50-ohm 4-bit levels")
    axes[0].set(ylabel="Loaded output (mV)",title="16 levels; 0.5-V signal supply and 50-ohm matched load")
    axes[0].legend()
    axes[1].plot(cv,z,"o-",label="Incremental source resistance near 0.25 V")
    axes[1].axhline(50,color="gray",ls="--",label="50 ohm reference")
    axes[1].set(xlabel="Binary-weighted driver code (8:4:2:1)",
                ylabel="Output resistance (ohm)")
    axes[1].legend()
    for a in axes: a.grid(alpha=.3)
    fig.savefig(out/"fig_tx_codes_and_impedance.png",dpi=175);plt.close(fig)

    fig, axes=plt.subplots(1,3,figsize=(16,5),layout="constrained")
    pvt=rows(out/"pvt_corner_sweep.csv")
    corners=sorted({r["corner"] for r in pvt if float(r["temp_C"])==27 and float(r.get("v_signal_V",0.5))==0.5})
    for c in corners:
        data=sorted([r for r in pvt if r["corner"]==c and float(r["temp_C"])==27 and float(r.get("v_signal_V",0.5))==0.5],key=lambda r:int(r["code"]))
        axes[0].plot([int(r["code"]) for r in data],
                     [float(r["rout_ohm_at_vref"]) for r in data],
                     marker="o",label=c.upper())
    axes[0].axhline(50,color="black",ls="--",lw=1)
    axes[0].set(xlabel="Driver code",ylabel="Output resistance (ohm)",
                title="PVT (no adaptive impedance feedback)")
    axes[0].legend(ncol=2)
    for code in (0,7,15):
        sweep=sorted((r for r in pvt if r["corner"]=="tt" and
          float(r["temp_C"])==27 and int(r["code"])==code),
          key=lambda r:float(r["v_signal_V"]))
        axes[1].plot([float(r["v_signal_V"]) for r in sweep],
                     [float(r["rout_ohm_at_vref"]) for r in sweep],
                     marker="o",label=f"Code {code}")
    axes[1].axhline(50,color="gray",ls="--")
    axes[1].set(xlabel="Signaling supply (V)",ylabel="Output resistance (ohm)",
                title="TT, VREF = VS/2, core gates 1.8 V")
    axes[1].legend()
    axes[2].plot(cv,p,"o-",label="TT @ 27 C")
    axes[2].set(xlabel="Driver code",ylabel="0.5-V supply DC power (mW)",
                title="Static MOS output-stage power, not the full link")
    axes[2].legend()
    for a in axes:a.grid(alpha=.3)
    fig.savefig(out/"fig_tx_corners_and_power.png",dpi=175);plt.close(fig)

    if "transient" in doc:
        fig,ax=plt.subplots(2,1,figsize=(12,7),layout="constrained",sharex=True)
        for name,title in (("baseline","No FFE"),("ffe_alpha_0p30","2-tap FFE alpha=0.30")):
            path=out/f"{name}_mos_tx_rx.csv"
            data=rows(path)
            stride=max(1,len(data)//2000)
            tt=[float(r["time_s"])*1e9 for r in data[::stride]]
            for axis,key in zip(ax,["pad_V","rx_V"]):
                vv=[float(r[key])*1000 for r in data[::stride]]
                axis.plot(tt,vv,label=title,linewidth=.75)
        ax[0].set(ylabel="TX pad (mV)",title="Mos-driver data transient")
        ax[1].set(xlabel="Time (ns)",ylabel="RX after surrogate channel (mV)")
        for a in ax: a.grid(alpha=.25);a.legend()
        fig.savefig(out/"fig_mos_tx_and_rx_waveforms.png",dpi=175);plt.close(fig)
    print("PNG plots written to",out)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_segmented_driver"))
    args=p.parse_args()
    plot(args.out)
