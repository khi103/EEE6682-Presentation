#!/usr/bin/env python3
"""Fine PVT pump-strength overlap search for fixed 3fF 180nm MOS VCO.

Previous common-parameter tests showed FF qualifies at global scale
0.80 whereas SS qualifies at 0.90. TT, FS, and SF qualify at both;
hence sweep 0.825/0.850/0.875 on ALL five corners with one identical
0.96V initial bias and 3fF added at each VCO stage. Do not infer a
global pass until every corner of one common scale meets the electrical
lock screen in the actual ngspice traces.

This is deterministic 27C process-corner reference PLL characterization,
not the original silicon's PVT, jitter, mismatch or data CDR.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import p3_common_cap_pump_pvt as COMMON

CORNER=COMMON.CORNERS
SCALES=(.825,.85,.875)

def main(corner,scale,out):
    if corner not in CORNER or scale not in SCALES:raise ValueError
    before=COMMON.SCALES
    try:
        COMMON.SCALES=SCALES
        result=COMMON.run(out,corner,scale)
    finally:
        COMMON.SCALES=before
    m=result.get("measured",{})
    print(f"FINE_GLOBAL_MOS_PLL corner={corner} global_pump_scale={scale:.3f} "
          f"VCO_GHz={m.get('vco_GHz')} phase_STD_ps={m.get('std_phase_ps')} "
          f"gate_ripple_mV={m.get('physical_vco_gate_ripple_mV')} "
          f"lock={result['electrical_lock_screen_pass']}",flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--corner",choices=CORNER,required=True)
    p.add_argument("--scale",type=float,choices=SCALES,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_fine_common_MOS_PLL"))
    a=p.parse_args()
    main(a.corner,a.scale,a.out)
