#!/usr/bin/env python3
"""Plot evidence from the *actual one-netlist* MOS TX, MOS RX and MOS VCO.

This does not illustrate a claimed complete PLL/CDR; phase selection
was performed offline after MOS transient simulation.
"""
import argparse,csv,json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def plot(out):
    source=out/"integrated_mos_vco_ffe_waveform.csv"
    with source.open(newline="") as f:
        rows=list(csv.DictReader(f))
    report=json.loads((out/"integrated_mos_vco_summary.json").read_text())
    t=[float(r["time_s"])*1e9 for r in rows]
    t0=18
    t1=21.5
    sample=[i for i,ti in enumerate(t) if t0<=ti<=t1]
    if len(sample)<150: raise RuntimeError("No steady-state MOS waveform window")
    fig,axes=plt.subplots(3,1,figsize=(12,8),layout="constrained",sharex=True)
    xx=[t[i] for i in sample]
    for key,label in (("pad_V","MOS TX pad"),("rx_V","RX after 2-pole surrogate")):
        axes[0].plot(xx,[float(rows[i][key])*1000 for i in sample],label=label)
    axes[0].set(ylabel="Voltage (mV)",title="Actual MOS TX 8:4:2:1 and RC RX waveform")
    for key,label in (("vco_n1_V","3-stage MOS VCO"),
                      ("clock_even_V","MOS even-lane clock"),
                      ("clock_odd_V","MOS odd-lane clock")):
        axes[1].plot(xx,[float(rows[i][key]) for i in sample],label=label)
    axes[1].set(ylabel="Clock (V)",title="Physical current-starved MOS VCO and CMOS buffers")
    for key,label in (("qeven_V","Q (even-lane MOS latch)"),
                      ("qbeven_V","QB (even-lane MOS latch)"),
                      ("qodd_V","Q (odd-lane MOS latch)")):
        axes[2].plot(xx,[float(rows[i][key]) for i in sample],label=label)
    axes[2].set(xlabel="Time (ns)",ylabel="Latch output (V)",
                title="Physical PMOS-input regenerative RX decisions")
    for a in axes:
        a.grid(alpha=.3)
        a.legend(ncol=3,fontsize=8)
    fig.savefig(out/"fig_integrated_mos_tx_rx_physical_vco.png",dpi=170)
    plt.close(fig)
    data=report["cases"]["ffe_0p30"]
    fig,ax=plt.subplots(figsize=(8,3.6),layout="constrained")
    labels=["MOS VCO+RX at 1.8V","MOS TX at 0.5V"]
    values=[data["transistor_vdd_1p8V_source_power_mW"],
            data["transistor_tx_signaling_0p5V_source_power_mW"]]
    bars=ax.bar(labels,values)
    ax.bar_label(bars,fmt="%.3f mW")
    ax.set(ylabel="Time-averaged measured source power (mW)",
           title="Partial MOS-link power; NOT complete 27.12-mW paper budget")
    ax.grid(axis="y",alpha=.25)
    fig.savefig(out/"fig_integrated_partial_supply_power.png",dpi=170)
    plt.close(fig)
    print("PASS: Real MOS TX/RC/MOS RX/MOS-VCO waveform/power figures generated")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_mos_vco_integrated"))
    plot(p.parse_args().out)
