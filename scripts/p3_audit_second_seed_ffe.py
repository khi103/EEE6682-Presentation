#!/usr/bin/env python3
"""Repeat common-frame MOS FFE alpha/eye audit with a held-out PRBS31 seed."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"simulation"))
import p3_long_predriver_prbs31 as SOURCE
import p3_fullmos_ffe_alpha_audit as A
SEED=0x13572468

def main(source,out):
    original=A.BITS
    try:
        A.BITS=SOURCE.prbs31(512,seed=SEED)
        result=A.run(source,out)
    finally:
        A.BITS=original
    report={"independent_PRBS31_seed_hex":hex(SEED),
            "all_alphas_shared_frame_and_phase":True,
            "earlier_seed_used_for_parameter_discovery":hex(0x54C4EE17),
            "second_seed_out_of_sample_pattern_test":True,
            "original_2004_asic_equivalence":False,
            "results":result}
    (out/"independent_second_seed_summary.json").write_text(
         json.dumps(report,indent=2)+"\n")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--in-dir",type=Path,required=True)
    p.add_argument("--out",type=Path,default=Path("results/audit/p3_second_seed_ffe"))
    a=p.parse_args()
    main(a.in_dir,a.out)
