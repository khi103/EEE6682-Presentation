#!/usr/bin/env python3
"""Alexander-style bang-bang CDR on ngspice NMOS-TX / synthetic-channel trace.

Implements ONLY a first-order discrete-time CDR FUNCTIONAL phase update.
Not paper's PLL, phase detector, charge-pump mismatch, loop filter, VCO
or jitter-transfer/noise model. Uses the same fixed 128-bit PRBS snapshot.
"""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import p3_rx_noise_jitter_sensitivity as RX

K_UI=0.025
START_OFFSETS=(-0.28,+0.28)
BASE_PHASE_UI=1.20

def run(out: Path):
    out.mkdir(parents=True,exist_ok=True)
    bits=RX.prbs7(RX.BITS)
    full=[]
    report={}
    for mode in ("baseline","ffe_alpha_0p30"):
        time,v=RX.load_waveform(out/f"{mode}_mos_tx_rx.csv")
        idx=np.arange(16,RX.BITS-6)
        ideal=np.interp((idx+BASE_PHASE_UI)*RX.UI_S,time,v)
        high=ideal[bits[idx]==1];low=ideal[bits[idx]==0]
        threshold=(min(high)+max(low))/2
        for start in START_OFFSETS:
            phase_delta=start
            rows=[]
            edges_seen=0
            for n in range(17,RX.BITS-6):
                def sample(relative_bit):
                    t=(relative_bit+BASE_PHASE_UI+phase_delta)*RX.UI_S
                    return float(np.interp(t,time,v))
                d_prev=int(sample(n-1)>=threshold)
                d_cur=int(sample(n)>=threshold)
                d_edge=int(sample(n-.5)>=threshold)
                change=0
                if d_prev!=d_cur:
                    edges_seen+=1
                    if d_edge==d_prev:
                        change=+K_UI
                    else:
                        change=-K_UI
                phase_delta=float(np.clip(phase_delta+change,-.45,.45))
                rows.append({"mode":mode,"start_offset_UI":start,
                             "bit_index":n,
                             "phase_error_UI":phase_delta,
                             "phase_error_ps":phase_delta*RX.UI_S*1e12,
                             "transition_used":int(d_prev!=d_cur),
                             "true_bit":int(bits[n]),
                             "decision":d_cur,
                             "decision_correct":int(d_cur==bits[n])})
            full.extend(rows)
            label=f"{mode}_start_{start:+.2f}"
            report[label]={
              "start_phase_error_UI":start,
              "final_phase_error_UI":phase_delta,
              "final_phase_error_ps":phase_delta*RX.UI_S*1e12,
              "transitions_tracked":edges_seen,
              "final_20_steps_mean_phase_error_UI":float(np.mean([r["phase_error_UI"] for r in rows[-20:]])),
              "raw_decision_error_count":sum(1-r["decision_correct"] for r in rows),
              "limitation":"relative phase is the model's data-sampling phase correction, not a measured PLL phase"
            }
    with (out/"behavioral_cdr_phase_tracking.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(full[0]))
        w.writeheader();w.writerows(full)
    d={"status":"alexander_like_behavioral_phase_tracking",
       "loop_gain_UI_per_transition":K_UI,
       "nominal_sampling_phase_UI":BASE_PHASE_UI,
       "method":"early/late transition majority with ideal static input threshold",
       "scenarios":report,
       "limitations":[
         "Only 128 PRBS symbols, reused ngspice waveforms and first-order phase updates",
         "No charge pump current mismatch / phase detector metastability / VCO noise / recovered PLL",
         "Not original Wong et al. timing recovery hardware",
         "Phase convergence is a qualitative loop sensitivity example, not BER validation"
       ]}
    (out/"behavioral_cdr_phase_tracking.json").write_text(json.dumps(d,indent=2)+"\n")
    fig,ax=plt.subplots(figsize=(10.2,5.3),layout="constrained")
    for label in report:
        mode,start=label.split("_start_")
        rows=[z for z in full if z["mode"]==mode and abs(z["start_offset_UI"]-float(start))<1e-6]
        ax.plot([r["bit_index"] for r in rows],
                [r["phase_error_ps"] for r in rows],
                label=f"{'FFE' if mode!='baseline' else 'No FFE'} init {start}UI")
    ax.axhline(0,color="gray",ls="--")
    ax.set(xlabel="PRBS bit index",
           ylabel="Phase correction relative to nominal (ps)",
           title="Functional Alexander-like CDR: ideal sampled-loop stress test")
    ax.legend(fontsize=8);ax.grid(alpha=.3)
    fig.savefig(out/"fig_behavioral_cdr_phase_tracking.png",dpi=165)
    plt.close(fig)
    assert len(report)==4
    print("PASS: Functional CDR phase tracking executed (not PLL silicon)",json.dumps(report))
    return d

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--out",type=Path,default=Path("results/spice/p3_segmented_driver"))
    run(a.parse_args().out)
