#!/usr/bin/env python3
"""Compare an ACTUAL HSPICE CSV to the executed ngspice MOS I-V benchmark.

Never substitute ngspice data itself as an alleged HSPICE reference.
Missing reference is a BLOCKER, not an automatic passing score.
"""
from __future__ import annotations
import argparse,csv,json,math
from pathlib import Path

KEY_FIELDS=("corner","device","Vds_or_Vsd_V","Vgs_or_Vsg_V")
CURR="absolute_drain_current_A"

def read(path):
    if not path.is_file():
        raise FileNotFoundError(
            f"Actual HSPICE reference CSV unavailable: {path}; "
            "cannot claim cross-simulator equivalence.")
    with path.open(newline="",encoding="utf-8-sig") as f:
        rows=list(csv.DictReader(f))
    if not rows:raise ValueError(f"Empty CSV: {path}")
    for col in KEY_FIELDS+(CURR,):
        if col not in rows[0]:raise ValueError(f"{path}: missing column {col}")
    result={}
    for a in rows:
        key=(a["corner"].lower(),a["device"].lower(),
             round(float(a["Vds_or_Vsd_V"]),5),
             round(float(a["Vgs_or_Vsg_V"]),5))
        val=abs(float(a[CURR]))
        if not math.isfinite(val):raise ValueError("Nonfinite current")
        result[key]=val
    return result

def compare(reference:Path,model:Path,out:Path,cutoff=1e-6):
    hspice=read(reference)
    ngspice=read(model)
    keys=sorted(set(hspice)&set(ngspice))
    if len(keys)<10:raise RuntimeError("Too few matching HSPICE/ngspice I-V points")
    rows=[]
    for key in keys:
        h,n=hspice[key],ngspice[key]
        if h<cutoff:continue
        rows.append({**dict(zip(KEY_FIELDS,key)),
            "hspice_current_A":h,"ngspice_current_A":n,
            "current_relative_deviation_pct":100*(n-h)/h,
            "current_absolute_error_A":abs(n-h)})
    if len(rows)<10:raise RuntimeError("Too few matched above-threshold currents")
    values=[r["current_relative_deviation_pct"] for r in rows]
    report={
        "status":"numeric_correlation_report_actual_hspice_provided",
        "source_hspice":str(reference),
        "source_ngspice":str(model),
        "matched_above_threshold_points":len(rows),
        "ref_current_cutoff_A":cutoff,
        "mean_abs_current_error_pct":sum(abs(v) for v in values)/len(values),
        "rms_current_error_pct":math.sqrt(sum(v*v for v in values)/len(values)),
        "max_abs_current_error_pct":max(abs(v) for v in values),
        "limitations":[
            "Current-only DC correlation; does not check capacitance, noise or transient",
            "Same device geometries, bulk/sub connections and measurement temperatures must be checked separately"
        ]
    }
    out.mkdir(parents=True,exist_ok=True)
    (out/"hspice_ngspice_iv_comparison.json").write_text(json.dumps(report,indent=2)+"\n")
    with (out/"hspice_ngspice_iv_comparison.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    print(json.dumps(report,indent=2))
    return report

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--hspice",type=Path,required=True,
                   help="Measured/exported HSPICE reference CSV, NOT a renamed ngspice file")
    a.add_argument("--ngspice",type=Path,default=Path("results/spice/p3_device_iv/dbhitek_ngspice_device_iv.csv"))
    a.add_argument("--out",type=Path,default=Path("results/spice/hspice_correlation"))
    p=a.parse_args()
    compare(p.hspice,p.ngspice,p.out)
