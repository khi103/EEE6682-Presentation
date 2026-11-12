#!/usr/bin/env python3
"""Offline characterization of DATA phase offsets, NO receiver CDR feedback.

Find whether the locked reference PLL with a real 2-stage MOS clock-delay
path has any starting phase offsets that cause poor physical MOS latch
decisions. This is a *preregistered uniform offset sweep*, not a search
over known PRBS labels to program clock sampling. The seed and analogue
DUT bias are unchanged; only the TX burst start changes. These runs
identify challenge scenarios for a follow-up causal data-feedback test.
"""
from __future__ import annotations
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"simulation"))
import p3_live_mos_phase_servo as SERVO

SHIFTS=(-.85,-.65,-.45,-.25,-.05,.15,.55,.75,.95)

def main(shift):
    if shift not in SHIFTS:raise ValueError(shift)
    prior=SERVO.SHIFTS
    SERVO.SHIFTS=SHIFTS
    try:
        report=SERVO.main(Path("results/spice/p3_mos_phase_offset_baseline"),
                          0.,shift)
    finally:
        SERVO.SHIFTS=prior
    a=report["coverage_aware"]["holdout"]
    print(f"RECEIVER_NOFEEDBACK_PHASE_SWEEP offset_UI={shift:+.2f} "
          f"error={a['total_invalid']}/{a['expected']} "
          f"missing={a['missing']} wrong={a['wrong_regenerated']} "
          f"unresolved={a['unresolved']}",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--shift",type=float,choices=SHIFTS,required=True)
    a=p.parse_args()
    main(a.shift)
