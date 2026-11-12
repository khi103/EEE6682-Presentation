#!/usr/bin/env python3
"""Sweep negative receiver clock offsets in independent PRBS31 MOS BBPD.

The paper-inspired Fig19-like four-XOR Python CDR drives ideal PWL
clock sources into real DB HiTek MOS receiver latches. Compare +/- PPM
and divider choices without changing the detector or phase law. This
isolates the observed -2000ppm failure mechanism and avoids labeling a
one-sided successful CDR test as a universal lock range.
"""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"simulation"))
import p3_transistor_driver as TX
import p3_fig19_bbpd_mos_cosim as BBPD

def bits31(n,seed):
    state=seed&((1<<31)-1)
    out=[]
    for _ in range(n):
        out.append(state&1)
        fb=((state>>30)^(state>>27))&1
        state=((state<<1)&((1<<31)-1))|fb
    return out

SWEEP=(
 ("minus500_on",15,4,-500.),
 ("minus500_off",15,0,-500.),
 ("minus1000_on",15,4,-1000.),
 ("minus1000_off",15,0,-1000.),
 ("minus1500_on",15,4,-1500.),
 ("minus1500_off",15,0,-1500.),
 ("minus2000_div2",15,2,-2000.),
 ("minus2000_div8",15,8,-2000.),
 ("minus2000_div16",15,16,-2000.),
 ("minus2000_start100_div4",100,4,-2000.),
)

def main(out,seed):
    original,tests=TX.prbs7,BBPD.TESTS
    try:
        TX.prbs7=lambda n:bits31(n,seed)
        BBPD.TESTS=tests+SWEEP
        data=BBPD.run(out)
    finally:
        TX.prbs7,BBPD.TESTS=original,tests
    results={}
    for name,*_ in SWEEP:
        c=data["results"][name]
        m=c["mos_rx"]
        results[name]={
          "errors":m["total_errors_including_unresolved"],
          "unresolved":m["unresolved_latch_samples"],
          "compared":m["evaluated_bits"],
          "last_code":c["last_counter_code"]
        }
        print(f"NEGATIVE_PPM_CDR {name} "
              f"errors={results[name]['errors']}/{results[name]['compared']} "
              f"unresolved={results[name]['unresolved']} "
              f"final_code={results[name]['last_code']}",flush=True)
    comparison={}
    for p in (500,1000,1500):
        on=results[f"minus{p}_on"]
        off=results[f"minus{p}_off"]
        comparison[f"minus{p}ppm"]={
          "CDR_ON":on["errors"],
          "CDR_OFF":off["errors"],
          "CDR_improved":on["errors"]<off["errors"]
        }
    (out/"negative_ppm_PRBS31_MOS_BBPD.json").write_text(
        json.dumps({"seed_hex":f"{seed:#x}","new_cases":results,
                    "comparison":comparison,
                    "physical_same_SPICE_loop":False,
                    "charge_pump_to_phase_transfer_assumed":True,
                    "note":"Negative PPM stresses algorithm, not a proof of original 2004 silicon CDR"},indent=2)+"\n")
    return comparison

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--seed",type=lambda x:int(x,0),default=0x54C4EE17)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_prbs31_negative_ppm"))
    a=p.parse_args()
    main(a.out,a.seed)
