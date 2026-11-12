#!/usr/bin/env python3
"""Common-startup-voltage PVT study for fixed physical MOS reference PLL.

The earlier 3fF added node-cap / 0.825 or 0.85 global CP strength
combination passed FF but did not capture SS under a 0.96V start.
The existing physical VCO has very different preferred control bias:
FF around 0.8V and SS around 1.13V. This experiment changes ONE shared
startup voltage across ALL five corners to test whether the apparent
FF/SS conflict is just a start-bias acquisition basin issue.

All MOS CP and ring device sizes, XSPICE PFD/4, 450MHz reference,
1.8V supply and RC loop filter are fixed per scale. NO per-corner
startup tuning is allowed within a test configuration.

Deterministic PDK corner transient only; not original 2004 silicon.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import p3_global_vco_cap_pll as PREV

CORNERS=PREV.CORNERS
SCALES=(.825,.85,.875)
STARTS=(.90,1.02,1.10)
CAP_FF=3.

def run(out,corner,scale,initial):
    if corner not in CORNERS or scale not in SCALES or initial not in STARTS:
        raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    old_scale,old_start=PREV.PUMP_WIDTH_SCALE,PREV.INITIAL_BIAS
    try:
        PREV.PUMP_WIDTH_SCALE=scale
        PREV.INITIAL_BIAS=initial
        result=PREV.run(out,corner,CAP_FF)
    finally:
        PREV.PUMP_WIDTH_SCALE,PREV.INITIAL_BIAS=old_scale,old_start
    m=result.get("measured",{})
    result.update({"common_pump_strength":scale,
                   "common_startup_control_V":initial,
                   "corner_tuning_done":False,
                   "added_VCO_node_cap_fF":CAP_FF})
    file=out/f"{corner}_src{scale:.3f}_start{initial:.2f}.json"
    file.write_text(json.dumps(result,indent=2)+"\n")
    print(f"COMMON_STARTUP_PVT corner={corner} pump={scale:.3f} "
          f"start={initial:.2f} VCO={m.get('vco_GHz')} "
          f"phaseSTD_ps={m.get('std_phase_ps')} "
          f"gateRipple_mV={m.get('physical_vco_gate_ripple_mV')} "
          f"qualifies={result['electrical_lock_screen_pass']}",flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--corner",choices=CORNERS,required=True)
    p.add_argument("--scale",type=float,choices=SCALES,required=True)
    p.add_argument("--start",type=float,choices=STARTS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_common_start_MOS_PLL"))
    a=p.parse_args()
    run(a.out,a.corner,a.scale,a.start)
