#!/usr/bin/env python3
"""Held-out, coverage-aware PRBS31 MOS-FFE evidence audit.

Postprocess physical MOS receiver CSV files from a locked 450-MHz XSPICE
reference PLL. Reconstruct known transmitted PRBS31 bits ONLY for
post-run evaluation, use one common integer lag fitted on first 126
symbols, then score 358 unseen transmitted UI windows. Missing UI
samples are errors; duplicates are explicitly tracked, never silently
reused to inflate the result.
"""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import audit_physical_mos_ffe_coverage as AUDIT

def prbs31(n=512,seed=0x54C4EE17):
    mask=(1<<31)-1
    state=seed&mask
    out=[]
    for _ in range(n):
        out.append(state&1)
        fb=((state>>30)^(state>>27))&1
        state=((state<<1)&mask)|fb
    return out

def run(input_dir,out):
    original=(AUDIT.BITS,AUDIT.TRAIN_START,AUDIT.TRAIN_END,
              AUDIT.TEST_START,AUDIT.TEST_END,AUDIT.prbs7)
    try:
        AUDIT.BITS=512
        AUDIT.TRAIN_START=18
        AUDIT.TRAIN_END=144
        AUDIT.TEST_START=144
        AUDIT.TEST_END=502
        AUDIT.prbs7=prbs31
        output=AUDIT.main(input_dir,out)
        output["simulation_source_run"]=43173360810
        output["input_pattern"]="PRBS31, 512 bits, seed 0x54C4EE17"
        (out/"heldout_coverage_aware_ffe.json").write_text(
            json.dumps(output,indent=2)+"\n")
        for k,item in output["comparison"].items():
            value=item["coverage_aware_floor_score"]
            print(f"PRBS31_FINAL_AUDIT {k} "
                  f"score={value['invalid_or_wrong_UI']}/{value['expected_unique_bits']} "
                  f"missing={value['missing_UI']} "
                  f"duplicates={value['duplicate_extra_sample_events']} "
                  f"wrong={value['wrong_regenerated_UI']}",flush=True)
        return output
    finally:
        (AUDIT.BITS,AUDIT.TRAIN_START,AUDIT.TRAIN_END,
         AUDIT.TEST_START,AUDIT.TEST_END,AUDIT.prbs7)=original

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--in-dir",type=Path,required=True)
    p.add_argument("--out",type=Path,
          default=Path("results/audit/p3_prbs31_mos_ffe_heldout"))
    a=p.parse_args()
    run(a.in_dir,a.out)
