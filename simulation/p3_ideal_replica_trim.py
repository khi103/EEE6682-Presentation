#!/usr/bin/env python3
"""A *hypothetical* code-7 replica calibration of independent NMOS P3 TX.

We do NOT implement the paper's physical feedback. For each PVT corner we
numerically choose a common width/finger multiplier that restores 50 ohms
at the replica code-7 / fixed VREF test point, then check other output
codes at their ACTUAL loaded DC voltages. The latter exposes nonlinear
output conductance which a single calibration point cannot remove.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
import shutil
from pathlib import Path
import p3_transistor_driver as TX

CORNERS = TX.CORNER_NAMES
TEST_CODES = (0, 3, 7, 12, 15)
TARGET = 50.0
REF_CODE = 7

def calibrate(runner, corner: str, base_wu: float, base_wd: float):
    lo,hi = 0.55,1.75
    hist=[]
    def test(scale):
        z=runner.rout(REF_CODE,base_wu*scale,base_wd*scale,corner)
        hist.append([scale,z])
        return z
    a,b=test(lo),test(hi)
    if not a>=TARGET>=b:
        # Do not hide failed bracket; report unable to calibrate.
        best=min(hist,key=lambda r:abs(r[1]-TARGET))
        return {"bracketed":False,"scale":best[0],"rout_ref":best[1],"history":hist}
    for _ in range(12):
        mid=(lo+hi)/2
        z=test(mid)
        if z>TARGET:lo=mid
        else:hi=mid
    best=min(hist,key=lambda r:abs(r[1]-TARGET))
    return {"bracketed":True,"scale":best[0],"rout_ref":best[1],"history":hist}

def process(out: Path):
    out.mkdir(parents=True,exist_ok=True)
    source=json.loads((out/"driver_summary.json").read_text())
    wu=source["calibration"]["up"]["unit_w_um"]
    wd=source["calibration"]["down"]["unit_w_um"]
    w=TX.ENGINE_DIR/"p3_calibration"
    runner=TX.SpiceRunner(w)
    for corner in CORNERS:
        src=TX.model_path(corner)
        if not (w/src.name).exists() or src.stat().st_mtime>(w/src.name).stat().st_mtime:
            shutil.copy2(src,w/src.name)

    data=[];adjustments={}
    for corner in CORNERS:
        adj=calibrate(runner,corner,wu,wd)
        adjustments[corner]=adj
        for label,scale in [("fixed_TT_sizing",1.0),("ideal_per_corner_retrim",adj["scale"])]:
            for code in TEST_CODES:
                up,dn=wu*scale,wd*scale
                v=runner.dc(code,up,dn,corner)
                rout_ideal=runner.rout(code,up,dn,corner)
                rout_loaded=TX.rout_at_operating_voltage(
                    runner,code,up,dn,corner,v["pad_V"])
                data.append({
                  "corner":corner,"configuration":label,"code":code,
                  "scale_from_TT":scale,
                  "unit_pullup_width_um":up,"unit_pulldown_width_um":dn,
                  "vout_V":v["pad_V"],"rout_at_vref_ohm":rout_ideal,
                  "rout_at_actual_pad_ohm":rout_loaded,
                  "abs_error_at_vref_pct":abs(rout_ideal/TARGET-1)*100,
                  "abs_error_at_actual_pad_pct":abs(rout_loaded/TARGET-1)*100,
                  "p_signaling_supply_mW":max(0,-v["driver_supply_A"]*TX.V_SIGNAL*1e3)
                })
        print(f"{corner.upper()}: replica 50-ohm trim scale={adj['scale']:.4f},"
              f" Rref={adj['rout_ref']:.2f}, bracketed={adj['bracketed']}",
              flush=True)

    with (out/"ideal_replica_trim.csv").open("w",newline="") as f:
        wr=csv.DictWriter(f,fieldnames=list(data[0]))
        wr.writeheader();wr.writerows(data)
    comparison={}
    for c in CORNERS:
        comp={}
        for label in ("fixed_TT_sizing","ideal_per_corner_retrim"):
            rr=[x for x in data if x["corner"]==c and x["configuration"]==label]
            comp[label]={
              "mean_pct_error_fixed_reference":sum(x["abs_error_at_vref_pct"] for x in rr)/len(rr),
              "max_pct_error_fixed_reference":max(x["abs_error_at_vref_pct"] for x in rr),
              "mean_pct_error_actual_pad":sum(x["abs_error_at_actual_pad_pct"] for x in rr)/len(rr),
              "max_pct_error_actual_pad":max(x["abs_error_at_actual_pad_pct"] for x in rr),
              "nominal_power_mean_mW":sum(x["p_signaling_supply_mW"] for x in rr)/len(rr)
            }
        comparison[c]=comp
    result={
      "status":"passed_ideal_replica_width_authority_test",
      "measurement":"5 codes per corner, fixed 0.25-V replica and each actual loaded pad voltage",
      "trim":"hypothetical continuous width scale; actual MOS fingers and feedback NOT modeled",
      "original_widths_um":{"up":wu,"down":wd},
      "per_corner_calibration":adjustments,
      "per_corner_comparison":comparison,
      "ngspice_calls":runner.calls,
      "limitations":[
        "Hypothetical per-corner width tuning is not a physical closed-loop controller",
        "Replica is code 7 only and at fixed VREF, not all 16 codes/voltage states",
        "Continuous width scaling is not discrete hardware, and bin changes may affect interpolation",
        "Actual 2004 Fig. 8 feedback, predriver/slew, process model and power not reconstructed"
      ]
    }
    (out/"ideal_replica_trim.json").write_text(json.dumps(result,indent=2)+"\n")
    assert all(v["bracketed"] for v in adjustments.values()),"Not all corners could bracket 50 ohms"
    assert all(abs(v["rout_ref"]-50)<1. for v in adjustments.values())
    assert comparison["ss"]["ideal_per_corner_retrim"]["mean_pct_error_fixed_reference"] < comparison["ss"]["fixed_TT_sizing"]["mean_pct_error_fixed_reference"]
    print("PASS: All PVT corners tuned nominally, loaded-point residual measured",flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=TX.DEFAULT_OUT)
    a=p.parse_args()
    process(a.out)
