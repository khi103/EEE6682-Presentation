#!/usr/bin/env python3
"""Experimental negative phase-DAC gain for long 512-bit physical MOS CDR.

Previous four-seed 1024-bit transient evidence showed seven-bit
counter unilaterally running from 63 to saturation 0, and a positive
3mV/code MOS delay gain actually increased all eight matched CDR
receiver error counts compared with zero feedback.

This isolates COUNTER-TO-PHYSICAL-MOS CLOCK SIGN (not detector topology):
sweep four predeclared negative mV/count polarities with the ORIGINAL
four-XOR XSPICE 7-bit counter, source patterns and physical MOS chain.
No source data labels enter the CDR logic; use same holdout 358 UI.
This is a sign diagnostic, not Fig19 original silicon reproduction.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import p3_512bit_mos_7bit_counter_cdr as BASE

GAINS=(-.5,-1.,-2.,-3.)
SEEDS=BASE.SEEDS
PHASES=BASE.SHIFTS

def run(out,seed,phase,negative):
    if seed not in SEEDS or phase not in PHASES or negative not in GAINS:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    original=BASE.STEP_MV
    try:
        BASE.STEP_MV=GAINS
        result=BASE.run(out,seed,phase,negative)
    finally:
        BASE.STEP_MV=original
    h=result.get("heldout",{})
    item={"seed_hex":hex(seed),"initial_phase_UI":phase,
          "negative_mV_per_counter_code":negative,
          "actual_180nm_MOS_actuator":True,
          "same_4xor_7bit_XSPICE_controller":True,
          "full_transient":result.get("source_status")=="simulated",
          "physical_receiver_holdout":h,
          "foundry_2004_original":False,
          "data_CDR_lock_proven":False}
    name=f"seed{seed:X}_phase{phase:+.2f}_step{negative:+.1f}".replace("+","p").replace("-","m").replace(".","p")
    (out/(name+"_sign_test.json")).write_text(json.dumps(item,indent=2)+"\n")
    print(f"CDR_NEGATIVE_GAIN seed={seed:#x} phase={phase:+.2f} "
          f"mV_per_code={negative:.1f} status={result.get('source_status')} "
          f"invalid={h.get('total_invalid')}/{h.get('expected')} "
          f"missing={h.get('missing')} wrong={h.get('wrong_regenerated')} "
          f"unresolved={h.get('unresolved')}",flush=True)
    return item

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--seed",type=lambda x:int(x,0),choices=SEEDS,required=True)
    p.add_argument("--phase",type=float,choices=PHASES,required=True)
    p.add_argument("--gain",type=float,choices=GAINS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_512_neg_gain_MOS_CDR"))
    a=p.parse_args()
    run(a.out,a.seed,a.phase,a.gain)
