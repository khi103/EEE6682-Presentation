#!/usr/bin/env python3
"""Numerical-convergence test of the worst 90-case MOS reference PLL PVT.

The independent 90-case PVT audit found the most marginal case:
SS 85C VDD=1.71V. The W16/4k MOS diode-bias candidate passed the
2-MHz late 3x80ns frequency-drift limit by only about 0.00491 MHz.
Re-simulate the SAME MOS netlist, unchanged electrical sizes/bias,
with tighter trapezoidal maximum time steps or Gear integration.
A successful nominal PVT screen is not automatically numerically
robust or a statistical foundry guarantee.

This checks two fixed physical diode PMOS bias designs with the
same 450MHz ideal reference and reconstructed MOS CP/VCO. No actual
2004 layout, measured phase noise, or physical data CDR is implied.
"""
from __future__ import annotations
import argparse,json,re
from pathlib import Path
import p3_real_mos_bias_full_pvt as BASE
import p3_pll_extended_pvt_phase as P

DESIGNS=BASE.DESIGNS
VARIANTS=("default_3ps","trap_2ps","trap_1ps","gear_3ps")
CORNER="ss"
TEMP_C=85.
VDD=1.71

def substitute(src,variant):
    if variant=="default_3ps":return src
    step="1p" if variant=="trap_1ps" else "2p" if variant=="trap_2ps" else "3p"
    modified,n=re.subn(r"(?m)^tran 3p ([\d.]+)n uic$",
                       lambda m:f"tran {step} {m.group(1)}n uic",src)
    if n!=1:raise RuntimeError("Cannot identify original integration time grid")
    if variant=="gear_3ps":
        modified=modified.replace(".control",".options method=gear reltol=.001\n.control",1)
    return modified

def run(out,design,variant):
    if design not in DESIGNS or variant not in VARIANTS:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    before=P.deck
    try:
        P.deck=lambda c,t,v: substitute(before(c,t,v),variant)
        record=BASE.run(out/variant,design,CORNER,TEMP_C,VDD)
    finally:
        P.deck=before
    report={
      "design":design,"PVT":"SS 85C 1.71V","transient_solver":variant,
      "topology_and_MOS_bias_unchanged":True,
      "phase_std_ps":record["reference_phase_std_ps"],
      "frequency_window_span_MHz":record["last_disjoint_window_freq_drift_MHz"],
      "reference_slips":record["last_reference_cycle_slips"],
      "electrical_screen_pass":record["electrical_screen_passed"],
      "numerically_robust_global_design_proven":False,
      "original_P3_silicon":False,
    }
    file=out/variant/f"{design}_SS_hot_lowV_convergence.json"
    file.write_text(json.dumps(report,indent=2)+"\n")
    print(f"MOS_PVT_SOLVER design={design} variant={variant} "
          f"phaseSTD_ps={record['reference_phase_std_ps']} "
          f"threeWindowDrift_MHz={record['last_disjoint_window_freq_drift_MHz']} "
          f"no_slips={record['last_reference_cycle_slips']==0} "
          f"electricalPASS={record['electrical_screen_passed']}",flush=True)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--design",choices=DESIGNS,required=True)
    p.add_argument("--variant",choices=VARIANTS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_MOS_PVT_solver_sensitivity"))
    a=p.parse_args()
    run(a.out,a.design,a.variant)
