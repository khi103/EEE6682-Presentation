#!/usr/bin/env python3
"""Sensitivity of reconstructed MOS-TX waveforms to synthetic RX noise/jitter.

INPUTS: transient waveforms produced by ngspice for the same 128-bit PRBS7,
baseline (alpha 0) and 2-tap FFE (alpha 0.30). This script does not model
the original 2004 comparator, PLL, CDR, a measured cable, or a BER-12 target.

The per-mode slicer threshold is calibrated from NOISELESS waveforms at a
COMMON sample phase of 1.20 UI. Each PRBS bit is then re-sampled with
independent Gaussian timing jitter and Gaussian sampler voltage noise.
Monte-Carlo trials reuse the same 106 distinct PRBS bits; this is a useful
sensitivity metric, not statistical evidence for 1e-12 BER.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

GBPS = 3.6
UI_S = 1/(GBPS*1e9)
BITS = 128
PHASE_UI = 1.20
NOISE_SIGMA_MV = (0, 4, 8, 12, 16, 20, 24)
JITTER_SIGMA_PS = (0, 5, 10, 20)
MONTE_CARLO_TRIALS = 2000
RNG_SEED = 20261112

def prbs7(n: int, seed: int=0x5D):
    state=seed & 127
    result=[]
    for _ in range(n):
        result.append(state&1)
        feedback=((state>>6) ^ (state>>5))&1
        state=((state<<1)&127)|feedback
    return np.asarray(result,dtype=np.int8)

def load_waveform(file: Path):
    a=np.genfromtxt(file,delimiter=",",names=True)
    time=a["time_s"]
    volts=a["rx_V"]
    if len(time)<500 or np.min(volts)<-1 or np.max(volts)>2:
        raise ValueError(f"Unexpected waveform file {file}")
    if np.any(np.diff(time)<0):
        raise ValueError("Waveform times not monotonic")
    # Interpolation handles duplicate solver time points; select first instance.
    unique,index=np.unique(time,return_index=True)
    return unique,volts[index]

def analyze(out: Path, trials:int=MONTE_CARLO_TRIALS):
    bits=prbs7(BITS)
    idx=np.arange(16,BITS-6)
    targets=bits[idx]
    sampled_t=(idx+PHASE_UI)*UI_S
    total=trials*len(idx)
    rng=np.random.default_rng(RNG_SEED)
    rows=[]
    metadata={}
    for mode in ("baseline","ffe_alpha_0p30"):
        t,v=load_waveform(out/f"{mode}_mos_tx_rx.csv")
        samples=np.interp(sampled_t,t,v)
        hi=samples[targets==1]
        lo=samples[targets==0]
        threshold=(np.min(hi)+np.max(lo))/2
        eye_mV=(np.min(hi)-np.max(lo))*1000.
        metadata[mode]={
          "noise_free_common_phase_eye_mV":float(eye_mV),
          "threshold_V":float(threshold),
          "unique_prbs_bits_per_trial":len(idx),
          "samples_reused_per_mode":int(total),
        }
        if eye_mV<=0:
            raise AssertionError(f"Eye closed at common phase for {mode}")
        for jitter_ps in JITTER_SIGMA_PS:
            # Same seed and sample-time jitters for both FFE modes.
            # Fresh independent receiver-voltage noise at each noise RMS.
            jitter_rng=np.random.default_rng(RNG_SEED+int(jitter_ps))
            jitters=jitter_rng.normal(0.,jitter_ps*1e-12,(trials,len(idx)))
            noisy_sample_time=(sampled_t[None,:]+jitters).ravel()
            raw=np.interp(noisy_sample_time,t,v).reshape(trials,len(idx))
            for noise_mV in NOISE_SIGMA_MV:
                noise_rng=np.random.default_rng(RNG_SEED+10000+int(noise_mV)*100+int(jitter_ps))
                noise=noise_rng.normal(0.,noise_mV/1000.,raw.shape)
                observed=raw+noise
                errors=int(np.count_nonzero((observed>threshold)!=targets[None,:]))
                rows.append({
                  "mode":mode,
                  "rx_noise_sigma_mV":noise_mV,
                  "timing_jitter_sigma_ps":jitter_ps,
                  "trial_bits":total,
                  "error_count":errors,
                  "empirical_error_fraction":errors/total,
                  "upper_95pct_bound_if_zero_errors":float(3/total) if errors==0 else "",
                  "ideal_threshold_V":float(threshold),
                  "noiseless_eye_height_mV":float(eye_mV)
                })
    dest=out/"rx_noise_jitter_robustness.csv"
    with dest.open("w",newline="",encoding="utf8") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report={
      "status":"synthetic_receiver_noise_jitter_study",
      "data_source":"Actual ngspice transient waveforms of INDEPENDENT DB HiTek NMOS TX reconstruction",
      "method":"sample same 1.20-UI phase; optimize only noiseless decision threshold per mode; independent zero-mean Gaussian receiver voltage noise and timing jitter",
      "noise_rms_mV":NOISE_SIGMA_MV,
      "jitter_rms_ps":JITTER_SIGMA_PS,
      "trials_per_mode_per_condition":trials,
      "reused_prbs_bits_per_trial":len(idx),
      "limitations":[
       "Synthetic Gaussian RX noise and jitter are not transistor-level noise/PLL/CDR models",
       "Only 128-bit PRBS7 captured, 106 evaluated bits per repetition; errors are conditional Monte Carlo proxies",
       "Zero observed errors cannot demonstrate actual BER below 1e-12",
       "Threshold calibrated independently for each mode from noiseless samples",
       "No original silicon 37 mV eye reproduction",
      ],
      "modes":metadata,
      "comparison_10ps_12mV":{
        m:next({"error_count":r["error_count"],"empirical_error_fraction":r["empirical_error_fraction"]}
               for r in rows if r["mode"]==m and r["timing_jitter_sigma_ps"]==10 and r["rx_noise_sigma_mV"]==12)
        for m in ("baseline","ffe_alpha_0p30")
      }
    }
    (out/"rx_noise_jitter_robustness.json").write_text(json.dumps(report,indent=2)+"\n")
    fig,ax=plt.subplots(figsize=(9.4,5.6),layout="constrained")
    for mode,line_style in (("baseline","--"),("ffe_alpha_0p30","-")):
        for jitter_ps in (0,10,20):
            selected=[r for r in rows if r["mode"]==mode and r["timing_jitter_sigma_ps"]==jitter_ps]
            ax.semilogy([r["rx_noise_sigma_mV"] for r in selected],
                        [max(r["empirical_error_fraction"],1/total/3) for r in selected],
                        linestyle=line_style,marker="o",
                        label=f"{'FFE' if mode!='baseline' else 'No FFE'}, J={jitter_ps} ps")
    ax.set(xlabel="Added Gaussian RX noise RMS (mV)",
           ylabel="Observed decision-error fraction (log scale)",
           title="Synthetic RX noise/jitter sensitivity of ngspice MOS-TX traces")
    ax.legend(ncol=2,fontsize=9)
    ax.grid(alpha=.25)
    fig.savefig(out/"fig_rx_noise_jitter_robustness.png",dpi=170)
    plt.close(fig)
    print("PASS: Synthetic RX noise/jitter sensitivity run",json.dumps(report["comparison_10ps_12mV"]))
    return report

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",type=Path,default=Path("results/spice/p3_segmented_driver"))
    ap.add_argument("--trials",type=int,default=MONTE_CARLO_TRIALS)
    args=ap.parse_args()
    analyze(args.out,args.trials)
