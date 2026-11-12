#!/usr/bin/env python3
"""Second-stage common-parameter MOS PLL PVT search after FS recovery.

A first physical CMOS experiment used fixed 3fF extra load per VCO
stage and 75%-strength MOS charge pump: TT FF FS SF qualified, SS did
not. Here we keep that EXACT physical VCO size/load and common 0.96V
start, but change one globally shared MOS pump-strength parameter.
All five PDK corners are tested independently for each candidate, so
a failure in any one corner prevents a full-PVT pass.

The resulting 'lock screen' is limited to deterministic reference
phase/frequency/ripple in 1.2us of ngspice at 27C. It is NOT original
2004 silicon, noise/mismatch/voltage PVT, or in-circuit data CDR.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import p3_global_vco_cap_pll as PREV

CORNERS=PREV.CORNERS
SCALES=(.8,.9,1.0,1.1,1.25)
CAP_FF=3.

def run(out,corner,scale):
    if corner not in CORNERS or scale not in SCALES:raise ValueError
    original=PREV.PUMP_WIDTH_SCALE
    try:
        PREV.PUMP_WIDTH_SCALE=scale
        result=PREV.run(out,corner,CAP_FF)
    finally:
        PREV.PUMP_WIDTH_SCALE=original
    # PREV.run stores at a cap/corner path; each matrix run in its
    # isolated GitHub Actions checkout, so there are no collisions.
    m=result.get("measured",{})
    print(f"COMMON_CAP_PUMP_PVT corner={corner} pump_scale={scale} "
          f"extra_cap_per_stage_fF={CAP_FF} "
          f"f_GHz={m.get('vco_GHz')} "
          f"phase_std_ps={m.get('std_phase_ps')} "
          f"ripple_mVpp={m.get('physical_vco_gate_ripple_mV')} "
          f"controller_last_V={m.get('control_last_V')} "
          f"pass={result['electrical_lock_screen_pass']}",flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--corner",choices=CORNERS,required=True)
    p.add_argument("--scale",type=float,choices=SCALES,required=True)
    p.add_argument("--out",type=Path,
       default=Path("results/spice/p3_common_cap_pump_PVT"))
    a=p.parse_args()
    run(a.out,a.corner,a.scale)
