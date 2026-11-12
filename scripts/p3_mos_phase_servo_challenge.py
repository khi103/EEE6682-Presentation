#!/usr/bin/env python3
"""Held-out data-only MOS-phase servo challenge at two confirmed bad phases.

The preregistered zero-feedback phase scan (GitHub Actions 43175884456)
found 29 incorrectly regenerated receiver samples in a 156-UI holdout
at -0.05 UI and +0.95 UI, with the physical delay bias fixed at 1.10V.

These are intentionally hard conditions for checking whether the
behavioral analog RX-transition phase detector in the SAME SPICE deck
can retune the ACTUAL MOS current-starved inverter phase delay. Gain
zero is the primary negative control. All data labels remain excluded
from every physical phase and reference-PLL feedback path.
"""
from __future__ import annotations
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"simulation"))
import p3_live_mos_phase_servo as SERVO

CHALLENGES=(-.05,.95)
GAINS=(-400.,-200.,-80.,0.,80.,200.,400.)

def run(shift,gain):
    if shift not in CHALLENGES or gain not in GAINS:raise ValueError
    original=(SERVO.SHIFTS,SERVO.GAINS_UA)
    try:
        SERVO.SHIFTS=CHALLENGES
        SERVO.GAINS_UA=GAINS
        result=SERVO.main(Path("results/spice/p3_MOS_phase_servo_challenge"),gain,shift)
    finally:
        SERVO.SHIFTS,SERVO.GAINS_UA=original
    h=result["coverage_aware"]["holdout"]
    print(f"PHYSICAL_MOS_PHASE_CDR_CHALLENGE shift_UI={shift:+.2f} "
          f"gain_uA={gain:+.0f} "
          f"wrong={h['wrong_regenerated']} "
          f"missing={h['missing']} "
          f"unresolved={h['unresolved']} "
          f"total={h['total_invalid']}/{h['expected']}",flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--shift",type=float,choices=CHALLENGES,required=True)
    p.add_argument("--gain",type=float,choices=GAINS,required=True)
    a=p.parse_args()
    run(a.shift,a.gain)
