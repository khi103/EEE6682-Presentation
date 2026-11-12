#!/usr/bin/env python3
"""21-condition full-PVT electrical qualification of two common MOS PLLs.

Designs preselected by 9-scenario PVT sentinel (run 43237225515).
NO per-corner selection or individual initial-condition tuning:
 CP source/sink W scale = 82.5%, VCO +3fF/stage, startup 1.02V,
 RZERO = 1kOhm, identical MOS devices and 450MHz reference XSPICE.
 Only the common PMOS CP bias generator equation differs:
   tracked_091: pbias=VDD-0.91 V
   tracked_graded: pbias=.833333333*VDD-.625 V.
The generator is a behavioral voltage source, not a transistor-realized
supply reference. PVT is 15 process/temp combos at 1.8V plus 6
process-voltage corners at 27C. Actual 1.2us ngspice MOS transient,
frequency, nearest-reference phase, VCO gate ripple, reference-cycle
slips and last THREE DISJOINT frequency windows are checked.
Passing 21/21 would demonstrate a strong MODELED reference PLL
qualification, NOT original 2004 ASIC, jitter or physical data CDR.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import p3_pll_extended_pvt_phase as P
import p3_global_pvt_candidate as C

DESIGNS=("tracked_091","tracked_graded")
CORNERS=P.CORNERS
TEMPS=P.TEMPS
VDDS=P.VDDS

def run(out,design,corner,temp,vdd):
    if design not in DESIGNS or corner not in CORNERS or temp not in TEMPS or vdd not in VDDS:
        raise ValueError("Invalid defined PVT")
    out.mkdir(parents=True,exist_ok=True)
    before=P.deck
    try:
        P.deck=lambda c,t,v:C.patch(before(c,t,v),design)
        result=P.main(out/design,corner,temp,vdd)
    finally:
        P.deck=before
    r={
      "study":"one globally fixed physical MOS reference PLL design across PVT",
      "design":design,"corner":corner,"temperature_C":temp,
      "supply_V":vdd,"initial_bias_V":P.INITIAL,
      "MOS_switched_CP_width_scale":P.CP_SCALE,"MOS_VCO_extra_load_per_stage_fF":P.EXTRA_FF,
      "PFD":"XSPICE digital 450MHz reference PFD and divider",
      "bias":"supply-tracked ideal behavioral PMOS gate-voltage generator",
      "MOS_realized_bias_generator":False,
      "PLL_integrated_reference_lock_criterion_passed":result["passes_extended_screen"],
      "full_original_2004_P3_PLL_equivalent":False,
      "results":result,
    }
    name=f"{corner}_T{temp:+.0f}_V{vdd:.2f}".replace("+","p").replace("-","m").replace(".","p")
    (out/design/(name+"_confirmation.json")).write_text(json.dumps(r,indent=2)+"\n")
    m=result.get("measured",{})
    print(f"GLOBAL_PVT_CONFIRM design={design} corner={corner} T={temp:.0f} "
          f"vdd={vdd:.2f} f_GHz={m.get('vco_GHz')} "
          f"phase_std_ps={m.get('std_phase_ps')} "
          f"ripple_mVpp={m.get('physical_vco_gate_ripple_mV')} "
          f"drift_MHz={result.get('interwindow_frequency_span_MHz')} "
          f"ref_slip={result.get('window_checks',[{}])[-1].get('bad_four_to_one_reference_intervals')} "
          f"electricalPASS={r['PLL_integrated_reference_lock_criterion_passed']}",flush=True)
    return r

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--design",choices=DESIGNS,required=True)
    p.add_argument("--corner",choices=CORNERS,required=True)
    p.add_argument("--temp",type=float,choices=TEMPS,required=True)
    p.add_argument("--vdd",type=float,choices=VDDS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_fixed_PLL_full_PVT"))
    a=p.parse_args()
    run(a.out,a.design,a.corner,a.temp,a.vdd)
