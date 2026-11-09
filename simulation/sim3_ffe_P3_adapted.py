#!/usr/bin/env python3
"""P3 adaptation of the EXPERIMENT in the lecture linksim_H-L/sim3_ffe.py.
Original: 56 Gb/s, 3/5/9-tap ZF, Verilator/S-parameter channel.
Here: 3.6 Gb/s, 12 dB @ 1.8 GHz, 250 mVpp, 2-tap alpha=0.30,
plus 3/5/9 ZF and the same sum(abs(coefficients))=1 convention.
The simulation BACKEND is an independent Python 2-pole RC surrogate.
This is not a literal original-Verilator run or the fabricated-chip model.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import p3_reproduce as P

G = 3.6
LOSS_DB_AT_NYQUIST = 12.0
ALPHA = 0.30
VPP_MV = 250.0
CFG = {"No FFE":(1,0), "Paper 2-tap":(2,0),
       "ZF 3-tap":(3,1), "ZF 5-tap":(5,1), "ZF 9-tap":(9,2)}

def reproduce(outdir: Path, nbits: int=2048):
    outdir.mkdir(parents=True,exist_ok=True)
    P.run(outdir, nbits=nbits)
    raw=json.loads((outdir/"p3_results.json").read_text())
    lookup={"No FFE":"1-tap, no FFE",
            "Paper 2-tap":"2-tap, alpha=0.30",
            "ZF 3-tap":"3-tap ZF (lecture extension)",
            "ZF 5-tap":"5-tap ZF (lecture extension)",
            "ZF 9-tap":"9-tap ZF (lecture extension)"}
    names=list(lookup)
    vals=[raw["simulated_cases"][lookup[k]] for k in names]
    eye=np.array([v["worst_case_eye_height_mV"] for v in vals])
    dc=np.array([v["DC_run_amplitude_mVpp"] for v in vals])
    main=np.array([v["main_cursor_mV"] for v in vals])
    isi=np.array([v["sum_abs_other_cursors_mV"] for v in vals])
    assert np.all([abs(v["L1"]-1)<1e-10 for v in vals])
    assert abs(P.channel_db(1.8e9)+12)<1e-10
    assert np.allclose(vals[1]["taps"],[1/(1+ALPHA),-ALPHA/(1+ALPHA)])
    fig, ax=plt.subplots(1,3,figsize=(15,4.8))
    xx=np.arange(len(names)); labs=["1","2","3","5","9"]
    colors=["#777777","#b3261e"]+["#537f95"]*3
    ax[0].bar(xx,dc,color=colors);ax[0].axhline(VPP_MV,color="black",ls="--",label="Peak budget")
    ax[0].set(ylabel="Long-run DC swing (mVpp)",title="Swing cost, Σ|c|=1");ax[0].legend()
    ax[1].bar(xx,np.maximum(eye,0),color=colors)
    ax[1].set(ylabel="Worst-case eye height (mV)",title="Eye height: not monotonic")
    ax[2].plot(xx,main,"-o",label="Main cursor");ax[2].plot(xx,isi,"-s",label="Σ |other cursors|")
    ax[2].set(ylabel="SBR voltage (mV)",title="Cursor/ISI trade-off");ax[2].legend()
    for a in ax:
        a.set_xticks(xx,labs);a.set_xlabel("Number of TX FFE taps");a.grid(axis="y",alpha=.2)
    fig.suptitle("Modified lecture sim3_ffe methodology: 3.6 Gb/s, 12 dB at 1.8 GHz, 250 mVpp")
    fig.tight_layout(rect=(0,0,1,.93))
    fig.savefig(outdir/"P3_modified_sim3_ffe_tap_swing_eye.png",dpi=180)
    plt.close(fig)
    results={"lecture_start":"linksim_H-L/sim3_ffe.py",
             "limitation":"Independent Python 2-pole RC, NOT Verilator or measured RG58",
             "gbps":G,"nyquist_GHz":1.8,"loss_dB_at_nyquist":12,
             "peak_mVpp":250,
             "cases":{k:{"taps":vals[i]["taps"],"sum_abs_taps":vals[i]["L1"],
                        "dc_swing_mVpp":dc[i],"eye_height_mV":eye[i],
                        "h0_mV":main[i],"ISI_mV":isi[i]} for i,k in enumerate(names)}}
    (outdir/"P3_modified_sim3_ffe_summary.json").write_text(json.dumps(results,indent=2))
    print("Validated paper-specific 3.6-Gb/s adapted experiment")
    for i,name in enumerate(names):
        print(f"{name:14s} eye={eye[i]:.2f} mV | DC={dc[i]:.2f} mVpp | h0={main[i]:.2f} mV")
    return results

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",default="results")
    ap.add_argument("--nbits",type=int,default=2048)
    args=ap.parse_args()
    reproduce(Path(args.out),args.nbits)
