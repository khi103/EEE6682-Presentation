#!/usr/bin/env python3
"""Fine MOS seven-bit data-CDR gain sweep on full 512-bit PRBS31 packet.

Coarse counter-to-physical-phase gain 0/2/4/8 mV per counter code
reduced physical MOS receiver errors but had no universally locked
phase and high gains caused many missing samples. This follow-up
interpolates 0.5/1.0/1.5/3.0mV per code with the SAME two independent
PRBS31 seeds and two adverse initial phases.

Actual XSPICE digital four-XOR BBPD and 128-state saturating up/down
counter, MOS TX/RX and MOS clock-delay cell remain unchanged.
Strict complete waveform, physical clock-cycle coverage, training
and held-out errors are preserved from the parent challenge.
This is not an exact replica of 2004 Fig19 or BER/jitter silicon proof.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import p3_512bit_mos_7bit_counter_cdr as CORE

SEEDS=CORE.SEEDS
SHIFTS=CORE.SHIFTS
STEPS_MV=(.5,1.,1.5,3.)

def run(out,seed,phase,step):
    if seed not in SEEDS or phase not in SHIFTS or step not in STEPS_MV:raise ValueError
    old=CORE.STEP_MV
    try:
        CORE.STEP_MV=STEPS_MV
        r=CORE.run(out,seed,phase,step)
    finally:
        CORE.STEP_MV=old
    h=r["heldout"]
    print(
      f"FINE_MOS_CDR_GAIN seed={seed:#x} phase_UI={phase:+.2f} "
      f"step_mV={step:.2f} status={r['source_status']} "
      f"invalid={h.get('total_invalid')}/{h.get('expected')} "
      f"missing={h.get('missing')} wrong={h.get('wrong_regenerated')} "
      f"unresolved={h.get('unresolved')}",flush=True)
    return r

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--seed",type=lambda x:int(x,0),choices=SEEDS,required=True)
    p.add_argument("--phase",type=float,choices=SHIFTS,required=True)
    p.add_argument("--step",type=float,choices=STEPS_MV,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_fine_512_MOS_CDR"))
    a=p.parse_args()
    run(a.out,a.seed,a.phase,a.step)
