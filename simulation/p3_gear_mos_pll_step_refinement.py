#!/usr/bin/env python3
"""Fixed physical MOS PLL SS hot/low-V numerical convergence refinement.

The default 3ps and Gear 3ps trajectories for both 180nm MOS diode-PMOS
bias reference PLL designs were available. A previous attempt to
reduce Trapezoidal timestep to 1ps or 2ps aborted the transient; Gear
3ps passed candidate B but narrowly failed candidate A's late-window
frequency-span screen. Test Gear 3, 2 and 1ps with otherwise identical
MOS topologies, bias sources, and ideal 450MHz reference.

The simulator may abort; count electrical PASS only if the *full*
1200ns waveform is successfully measured and all five fixed PLL
electrical criteria hold. Never treat GitHub CI success as lock success.
"""
from __future__ import annotations
import argparse,json,re
from pathlib import Path
import p3_real_mos_bias_full_pvt as B
import p3_pll_extended_pvt_phase as P
import p3_xspice_physical_mos_pll as PLL
import p3_transistor_driver as TX

DESIGNS=B.DESIGNS
STEPS_PS=(1,2,3)
PVT=("ss",85.,1.71)

def patch(deck,step):
    target="tran 3p 1200n uic"
    if deck.count(target)!=1:
        # 1200ns is the current full reference-PLL analysis period.
        raise RuntimeError(f"Unexpected transient timepoint: {deck.count(target)}")
    deck=deck.replace(target,f"tran {step}p 1200n uic",1)
    return deck.replace(".control",
         ".options method=gear reltol=.001\n.control",1)

def run(out,design,step):
    if design not in DESIGNS or step not in STEPS_PS:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    old=P.deck
    try:
        P.deck=lambda c,t,v:patch(old(c,t,v),step)
        record=B.run(out/str(step),design,*PVT)
    finally:P.deck=old
    work=TX.ENGINE_DIR/"p3_PLL_extended_PVT_ss_tplus85_v1p71"
    try:last=PLL.read(work/"physical_pll.csv")[-1]["time_s"]*1e9
    except Exception:last=None
    complete=last is not None and last>=1199.8
    summary={
      "design":design,"Gear_timesteps_ps":step,
      "physical_MOS_RCVCO_PFD_chain":"DB HiTek 180nm MOS charge pump, MOS diode bias, ring VCO and digital XSPICE PFD",
      "PVT":"SS +85C 1.71V",
      "actual_transient_end_ns":last,
      "complete_1200ns_transient":complete,
      "original_electrical_screen_pass":record["electrical_screen_passed"],
      "qualified":bool(complete and record["electrical_screen_passed"]),
      "phase_std_ps":record["reference_phase_std_ps"],
      "frequency_drift_MHz":record["last_disjoint_window_freq_drift_MHz"],
      "reference_cycle_slips":record["last_reference_cycle_slips"],
      "model_p3_2004_silicon":False,
      "random_phase_noise_or_BER":False,
    }
    (out/f"{design}_Gear_{step}ps.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(f"GEAR_REFINEMENT design={design} step_ps={step} "
          f"last_ns={last} complete={complete} "
          f"phase_std_ps={summary['phase_std_ps']} "
          f"drift_MHz={summary['frequency_drift_MHz']} "
          f"cycle_slips={summary['reference_cycle_slips']} "
          f"qualified={summary['qualified']}",flush=True)
    return summary

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--design",choices=DESIGNS,required=True)
    p.add_argument("--step",type=int,choices=STEPS_PS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_gear_MOS_refinement"))
    a=p.parse_args()
    run(a.out,a.design,a.step)
