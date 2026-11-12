#!/usr/bin/env python3
"""1024-bit independent heldout MOS data-CDR validation with four PRBS31 seeds.

The existing one-SPICE XSPICE four-XOR BBPD + true 128-state 7-bit
saturating up/down counter, DAC-to-actual-MOS clock-delay cell, 450MHz
reference XSPICE PLL, transistor MOS VCO/charge pump, MOS TX and RX
regenerative latches are unchanged. This is a LONGER, independent
4-seed pattern stress, not new circuitry.

Fixed, pre-declared controls:
  two adverse start phases (-0.05, +0.95 UI)
  physical MOS clock bias per counter code: 0 vs 3mV/code
  four PRBS31 seeds (not used by CDR, only TX and postrun scoring)
  TRAIN [18,256), HOLDOUT [256,1014) = 758 heldout symbols
  count missing, duplicated, unregenerated, erroneous MOS samples
  strict 1024-bit FULL ngspice transient completion requirement.

Do not infer BER<1e-12 from hundreds of bits and do not claim the
original 2004 Fig19 transistor/pins/phase DAC implementation.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import p3_512bit_mos_7bit_counter_cdr as BASE

SEEDS=(0x54C4EE17,0x13572468,0x2468ACE1,0x41357268)
SHIFTS=(-.05,.95)
STEPS=(0.,3.)
BITS=1024
TRAIN=(18,256)
HOLD=(256,1014)

def run(out,seed,phase,step):
    if seed not in SEEDS or phase not in SHIFTS or step not in STEPS:raise ValueError
    original=(BASE.SEEDS,BASE.CORE.SEEDS,BASE.STEP_MV,BASE.N_BITS,BASE.TRAIN,BASE.TEST)
    try:
        BASE.SEEDS=SEEDS
        BASE.CORE.SEEDS=SEEDS
        BASE.STEP_MV=STEPS
        BASE.N_BITS=BITS
        BASE.TRAIN=TRAIN
        BASE.TEST=HOLD
        report=BASE.run(out,seed,phase,step)
    finally:
        (BASE.SEEDS,BASE.CORE.SEEDS,BASE.STEP_MV,BASE.N_BITS,BASE.TRAIN,BASE.TEST)=original
    h=report["heldout"]
    summary={"source":"1024-bit true XSPICE seven-bit counter and MOS receiver",
             "seed":hex(seed),"start_UI":phase,"step_mV_per_code":step,
             "heldout_bits_expected":HOLD[1]-HOLD[0],
             "actually_simulated_1024bits":report["source_status"]=="simulated",
             "physical_7bit_counter":True,
             "physical_180nm_MOS_delay_actuator":True,
             "MOS_RX":h,
             "counter":report["counter"],
             "original_P3_Fig19_reproduced":False,
             "BER_statistical_proof":False,
             "data_CDR_lock_proven":False}
    tag=f"seed_{seed:X}_phase{phase:+.2f}_step{step:.1f}".replace("+","p").replace("-","m").replace(".","p")
    (out/f"{tag}_independent1024.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(f"MOS_1024_CDR seed={seed:#x} phase_UI={phase:+.2f} "
          f"step_mV={step:.1f} status={report['source_status']} "
          f"invalid={h.get('total_invalid')}/{h.get('expected')} "
          f"missing={h.get('missing')} unresolved={h.get('unresolved')} "
          f"wrong={h.get('wrong_regenerated')}",flush=True)
    return summary

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--seed",type=lambda x:int(x,0),choices=SEEDS,required=True)
    p.add_argument("--phase",type=float,choices=SHIFTS,required=True)
    p.add_argument("--step",type=float,choices=STEPS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_1024bit_MOS_counter_CDR"))
    a=p.parse_args()
    run(a.out,a.seed,a.phase,a.step)
