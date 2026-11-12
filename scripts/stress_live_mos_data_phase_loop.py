#!/usr/bin/env python3
"""Cross-pattern, opposite-phase and gain stress for same-netlist data PLL.

Import the exact previously characterized received-data B-source/physical
MOS PLL testbench without altering its equations; vary ONLY test
conditions. PRBS31 control never uses transmitted labels. These are
characterization runs, not assertions of Fig.19 BBPD CDR lock.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "simulation"))
import p3_transistor_driver as TX
import p3_mos_reference_pll_live_data_phase_test as LIVE

def prbs31(n,seed=0x54C4EE17):
    mask=(1<<31)-1
    state=seed&mask
    if not state:
        raise ValueError("zero seed")
    bits=[]
    for _ in range(n):
        bits.append(state&1)
        feedback=((state>>30)^(state>>27))&1
        state=((state<<1)&mask)|feedback
    return bits

def main(out,pattern,gain,shift):
    if pattern not in ("prbs7","prbs31"):
        raise ValueError(pattern)
    original=TX.prbs7
    valid=LIVE.VALID_GAIN
    try:
        if pattern=="prbs31":
            TX.prbs7=lambda n:prbs31(n)
        LIVE.VALID_GAIN=tuple(sorted(set(valid+(gain,))))
        case_out=out/pattern
        result=LIVE.main(case_out,gain,shift)
        result["input_pattern"]=pattern
        result["pattern_seed"]="0x54C4EE17" if pattern=="prbs31" else "0x5D"
        print(f"DATA_CDR_STRESS pattern={pattern} gain_uA={gain*1e6:+.0f} "
              f"shift_UI={shift:+.2f} "
              f"physical_latch_errors={result['physical_rx']['bit_errors_including_unresolved']}/"
              f"{result['physical_rx']['samples_scored']}",flush=True)
        return result
    finally:
        TX.prbs7=original
        LIVE.VALID_GAIN=valid

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--pattern",choices=("prbs7","prbs31"),required=True)
    p.add_argument("--gain",type=float,required=True)
    p.add_argument("--shift-ui",type=float,required=True)
    p.add_argument("--out",type=Path,
          default=Path("results/spice/p3_physical_data_loop_stress"))
    args=p.parse_args()
    main(args.out,args.pattern,args.gain,args.shift_ui)
