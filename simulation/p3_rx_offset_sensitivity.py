#!/usr/bin/env python3
"""Synthetic sampler-offset calibration sensitivity using MOS TX waveforms.

Runs 128-bit ngspice MOS-driver waveform through an IDEAL binary sampler
at one fixed 1.20-UI phase. Uses a fixed ±40-mV input-referred offset,
Gaussian 4-mV RMS voltage noise, then an ideal exact offset subtraction.
The circuit of the paper's digitally calibrated comparator is NOT modeled.
"""
from __future__ import annotations
from pathlib import Path
import argparse,csv,json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import p3_rx_noise_jitter_sensitivity as RX

OFFSETS_MV=(-40,-30,-20,-10,0,10,20,30,40)
SIGMA_MV=4.0
SEED=20261112
TRIALS=500

def analyze(out: Path):
    out.mkdir(parents=True,exist_ok=True)
    bits=RX.prbs7(RX.BITS)
    idx=np.arange(16,RX.BITS-6)
    labels=bits[idx]
    ts=(idx+RX.PHASE_UI)*RX.UI_S
    rng=np.random.default_rng(SEED)
    noise=rng.normal(0,SIGMA_MV/1e3,(TRIALS,len(idx)))
    rowlist=[];calibrations={}
    for mode in ("baseline","ffe_alpha_0p30"):
        t,v=RX.load_waveform(out/f"{mode}_mos_tx_rx.csv")
        waveform=np.interp(ts,t,v)
        threshold=(np.min(waveform[labels==1]) +np.max(waveform[labels==0]))/2
        eye=(np.min(waveform[labels==1])-np.max(waveform[labels==0]))*1e3
        calibrations[mode]={"threshold_no_offset_V":float(threshold),
                            "noiseless_eye_mV":float(eye)}
        for offset in OFFSETS_MV:
            for calib in ("none","ideal_exact_offset_removal"):
                measured=waveform[None,:]+noise+(offset/1e3)
                if calib=="ideal_exact_offset_removal":
                    measured=measured-offset/1e3
                errors=int(np.count_nonzero((measured>=threshold)!=labels[None,:]))
                rowlist.append({
                  "mode":mode,"offset_mV":offset,"noise_rms_mV":SIGMA_MV,
                  "calibration":calib,"trial_bits":len(labels)*TRIALS,
                  "error_count":errors,
                  "observed_error_fraction":errors/(len(labels)*TRIALS),
                  "not_true_BER":1,
                })
    with (out/"rx_offset_sensitivity.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rowlist[0]))
        w.writeheader();w.writerows(rowlist)
    report={"status":"synthetic_comparator_offset_and_ideal_correction",
            "physical_source":"ngspice MOS TX plus surrogate RC channel",
            "not_original_RX":True,
            "noise_rms_mV":SIGMA_MV,
            "fixed_sample_UI":RX.PHASE_UI,
            "trial_bits_per_case":len(labels)*TRIALS,
            "offsets_mV":OFFSETS_MV,
            "calibrations":calibrations,
            "limits":["Ideal comparator threshold; no physical transistor comparator",
                      "Perfect offset subtraction uses the true offset; not the paper's calibration",
                      "Reused 106 bits from a single 128-bit PRBS7 transient",
                      "Finite empirical error rate does not establish silicon BER"],
            "results":rowlist}
    (out/"rx_offset_sensitivity.json").write_text(json.dumps(report,indent=2)+"\n")
    fig,ax=plt.subplots(figsize=(9,5.3),layout="constrained")
    for mode in ("baseline","ffe_alpha_0p30"):
      for cal in ("none","ideal_exact_offset_removal"):
        rr=[r for r in rowlist if r["mode"]==mode and r["calibration"]==cal]
        xx=[r["offset_mV"] for r in rr]
        yy=[max(r["observed_error_fraction"],1/(len(labels)*TRIALS)/3) for r in rr]
        ax.semilogy(xx,yy,marker="o",linestyle=("-" if mode=="ffe_alpha_0p30" else "--"),
                    label=("FFE" if mode=="ffe_alpha_0p30" else "No FFE")+
                    (" + ideal offset trim" if cal!="none" else ""))
    ax.set(xlabel="Added input-referred comparator offset (mV)",
           ylabel="Observed decision-error fraction (log scale)",
           title="Synthetic RX offset: ngspice MOS TX + ideal comparator")
    ax.legend(ncol=2,fontsize=8)
    ax.grid(alpha=.3)
    fig.savefig(out/"fig_rx_offset_sensitivity.png",dpi=165)
    plt.close(fig)
    assert len(rowlist)==2*len(OFFSETS_MV)*2
    print("PASS: RX offset/ideal-correction sensitivity on MOS transient",flush=True)
    return report

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--out",type=Path,default=Path("results/spice/p3_segmented_driver"))
    analyze(a.parse_args().out)
