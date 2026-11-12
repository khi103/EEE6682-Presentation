#!/usr/bin/env python3
"""Stress Fig.19-inspired two-pass MOS-BBPD timing recovery with PRBS31.

The original regression uses a 512-bit PRBS7 waveform, repeating its
127-bit base pattern. This *independent* stress run uses PRBS31 and a
different deterministic seed, plus +/-2000ppm clock offsets. This is
still a two-pass MOS/Python/MOS co-simulation; the actuated receiver
clock is an IDEAL SPICE PWL, not a physical VCO-feedback loop.

All MOS TX / RX and 7-bit MOS charge-pump DC lookup devices are
transistor-level DB HiTek 180-nm PDK simulations. The Python Fig19-like
four-XOR phase detector sees only RX voltage samples, not true bits.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulation"))
import p3_transistor_driver as TX
import p3_fig19_bbpd_mos_cosim as BBPD

NEW_TESTS=(
    ("hard_start_plus2000ppm_on",127,4,+2000.),
    ("hard_start_plus2000ppm_off",127,0,+2000.),
    ("early_start_minus2000ppm_on",15,4,-2000.),
    ("early_start_minus2000ppm_off",15,0,-2000.),
)

def prbs31(n, seed):
    """PRBS31 x^31+x^28+1 (left-shift feedback convention)."""
    state=seed & ((1<<31)-1)
    if state==0:
        raise ValueError("All-zero LFSR seed")
    result=[]
    for _ in range(n):
        result.append(state & 1)
        feedback=((state >> 30) ^ (state >> 27)) & 1
        state=((state<<1)&((1<<31)-1)) | feedback
    return result

def main(out,seed):
    out.mkdir(parents=True,exist_ok=True)
    original = TX.prbs7
    old_tests = BBPD.TESTS
    try:
        TX.prbs7 = lambda n: prbs31(n,seed)
        BBPD.TESTS = old_tests + NEW_TESTS
        summary=BBPD.run(out)
    finally:
        TX.prbs7 = original
        BBPD.TESTS = old_tests

    comparisons={}
    cases=summary["results"]
    pairs=(
      ("+1000ppm hard start", "late_hard_phase_div4_plus1000ppm",
       "late_hard_phase_fixed_plus1000ppm"),
      ("+2000ppm hard start", "hard_start_plus2000ppm_on",
       "hard_start_plus2000ppm_off"),
      ("-2000ppm early start", "early_start_minus2000ppm_on",
       "early_start_minus2000ppm_off"),
    )
    for label,on,off in pairs:
        lhs=cases[on]["mos_rx"]
        rhs=cases[off]["mos_rx"]
        comparisons[label]={
           "CDR_ON_errors":lhs["total_errors_including_unresolved"],
           "CDR_OFF_errors":rhs["total_errors_including_unresolved"],
           "evaluated":lhs["evaluated_bits"],
           "CDR_reduced_errors":lhs["total_errors_including_unresolved"] <
                                rhs["total_errors_including_unresolved"],
        }
        print(
          f"PRBS31_STRESS seed={seed} {label}: "
          f"CDR_ON={comparisons[label]['CDR_ON_errors']}/"
          f"{comparisons[label]['evaluated']}, "
          f"OFF={comparisons[label]['CDR_OFF_errors']}/"
          f"{comparisons[label]['evaluated']}",
          flush=True
        )
    summary["independent_stress"]={
      "prbs_type":"PRBS31",
      "prbs31_seed_hex":f"{seed:#x}",
      "mos_pdk":"DB HiTek 180nm SVT",
      "comparisons":comparisons,
      "nonphysical_phase_actuator":"normalized assumed 350ps current-to-phase and ideal PWL clock",
      "actual_simultaneous_physical_CDR":False,
    }
    (out/"prbs31_cdr_mos_extended_summary.json").write_text(
         json.dumps(summary,indent=2)+"\n")
    return summary

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--seed",type=lambda x:int(x,0),required=True)
    p.add_argument("--out",type=Path,
          default=Path("results/spice/p3_prbs31_mos_bbpd"))
    args=p.parse_args()
    main(args.out,args.seed)
