#!/usr/bin/env python3
"""512-bit PRBS31 physical MOS reference-PLL FFE validation.

Runs the existing P3 transistor TX, 450MHz reference PLL with switched
MOS CP and physical VCO, and half-rate MOS RX. The previous exploratory
256-bit PRBS7 run repeats a 127-bit pattern; this run exercises 512
successive PRBS31 bits and identical 0/.15/.30/.45 FFE choices.

No transmitted labels are used by any PLL phase/frequency detector.
Reported errors are diagnostic, not measured BER or a data CDR.
"""
from __future__ import annotations
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"simulation"))
import p3_transistor_driver as TX
import p3_reference_pll_integrated_mos_link as LINK
import p3_reference_pll_ffe_ablation as ABLA

def prbs31(n,seed=0x54C4EE17):
    mask=(1<<31)-1
    x=seed&mask
    if not x:raise ValueError("Invalid zero seed")
    bits=[]
    for _ in range(n):
        bits.append(x&1)
        fb=((x>>30)^(x>>27))&1
        x=((x<<1)&mask)|fb
    return bits

def main(out,alpha):
    fn=TX.prbs7
    old_n=LINK.BITS
    try:
        TX.prbs7=lambda n:prbs31(n)
        LINK.BITS=512
        result=ABLA.run(out,alpha)
        m=result["electrical_diagnostics"]
        print(
          f"PRBS31_PHYSICAL_FFE alpha={alpha:.2f} "
          f"analog_margin_p05={m['p05_signed_RX_margin_mV']}mV "
          f"physical_MOS_latch_errors={m['total_errors_including_unresolved']}/"
          f"{m['total_clock_samples']} "
          f"unique={m['different_symbol_indices']} "
          f"duplicates={m['duplicate_symbol_index_events']}",flush=True)
        return result
    finally:
        TX.prbs7=fn
        LINK.BITS=old_n

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--alpha",type=float,required=True)
    a.add_argument("--out",type=Path,
       default=Path("results/spice/p3_prbs31_refpll_ffe"))
    x=a.parse_args()
    main(x.out,x.alpha)
