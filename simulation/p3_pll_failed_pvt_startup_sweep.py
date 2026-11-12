#!/usr/bin/env python3
"""Diagnostic common-design startup-bias sweep at actual PLL PVT failures.

Followup to executed 21-case 180nm XSPICE/MOS PLL survey:
run 43214358821 had confirmed electrical failures in
FF -20C, FF 27C 1.89V, SS -20C, SS 27C 1.71V and strict
SS 27C late-frequency stability. Keep MOS source/sink sizing fixed
at 82.5%, additional MOS VCO load at 3fF/stage, same RC loop filter,
same external 450MHz reference and voltage-dependent DAC gate rails.

Sweep one startup voltage shared over all failure scenarios, not
a per-corner optimized permanent design. Measure actual ngspice
frequency, phase, VCO gate ripple, final reference-cycle slip, and
three DISJOINT final 80ns frequency windows. A startup intervention
that succeeds in one PVT condition does not prove a full robust chip.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import p3_pll_extended_pvt_phase as P

SCENARIOS={
  "ff_cold":("ff",-20.,1.8),
  "ff_vdd_high":("ff",27.,1.89),
  "ss_cold":("ss",-20.,1.8),
  "ss_vdd_low":("ss",27.,1.71),
  "ss_nominal_drift":("ss",27.,1.8),
  "tt_nominal_control":("tt",27.,1.8),
}
STARTS=(.90,1.02,1.10,1.20)

def run(out,scenario,start):
    if scenario not in SCENARIOS or start not in STARTS:
        raise ValueError("Unsupported condition")
    corner,temp,vdd=SCENARIOS[scenario]
    old=P.INITIAL
    try:
        P.INITIAL=start
        result=P.main(out/scenario/f"start_{start:.2f}",corner,temp,vdd)
    finally:
        P.INITIAL=old
    result["scenario"]=scenario
    result["experimental_startup_bias_V"]=start
    result["external_PLL_reference"]=450e6
    result["original_chip_not_reconstructed"]=True
    output=out/scenario/f"start_{start:.2f}"/"startup_audit.json"
    output.write_text(json.dumps(result,indent=2)+"\n")
    print(
      f"STARTUP_FAILURE_PVT scenario={scenario} init_V={start:.2f} "
      f"frequency_GHz={result.get('measured',{}).get('vco_GHz')} "
      f"phase_std_ps={result.get('measured',{}).get('std_phase_ps')} "
      f"drift_MHz={result.get('interwindow_frequency_span_MHz')} "
      f"no_slips={result.get('screen',{}).get('no_ref_interval_cycle_slip_last_80ns')} "
      f"passes_corrected_screen={result['passes_extended_screen']}",flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--scenario",choices=SCENARIOS,required=True)
    p.add_argument("--start",type=float,choices=STARTS,required=True)
    p.add_argument("--out",type=Path,
       default=Path("results/spice/p3_PVT_failed_startup_analysis"))
    args=p.parse_args()
    run(args.out,args.scenario,args.start)
